import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties  # ← ВАЖНО!
import sys
import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from handlers import router
from admin_panel import admin_router
from duels import router as duels_router
from db import init_db

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

logger = logging.getLogger(__name__)
BOT_TOKEN = os.getenv("BOT_TOKEN")

async def setup_bot_commands(bot: Bot):
    from aiogram.types import BotCommand, BotCommandScopeDefault
    commands = [
        BotCommand(command="start", description="🚀 Запустить бота"),
        BotCommand(command="menu", description="📱 Главное меню"),
        BotCommand(command="duels", description="⚔️ Дуэли"),
        BotCommand(command="profile", description="👤 Профиль"),
        BotCommand(command="help", description="❓ Помощь"),
        BotCommand(command="stats", description="📊 Статистика")
    ]
    await bot.set_my_commands(commands, BotCommandScopeDefault())

async def check_database_connection():
    try:
        from db import db
        await db.connect()
        user_count = await db.get_total_users_count()
        logger.info(f"✅ База данных подключена. Пользователей: {user_count}")
        await db.close()
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к базе данных: {e}")
        return False

async def on_startup(bot: Bot):
    logger.info("🤖 Бот запущен и готов к работе!")
    if not await check_database_connection():
        logger.error("❌ Проблемы с подключением к базе данных!")
        return
    await setup_bot_commands(bot)
    try:
        from duels import start_background_tasks
        await start_background_tasks()
        logger.info("✅ Фоновые задачи дуэлей запущены")
    except Exception as e:
        logger.error(f"❌ Ошибка запуска фоновых задач: {e}")
    logger.info("🎉 Все системы запущены и готовы к работе!")

async def on_shutdown(bot: Bot):
    logger.info("🛑 Бот выключается...")
    try:
        from db import db
        await db.close()
        logger.info("✅ Соединение с базой данных закрыто")
    except Exception as e:
        logger.error(f"❌ Ошибка при закрытии базы данных: {e}")
    try:
        await bot.session.close()
        logger.info("✅ Сессия бота закрыта")
    except Exception as e:
        logger.error(f"❌ Ошибка при закрытии сессии: {e}")

async def main():
    bot: Optional[Bot] = None
    try:
        logger.info("🔄 Инициализация базы данных...")
        await init_db()
        logger.info("✅ База данных инициализирована")

        # ИСПРАВЛЕННАЯ СТРОКА ↓
        bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        dp = Dispatcher()

        dp.include_router(router)
        dp.include_router(duels_router)
        dp.include_router(admin_router)

        dp.startup.register(on_startup)
        dp.shutdown.register(on_shutdown)

        logger.info("🚀 Запуск бота...")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

    except Exception as main_error:
        logger.critical(f"💥 Критическая ошибка: {main_error}")
        if bot:
            try:
                await bot.session.close()
            except Exception:
                pass
        raise
    finally:
        logger.info("👋 Бот завершил работу")

if __name__ == "__main__":
    if not BOT_TOKEN:
        logger.critical("❌ Токен бота не найден!")
        sys.exit(1)
    if BOT_TOKEN == "your_bot_token_here" or len(BOT_TOKEN) < 10:
        logger.critical("❌ Токен бота не установлен корректно!")
        sys.exit(1)
    
    logger.info("🐍 Запуск на Python %s", sys.version)
    asyncio.run(main())
