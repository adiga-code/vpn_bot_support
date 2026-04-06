import redis.asyncio as aioredis
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from app.config import Settings
from app.database import DatabaseManager
from app.n8n_client import N8NClient


class TelegramBot:
    """Telegram бот с минимальной локальной БД"""

    def __init__(self, settings: Settings, db: DatabaseManager, redis: aioredis.Redis):
        self.settings = settings
        self.db = db
        self.bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
        self.dp = Dispatcher()
        self.n8n_client = N8NClient(settings, redis)
        
        self._register_handlers()
    
    def _register_handlers(self):
        """Регистрация обработчиков"""
        
        @self.dp.message()
        async def handle_manager_message(message: Message):
            if message.chat.id != self.settings.TELEGRAM_GROUP_ID:
                return
            
            if not message.message_thread_id:
                return
            
            # Удаляем системные сообщения
            if (message.forum_topic_edited or message.forum_topic_created or 
                message.forum_topic_closed or message.forum_topic_reopened):
                try:
                    await message.delete()
                except Exception as e:
                    print(f"⚠️ Could not delete service message: {e}")
                return
            
            # Игнорируем ботов
            if message.from_user and message.from_user.is_bot:
                return
            
            # Игнорируем пустые сообщения
            if not message.text and not message.photo and not message.video:
                return
            
            # Получаем chat_id по topic_id
            chat_id = await self.db.get_chat_id_by_topic(message.message_thread_id)
            
            if not chat_id:
                await message.reply("⚠️ Топик не найден в базе данных")
                return
            
            # Формируем текст
            if message.text:
                text = message.text
            elif message.photo:
                text = f"[Фото{': ' + message.caption if message.caption else ''}]"
            elif message.video:
                text = f"[Видео{': ' + message.caption if message.caption else ''}]"
            else:
                text = "[Медиа]"
            
            # Отправляем в n8n
            success = await self.n8n_client.send_manager_message(chat_id, text)
            
            if success:
                try:
                    await message.react([types.ReactionTypeEmoji(emoji="👍")])
                except Exception as e:
                    print(f"⚠️ Could not add reaction: {e}")
            else:
                await message.reply("❌ Ошибка отправки в n8n")
        
        @self.dp.callback_query()
        async def handle_callback(callback: types.CallbackQuery):
            """Обработка нажатия кнопки переключения AI"""
            
            # Валидация callback_data
            if not callback.data or not callback.data.startswith("toggle_ai:"):
                try:
                    await callback.answer("❌ Неверные данные кнопки", show_alert=True)
                except Exception:
                    pass
                return
            
            # Извлечение chat_id
            parts = callback.data.split(":")
            if len(parts) != 2:
                try:
                    await callback.answer("❌ Некорректный формат данных", show_alert=True)
                except Exception:
                    pass
                return
            
            chat_id = parts[1]
            print(f"🔘 Button pressed for chat_id: {chat_id}")
            
            # Отправка запроса в n8n
            result = await self.n8n_client.toggle_ai_status(chat_id)
            
            # Обработка результата
            if result is None:
                # Критическая ошибка (не должно происходить)
                try:
                    await callback.answer(
                        "❌ Критическая ошибка переключения AI",
                        show_alert=True
                    )
                except Exception:
                    pass
                return
            
            # Проверка на ошибку
            if "error" in result:
                error_msg = result["error"]
                details = result.get("details", "")
                print(f"❌ Toggle failed: {error_msg} | {details}")
                
                try:
                    await callback.answer(
                        f"❌ {error_msg}\n\nПопробуйте позже",
                        show_alert=True
                    )
                except Exception:
                    pass
                return
            
            # Успешное переключение
            if "ai_enabled" in result:
                new_state = result["ai_enabled"]
                
                # Обновляем иконку топика
                topic_id = await self.db.get_topic_id(chat_id)
                if topic_id:
                    icon_updated = await self._update_topic_icon(topic_id, new_state)
                    if not icon_updated:
                        print(f"⚠️ Failed to update topic icon for {chat_id}")
                
                # Показываем уведомление пользователю
                status_text = "включен ✅" if new_state else "выключен ⏸"
                try:
                    await callback.answer(
                        f"AI {status_text}",
                        show_alert=True
                    )
                except Exception as e:
                    # Callback может быть слишком старым
                    if "too old" not in str(e).lower():
                        print(f"⚠️ Callback answer error: {e}")
                
                print(f"✅ AI toggled successfully: {chat_id} -> {new_state}")
            else:
                # Неожиданный формат ответа (не должно происходить после проверок)
                try:
                    await callback.answer(
                        "❌ Некорректный ответ от сервера",
                        show_alert=True
                    )
                except Exception:
                    pass
    
    async def _update_topic_icon(self, topic_id: int, ai_enabled: bool) -> bool:
        """
        Обновить иконку топика
        
        Args:
            topic_id: ID топика
            ai_enabled: Статус AI (True = включен, False = выключен)
            
        Returns:
            True если успешно, False при ошибке
        """
        try:
            icon_emoji_id = (
                self.settings.ICON_AI_ENABLED if ai_enabled 
                else self.settings.ICON_AI_DISABLED
            )
            
            await self.bot.edit_forum_topic(
                chat_id=self.settings.TELEGRAM_GROUP_ID,
                message_thread_id=topic_id,
                icon_custom_emoji_id=icon_emoji_id
            )
            
            status = "включен" if ai_enabled else "выключен"
            print(f"✅ Topic icon updated: AI {status}")
            return True
            
        except Exception as e:
            # TOPIC_NOT_MODIFIED - иконка уже такая же, это не ошибка
            if "TOPIC_NOT_MODIFIED" in str(e):
                print(f"ℹ️ Topic icon already correct")
                return True
            
            print(f"❌ Error updating topic icon: {e}")
            return False
    
    async def send_user_message(
        self, 
        chat_id: str, 
        message: str, 
        ai_enabled: bool = True
    ) -> bool:
        """Отправить сообщение от пользователя в топик"""
        try:
            topic_id = await self.db.get_topic_id(chat_id)
            
            # Создаем топик если нет
            if not topic_id:
                topic_name = chat_id
                icon_emoji_id = (
                    self.settings.ICON_AI_ENABLED if ai_enabled 
                    else self.settings.ICON_AI_DISABLED
                )
                
                topic = await self.bot.create_forum_topic(
                    chat_id=self.settings.TELEGRAM_GROUP_ID,
                    name=topic_name,
                    icon_custom_emoji_id=icon_emoji_id
                )
                topic_id = topic.message_thread_id
                
                # Сохраняем только маппинг (без ai_enabled)
                await self.db.save_chat_topic(
                    chat_id=chat_id,
                    topic_id=topic_id,
                    topic_name=topic_name
                )
                
                print(f"✅ Created topic: {topic_name} (ID: {topic_id}, AI: {ai_enabled})")
            else:
                # Топик существует - обновляем иконку по статусу из n8n
                await self._update_topic_icon(topic_id, ai_enabled)
            
            # Отправляем сообщение
            await self.bot.send_message(
                chat_id=self.settings.TELEGRAM_GROUP_ID,
                message_thread_id=topic_id,
                text=f"👤 Пользователь: {message}",
                parse_mode=ParseMode.HTML
            )
            
            return True
            
        except Exception as e:
            print(f"❌ Error sending user message: {e}")
            return False
    
    async def send_ai_response(self, chat_id: str, message: str) -> bool:
        """Отправить ответ AI с кнопкой переключения"""
        try:
            topic_id = await self.db.get_topic_id(chat_id)
            
            if not topic_id:
                print(f"⚠️ Topic not found for chat_id: {chat_id}")
                return False
            
            # Кнопка переключения AI
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="🔄 Переключить AI",
                    callback_data=f"toggle_ai:{chat_id}"
                )]
            ])
            
            await self.bot.send_message(
                chat_id=self.settings.TELEGRAM_GROUP_ID,
                message_thread_id=topic_id,
                text=f"🤖 AI: {message}",
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard
            )
            
            return True
            
        except Exception as e:
            print(f"❌ Error sending AI response: {e}")
            return False
    
    async def start(self):
        """Запуск бота"""
        print("✅ Telegram bot started")
        import asyncio
        self._polling_task = asyncio.create_task(self.dp.start_polling(self.bot))
    
    async def stop(self):
        """Остановка бота"""
        if hasattr(self, '_polling_task'):
            self._polling_task.cancel()
            try:
                await self._polling_task
            except asyncio.CancelledError:
                pass
        await self.bot.session.close()
        print("✅ Telegram bot stopped")