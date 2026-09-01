"""Резервный канал доставки ответа оператора.

Штатно ответ уходит через n8n в business-чат Telegram. Иногда Telegram отвечает
`400 BUSINESS_PEER_USAGE_MISSING` — сообщение просто теряется, и оператор видит
красный крестик, ничего не в силах сделать. Тогда панель пробует ещё раз, но уже
напрямую по MTProto, от того же аккаунта поддержки: клиент получает сообщение в
той же переписке, а не в чате с ботом, который выдаёт ключи.

Настройка пер-сервисная (`fallback_sender` в таблице settings), как `customer` и
`monitoring`:

    {"enabled": true,
     "config": {"app_id": 123456, "app_hash": "…", "phone": "+7…",
                "session": "<StringSession>", "account": "@support"}}

`app_id` и `app_hash` берутся на my.telegram.org. Строку сессии выдаёт
авторизация из формы сервиса (код из Телеграм плюс, если стоит, пароль 2FA);
её же можно вставить готовой, если она сгенерирована снаружи.

Telethon импортируется лениво, внутри методов: панель обязана подниматься и без
установленного пакета — просто без резервного канала.
"""
import asyncio
import json
import time

import aiohttp

FALLBACK_DEFAULTS = {"enabled": False, "config": {}}

# Незавершённые авторизации живут в памяти процесса: между «отправить код» и
# «ввести код» проходят секунды, и класть недо-сессию в базу незачем.
_PENDING_TTL = 600

# Telethon сам не ограничивает время на подключение: за фаерволом, который не
# пускает к серверам Telegram, форма крутилась бы вечно, а оператор ждал бы
# ответа на недоставленное сообщение. Лучше внятная ошибка.
_CONNECT_TIMEOUT = 30
_SEND_TIMEOUT = 60


class _Timeout(RuntimeError):
    """Отдельный тип, чтобы отличить «Telegram недоступен» от отказа Telegram."""

    def __init__(self, what: str):
        super().__init__(f"Telegram не отвечает ({what}) — проверьте, "
                         f"что сервер панели ходит наружу")


def _install_hint(error: Exception) -> str:
    return (f"Telethon не установлен ({error}). Добавьте telethon в requirements.txt "
            f"и пересоберите образ.")


class TelethonSender:
    """Один аккаунт Telegram на один ВПН-сервис.

    Клиент создаётся лениво и переиспользуется: авторизация по MTProto стоит
    несколько секунд, а фолбек может понадобиться на каждом втором сообщении,
    пока business-подключение не починят.
    """

    def __init__(self, config: dict):
        self.config = config or {}
        self._client = None
        self._lock = asyncio.Lock()

    @property
    def account(self) -> str:
        return self.config.get("account") or ""

    async def _connect(self):
        if self._client is not None and self._client.is_connected():
            return self._client
        async with self._lock:
            if self._client is not None and self._client.is_connected():
                return self._client
            from telethon import TelegramClient
            from telethon.sessions import StringSession
            session = self.config.get("session") or ""
            if not session:
                raise RuntimeError("аккаунт не авторизован")
            client = TelegramClient(
                StringSession(session),
                int(self.config.get("app_id") or 0),
                str(self.config.get("app_hash") or ""),
            )
            try:
                await asyncio.wait_for(client.connect(), _CONNECT_TIMEOUT)
                authorized = await asyncio.wait_for(client.is_user_authorized(),
                                                    _CONNECT_TIMEOUT)
            except asyncio.TimeoutError:
                await client.disconnect()
                raise _Timeout("подключение")
            if not authorized:
                await client.disconnect()
                raise RuntimeError("сессия больше не действует — авторизуйтесь заново")
            self._client = client
            return client

    async def close(self):
        if self._client is not None:
            try:
                await self._client.disconnect()
            except Exception:
                pass
            self._client = None

    async def send(self, chat_id: str, text: str,
                   file_url: str = None) -> tuple[bool, str]:
        """(получилось, пояснение). Исключений не бросает: неудача резервного
        канала — это результат, который надо показать оператору, а не сбой
        панели."""
        try:
            client = await self._connect()
        except ImportError as e:
            return False, _install_hint(e)
        except Exception as e:
            return False, str(e)[:200]

        try:
            peer = int(str(chat_id).strip())
        except ValueError:
            return False, f"нечисловой chat_id {chat_id!r}"

        try:
            if file_url:
                data = await self._download(file_url)
                if data is None:
                    return False, f"не удалось скачать вложение {file_url}"
                blob, name = data
                await asyncio.wait_for(
                    client.send_file(peer, blob, caption=text or None,
                                     file_name=name, force_document=False),
                    _SEND_TIMEOUT)
            else:
                if not text:
                    return False, "пустое сообщение"
                await asyncio.wait_for(client.send_message(peer, text), _SEND_TIMEOUT)
        except asyncio.TimeoutError:
            await self.close()
            return False, str(_Timeout("отправка"))
        except Exception as e:
            # Сессия могла протухнуть между вызовами — следующий заход
            # переподключится с нуля.
            await self.close()
            return False, str(e)[:200]
        return True, f"доставлено с аккаунта {self.account or 'поддержки'}"

    @staticmethod
    async def _download(url: str):
        """Вложение уже лежит у нас (или в S3) — качаем в память: файлы в чате
        поддержки небольшие, ради них не стоит городить временные файлы."""
        try:
            timeout = aiohttp.ClientTimeout(total=60)
            async with aiohttp.ClientSession(timeout=timeout) as s:
                async with s.get(url) as r:
                    if r.status >= 400:
                        return None
                    return await r.read(), url.rstrip("/").split("/")[-1] or "file"
        except Exception as e:
            print(f"[fallback] не скачалось {url}: {e}")
            return None


class FallbackSenderService:
    """Резервные отправители по сервисам: кэш, настройки и авторизация.

    Устроено как CustomerService.provider_for — объект пересоздаётся только
    когда админ поменял настройки.
    """

    def __init__(self, db):
        self.db = db
        self._senders: dict[int, tuple[str, TelethonSender]] = {}
        self._pending: dict[int, dict] = {}

    # ── Настройки ─────────────────────────────────────────────────────────────

    async def settings(self, service_id: int) -> dict:
        stored = await self.db.get_setting_json("fallback_sender", None, service_id) or {}
        return {**FALLBACK_DEFAULTS, **stored}

    async def save(self, service_id: int, data: dict) -> None:
        await self.db.set_setting_json("fallback_sender", data, service_id)
        self.invalidate(service_id)

    def invalidate(self, service_id: int) -> None:
        cached = self._senders.pop(service_id, None)
        if cached:
            asyncio.create_task(cached[1].close())

    async def sender_for(self, service_id: int) -> TelethonSender | None:
        """Настроенный и включённый отправитель либо None."""
        cfg = await self.settings(service_id)
        config = cfg.get("config") or {}
        if not cfg.get("enabled") or not config.get("session"):
            return None
        key = json.dumps(config, sort_keys=True, ensure_ascii=False)
        cached = self._senders.get(service_id)
        if cached and cached[0] == key:
            return cached[1]
        if cached:
            await cached[1].close()
        sender = TelethonSender(config)
        self._senders[service_id] = (key, sender)
        return sender

    async def send(self, service_id: int, chat_id: str, text: str,
                   file_url: str = None) -> tuple[bool, str]:
        """(получилось, пояснение). Не настроен — «выключен», и это не ошибка:
        большинству установок резервный канал не нужен."""
        sender = await self.sender_for(service_id)
        if not sender:
            return False, ""
        return await sender.send(chat_id, text, file_url)

    # ── Авторизация из админки ────────────────────────────────────────────────

    def _sweep_pending(self) -> None:
        now = time.monotonic()
        for sid, item in list(self._pending.items()):
            if now - item["at"] > _PENDING_TTL:
                asyncio.create_task(self._drop_pending(sid))

    async def _drop_pending(self, service_id: int) -> None:
        item = self._pending.pop(service_id, None)
        if item:
            try:
                await item["client"].disconnect()
            except Exception:
                pass

    async def send_code(self, service_id: int, app_id: int, app_hash: str,
                        phone: str) -> dict:
        """Шаг 1: попросить Telegram выслать код на телефон аккаунта поддержки."""
        self._sweep_pending()
        await self._drop_pending(service_id)
        try:
            from telethon import TelegramClient
            from telethon.sessions import StringSession
        except ImportError as e:
            raise RuntimeError(_install_hint(e))
        client = TelegramClient(StringSession(), int(app_id), str(app_hash))
        try:
            await asyncio.wait_for(client.connect(), _CONNECT_TIMEOUT)
            sent = await asyncio.wait_for(client.send_code_request(phone), _CONNECT_TIMEOUT)
        except asyncio.TimeoutError:
            await client.disconnect()
            raise _Timeout("запрос кода")
        except Exception:
            await client.disconnect()
            raise
        self._pending[service_id] = {
            "client": client, "phone": phone, "hash": sent.phone_code_hash,
            "app_id": int(app_id), "app_hash": str(app_hash), "at": time.monotonic(),
        }
        return {"ok": True, "needsCode": True}

    async def sign_in(self, service_id: int, code: str, password: str = "") -> dict:
        """Шаг 2: код (и пароль 2FA, если он стоит). На успехе сохраняем строку
        сессии в настройку сервиса."""
        item = self._pending.get(service_id)
        if not item:
            raise RuntimeError("Код устарел — запросите новый")
        client = item["client"]
        try:
            from telethon.errors import SessionPasswordNeededError
        except ImportError as e:
            raise RuntimeError(_install_hint(e))
        try:
            if password:
                await asyncio.wait_for(client.sign_in(password=password), _CONNECT_TIMEOUT)
            else:
                await asyncio.wait_for(
                    client.sign_in(item["phone"], code, phone_code_hash=item["hash"]),
                    _CONNECT_TIMEOUT)
        except asyncio.TimeoutError:
            await self._drop_pending(service_id)
            raise _Timeout("вход")
        except SessionPasswordNeededError:
            # Клиента не отпускаем: пароль придёт следующим запросом.
            item["at"] = time.monotonic()
            return {"ok": False, "needs2fa": True}
        except Exception:
            await self._drop_pending(service_id)
            raise

        me = await asyncio.wait_for(client.get_me(), _CONNECT_TIMEOUT)
        account = ("@" + me.username) if getattr(me, "username", None) else str(me.id)
        session = client.session.save()
        await client.disconnect()
        self._pending.pop(service_id, None)

        stored = await self.settings(service_id)
        await self.save(service_id, {
            **stored, "enabled": True,
            "config": {**(stored.get("config") or {}),
                       "app_id": item["app_id"], "app_hash": item["app_hash"],
                       "phone": item["phone"], "session": session, "account": account},
        })
        return {"ok": True, "account": account}

    async def check(self, service_id: int) -> dict:
        """От какого аккаунта уйдут сообщения — проверка перед боем."""
        cfg = await self.settings(service_id)
        config = cfg.get("config") or {}
        if not config.get("session"):
            return {"ok": False, "error": "Аккаунт не авторизован"}
        sender = TelethonSender(config)
        try:
            client = await sender._connect()
            me = await asyncio.wait_for(client.get_me(), _CONNECT_TIMEOUT)
            account = ("@" + me.username) if getattr(me, "username", None) else str(me.id)
            return {"ok": True, "account": account}
        except ImportError as e:
            return {"ok": False, "error": _install_hint(e)}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}
        finally:
            await sender.close()

    async def close(self) -> None:
        for _, sender in list(self._senders.values()):
            await sender.close()
        self._senders.clear()
        for sid in list(self._pending):
            await self._drop_pending(sid)
