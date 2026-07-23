"""Single source of truth for ticket routing and status transitions.

Status model (v2):
    ai          — AI is handling the dialog; no operator bound
    queue       — escalated to humans, waiting for a free operator slot
    in_progress — bound to an operator, SLA clock running (occupies a slot)
    waiting     — paused, still bound; waiting_reason: 'operator_replied'
                  (blue «ждём ответ») | 'manual' (red «клиент ждёт ответ»);
                  does NOT occupy a slot
    closed      — finished

All status writes, SLA accounting, routing system messages, n8n syncs and the
resulting WebSocket broadcasts go through RoutingEngine so the rules live in
one place. Assignment capacity is enforced by the advisory-locked primitives
in DatabaseManager (assign_dialog / claim_next_queued / claim_pending_return).
"""
import asyncio

from app.database import DatabaseManager
from app.n8n_client import N8NClient
from app.serializers import fmt_dialog, fmt_message
from app.ws_manager import WebSocketManager

WAITING_OPERATOR_REPLIED = "operator_replied"  # blue  «ждём ответ»
WAITING_MANUAL = "manual"                      # red   «клиент ждёт ответ»

AUTOMATION_DEFAULTS = {
    "operator_button_enabled": False,
    "operator_button_after_msgs": 3,
    "auto_handoff_enabled": False,
    "rating_enabled": False,
    "rating_message_text": "Оцените качество поддержки:",
    "rating_thanks_text": "Спасибо за оценку! 🙏",
    "close_message_enabled": False,
    "close_message_text": "Спасибо за обращение! Если появятся вопросы — просто напишите нам.",
    "max_tickets_per_operator": 10,
    "offline_grace_seconds": 60,
    # Промпт гейта-маршрутизатора: возвращает РОВНО HANDOFF или CONTINUE. n8n
    # публикует его отдельным полем vpn_bot:ai_settings.handoff_prompt (см.
    # web_server._sync_ai_settings_to_redis), к промпту ответчика не
    # приклеивается; счётчик и историю дописывает воркфлоу. Редактируется в
    # панели; пустое значение падает на этот дефолт, чтобы гейт не остался без
    # критериев. Здесь только статическая часть — без плейсхолдеров.
    "handoff_instruction_text": (
        "Ты — модуль-маршрутизатор поддержки GruVPN. Единственная задача: решить, "
        "передать ли диалог живому оператору или бот-ответчик может продолжать. Ты НЕ "
        "пишешь ответ пользователю и НЕ даёшь инструкций. Верни РОВНО одно слово: "
        "HANDOFF или CONTINUE. Без пояснений и знаков препинания.\n\n"
        "Ответь HANDOFF, если выполнено любое:\n"
        "- пользователь явно просит живого оператора или человека;\n"
        "- нужен сотрудник или проверка данных аккаунта: оплата, возврат, двойное "
        "списание, удалённый или утёкший ключ, перенос аккаунта, конкретный сервер, "
        "ручная проверка подписки;\n"
        "- бот уже давал набор шагов по этой проблеме, и пользователь снова сообщает о "
        "неудаче ЛЮБЫМИ словами (например: «не помогло», «всё сделал», «всё равно не "
        "работает», «глухо», «по нулям», «и что дальше», «то же самое») — формулировка "
        "не важна;\n"
        "- по счётчику ниже бот уже выдал два или более наборов шагов;\n"
        "- пользователь называет клиент, приложение или ситуацию, по которой у бота "
        "явно нет надёжной информации, и ответ начинает подменять её похожей (например "
        "отвечает про Happ, когда спросили про другой клиент).\n\n"
        "Ответь CONTINUE в остальных случаях: новый вопрос, первое обращение, "
        "уточнение, короткий ответ по текущему сценарию (устройство, сеть, «да»/«нет»), "
        "благодарность, или бот ещё ни разу не давал шагов по этой проблеме."
    ),
    # Deterministic escalation: a client message on an AI dialog matching any
    # of these keywords (comma-separated, case-insensitive) escalates
    # immediately — no LLM judgement involved. A multi-word keyword matches
    # when ALL its parts occur as substrings, so word stems cover Russian
    # inflection: «жив человек» matches «живого человека».
    "operator_call_keywords": "оператор, менеджер, жив человек, реальн человек, поддержк",
}


class RoutingEngine:
    def __init__(self, db: DatabaseManager, ws: WebSocketManager, n8n: N8NClient):
        self.db = db
        self.ws = ws
        self.n8n = n8n

    # ── Internals ─────────────────────────────────────────────────────────────

    async def _automation(self) -> dict:
        stored = await self.db.get_setting_json("automation", None) or {}
        return {**AUTOMATION_DEFAULTS, **stored}

    @staticmethod
    def _cfg_int(automation: dict, key: str) -> int:
        # `or default` would eat an explicit 0 (e.g. offline_grace_seconds=0
        # meaning "reassign immediately") — fall back only on missing/None.
        val = automation.get(key)
        return int(AUTOMATION_DEFAULTS[key] if val is None else val)

    async def _max_tickets(self, automation: dict = None) -> int:
        automation = automation or await self._automation()
        return self._cfg_int(automation, "max_tickets_per_operator")

    async def _grace_seconds(self, automation: dict = None) -> int:
        automation = automation or await self._automation()
        return self._cfg_int(automation, "offline_grace_seconds")

    async def _emit(self, dialog_id: str, sys_text: str = None) -> dict | None:
        """Optionally record a system message, then broadcast the fresh dialog."""
        if sys_text:
            row = await self.db.save_message(dialog_id, "system", sys_text)
            await self.ws.broadcast({"type": "new_message", "dialog_id": dialog_id,
                                     "message": fmt_message(row)})
        updated = await self.db.get_dialog(dialog_id)
        if updated:
            await self.ws.broadcast({"type": "dialog_updated", "dialog": fmt_dialog(updated)})
        return updated

    async def _disable_ai(self, dialog: dict):
        """Turn the AI off for the dialog (no-op if it is already off)."""
        if not dialog.get("ai_enabled"):
            return
        dialog_id, chat_id = dialog["dialog_id"], dialog["chat_id"]
        await self.db.update_ai_enabled(dialog_id, False)
        await self.db.sync_n8n_dialog_ai_status(chat_id, False)
        await self.n8n.notify_ai_toggled(dialog_id, chat_id, False)

    async def _notify_operator_called(self, dialog: dict):
        username = dialog.get("user_username") or dialog["dialog_id"]
        await self.n8n.schedule_notify(
            "operator_called", {"dialog_id": dialog["dialog_id"], "username": username}
        )

    # ── Transitions ───────────────────────────────────────────────────────────

    async def handoff_from_ai(self, dialog_id: str, reason: str = None) -> str | None:
        """AI → humans (scenario 1). AI is disabled at handoff time; the ticket
        lands in_progress if an online operator has a free slot, else in queue.
        `reason` is the AI's own explanation — shown to operators in the
        system message."""
        dialog = await self.db.get_dialog(dialog_id)
        if not dialog or dialog["status"] != "ai":
            return None
        await self._disable_ai(dialog)
        await self.db.update_operator_called(dialog_id, True)
        suffix = f" — причина: {reason}" if reason else ""
        op_name = await self.db.assign_dialog(dialog_id, await self._max_tickets())
        if op_name:
            await self._emit(dialog_id, f"ИИ передал диалог оператору {op_name}{suffix}")
        else:
            await self.db.move_to_queue(dialog_id)
            await self._emit(dialog_id, f"ИИ передал диалог в очередь{suffix}")
        await self._notify_operator_called(dialog)
        return op_name

    async def maybe_escalate_by_keywords(self, dialog: dict, text: str) -> bool:
        """Deterministic handoff: the client explicitly asked for a human in
        plain words («позови оператора») while the AI still owns the dialog.
        Fires regardless of what the model does — the [HANDOFF] marker is the
        AI's own judgement, this is the guarantee on top of it. Gated by the
        same «Авто-вызов от ИИ» toggle as the marker path — with escalation
        entirely off, stop-words must not be a separate live channel."""
        if dialog["status"] != "ai" or not text:
            return False
        automation = await self._automation()
        if not automation.get("auto_handoff_enabled"):
            return False
        keywords = [k.strip().lower() for k in
                    str(automation.get("operator_call_keywords") or "").split(",") if k.strip()]
        if not keywords:
            return False
        lowered = text.lower()
        # A multi-word keyword matches when all its parts are present — stems
        # survive Russian inflection («жив человек» ловит «живого человека»).
        if not any(all(part in lowered for part in k.split()) for k in keywords):
            return False
        await self.handoff_from_ai(dialog["dialog_id"], reason="клиент попросил оператора")
        return True

    async def on_operator_requested(self, dialog: dict) -> str | None:
        """The client explicitly asked for a human (call-operator button).
        From «ИИ» this is a full handoff; a ticket that is already escalated
        (queue/in_progress/waiting) just gets the operator_called flag raised
        and operators re-notified — it must never be a silent no-op."""
        dialog_id = dialog["dialog_id"]
        if dialog["status"] == "ai":
            return await self.handoff_from_ai(dialog_id)
        if dialog["status"] != "closed" and not dialog.get("operator_called"):
            await self.db.update_operator_called(dialog_id, True)
            await self._emit(dialog_id)
            await self._notify_operator_called(dialog)
        return dialog.get("assigned_operator")

    async def take_in_work(self, dialog_id: str, op_name: str) -> dict | None:
        """Operator manually takes an ai/queue ticket («Взять в работу»).
        Bypasses slot limits — an explicit human decision."""
        dialog = await self.db.get_dialog(dialog_id)
        if not dialog or dialog["status"] == "closed":
            return None
        await self._disable_ai(dialog)
        await self.db.update_operator_called(dialog_id, True)
        await self.db.move_to_in_progress(dialog_id, op_name)
        updated = await self._emit(dialog_id, f"Диалог взят в работу оператором {op_name}")
        await self._notify_operator_called(dialog)
        return updated

    async def on_operator_reply(self, dialog: dict, op_name: str):
        """Scenario 2: after the operator's message is saved/sent, the ticket
        moves to waiting («ждём ответ»), SLA pauses, the slot frees up."""
        dialog_id = dialog["dialog_id"]
        status = dialog["status"]
        if status in ("in_progress", "waiting"):
            # waiting(manual) → waiting(operator_replied): red label turns blue
            await self.db.move_to_waiting(dialog_id, WAITING_OPERATOR_REPLIED)
        elif status in ("ai", "queue"):
            # Sane takeover: replying to an unassigned ticket binds it to the
            # replier, then it immediately waits for the client.
            await self._disable_ai(dialog)
            await self.db.update_operator_called(dialog_id, True)
            await self.db.move_to_in_progress(dialog_id, op_name)
            await self.db.move_to_waiting(dialog_id, WAITING_OPERATOR_REPLIED)
        # closed: replying does not reopen — status untouched (as before)
        await self._emit(dialog_id)
        await self.drain()  # the freed slot may serve the queue

    async def set_waiting_manual(self, dialog_id: str, op_name: str) -> dict:
        """New button «В ожидание»: operator pauses an in_progress ticket while
        e.g. waiting for the team; the client is still owed an answer (red label)."""
        dialog = await self.db.get_dialog(dialog_id)
        if not dialog:
            raise LookupError(dialog_id)
        if dialog["status"] != "in_progress":
            raise ValueError("Only in_progress tickets can be paused manually")
        await self.db.move_to_waiting(dialog_id, WAITING_MANUAL)
        updated = await self._emit(dialog_id, f"Тикет переведён в ожидание оператором {op_name}")
        await self.drain()
        return updated

    async def on_client_message(self, dialog: dict):
        """Scenario 3/5: a client message on a waiting ticket asks to return to
        work; other statuses are unaffected (closed dialogs are reopened by
        upsert_dialog before this point)."""
        if dialog["status"] != "waiting":
            return
        dialog_id = dialog["dialog_id"]
        await self.db.set_return_requested(dialog_id)
        fresh = await self.db.get_dialog(dialog_id)
        await self.resolve_pending_return(fresh)

    async def resolve_pending_return(self, dialog: dict, drain_after: bool = True):
        """Route a waiting ticket whose client already replied. Bound operator
        online (or briefly offline, within grace) → it comes back to HIM as soon
        as HE has a free slot; gone for longer than the grace → unbind and route
        like a fresh handoff."""
        dialog_id = dialog["dialog_id"]
        op_name = dialog.get("assigned_operator")
        grace = await self._grace_seconds()
        if op_name and await self.db.is_operator_within_grace(op_name, grace):
            if drain_after:
                await self.drain()
            return
        if op_name:
            await self.db.set_assigned_operator(dialog_id, None)
        await self.assign_or_queue(
            dialog_id,
            queued_msg="Оператор недоступен — тикет возвращён в очередь",
        )

    async def assign_or_queue(self, dialog_id: str,
                              assigned_msg: str = None, queued_msg: str = None):
        """Try instant assignment; fall back to the queue."""
        op_name = await self.db.assign_dialog(dialog_id, await self._max_tickets())
        if op_name:
            await self._emit(dialog_id, assigned_msg or f"Диалог назначен оператору {op_name}")
        else:
            await self.db.move_to_queue(dialog_id)
            await self._emit(dialog_id, queued_msg or "Диалог переведён в очередь")
        return op_name

    async def return_to_queue(self, dialog_id: str) -> dict:
        """«Вернуть в очередь»: unbind and queue for another operator. The AI is
        NOT re-enabled — the ticket was already escalated; use the AI toggle to
        hand it back to the bot."""
        await self.db.move_to_queue(dialog_id)
        updated = await self._emit(dialog_id, "Диалог возвращён в очередь")
        await self.drain()
        return updated

    async def close(self, dialog_id: str, chat_id: str, closed_by: str) -> dict:
        await self.db.move_to_closed(dialog_id)
        updated = await self._emit(dialog_id, "Диалог закрыт оператором")
        await self.db.sync_n8n_dialog_status(chat_id, "closed")
        await self.n8n.notify_dialog_closed(dialog_id, chat_id, closed_by)
        await self.drain()  # the freed slot may serve the queue
        return updated

    async def reopen_closed(self, dialog_id: str, chat_id: str) -> dict:
        """«Открыть снова»: back to the queue, unassigned; AI stays off."""
        await self.db.move_to_queue(dialog_id)
        updated = await self._emit(dialog_id, "Диалог переоткрыт оператором")
        await self.db.sync_n8n_dialog_status(chat_id, "active")
        await self.drain()
        return updated

    async def transfer(self, dialog_id: str, target_op: str) -> dict:
        """Move the binding to another operator. in_progress/waiting keep their
        status (SLA keeps running for in_progress); ai/queue land in_progress."""
        dialog = await self.db.get_dialog(dialog_id)
        if not dialog:
            raise LookupError(dialog_id)
        if dialog["status"] in ("in_progress", "waiting"):
            await self.db.set_assigned_operator(dialog_id, target_op)
        else:
            await self._disable_ai(dialog)
            await self.db.update_operator_called(dialog_id, True)
            await self.db.move_to_in_progress(dialog_id, target_op)
        updated = await self._emit(dialog_id, f"Тикет передан оператору {target_op}")
        await self.drain()  # the previous operator's slot may have freed
        return updated

    async def release_offline_operator(self, op: dict):
        """Offline grace expired: the operator's in_progress tickets go back to
        the queue. Waiting tickets with the blue «ждём ответ» label stay bound
        (the ball is on the client's side — they wake up on a client reply),
        but red manual ones («клиент ждёт ответ») are owed an answer and must
        not stay bound to a gone operator."""
        for d in await self.db.get_operator_dialogs_by_status(op["name"], "in_progress"):
            await self.db.move_to_queue(d["dialog_id"])
            await self._emit(d["dialog_id"], "Оператор офлайн — тикет возвращён в очередь")
        for d in await self.db.get_operator_dialogs_by_status(op["name"], "waiting"):
            if d.get("waiting_reason") == WAITING_MANUAL:
                await self.db.move_to_queue(d["dialog_id"])
                await self._emit(d["dialog_id"], "Оператор офлайн — тикет возвращён в очередь")
        # Consume the grace timer: from now on the operator counts as gone.
        await self.db.set_operator_offline_since(op["id"], False)

    async def on_ai_toggled(self, dialog_id: str, ai_enabled: bool):
        """Keep the AI flag and the status model coherent (called after the
        toggle endpoint flipped ai_enabled)."""
        dialog = await self.db.get_dialog(dialog_id)
        if not dialog:
            return
        if ai_enabled and dialog["status"] == "queue":
            # The bot takes the ticket back — leave the human queue.
            await self.db.move_to_ai(dialog_id)
            await self._emit(dialog_id, "Диалог возвращён ИИ")
        elif not ai_enabled and dialog["status"] == "ai":
            # AI switched off while unattended — escalate so nobody loses it.
            await self.handoff_from_ai(dialog_id)

    # ── Queue draining ────────────────────────────────────────────────────────

    async def drain(self):
        """Serve as much as capacity allows: first waiting tickets whose client
        already replied (back to their own operators), then the global queue.
        Safe to call from anywhere; errors are logged, never raised."""
        try:
            max_tickets = await self._max_tickets()
            while True:
                result = await self.db.claim_pending_return(max_tickets)
                if not result:
                    break
                await self._emit(
                    result["dialog"]["dialog_id"],
                    f"Клиент ответил — тикет возвращён оператору {result['op_name']}",
                )
            while True:
                result = await self.db.claim_next_queued(max_tickets)
                if not result:
                    break
                dialog = result["dialog"]
                dialog_id = dialog["dialog_id"]
                # Defensive: legacy queued rows predating the handoff-time AI-off.
                await self._disable_ai(dialog)
                await self._emit(dialog_id, f"Диалог назначен оператору {result['op_name']}")
        except Exception as e:
            print(f"[routing.drain] error: {e}")

    # ── Background sweeper ────────────────────────────────────────────────────

    async def sweep_forever(self, interval: int = 10):
        """Timestamp-based fallback loop: expires offline graces, retries pending
        returns and drains the queue even if an event-driven drain was lost
        (e.g. across a restart). All state lives in Postgres."""
        print("Routing sweeper started")
        while True:
            await asyncio.sleep(interval)
            try:
                grace = await self._grace_seconds()
                for op in await self.db.get_offline_expired_operators(grace):
                    await self.release_offline_operator(op)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                print(f"[routing.sweep] offline-grace error: {e}")
            try:
                for d in await self.db.get_return_requested_dialogs():
                    await self.resolve_pending_return(d, drain_after=False)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                print(f"[routing.sweep] pending-return error: {e}")
            await self.drain()
