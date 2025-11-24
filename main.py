import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
import sys
import os
from typing import Optional
from dotenv import load_dotenv  # ← ДОБАВЛЕНО

# Загружаем переменные из .env файла ← ДОБАВЛЕНО
load_dotenv()  # ← ДОБАВЛЕНО

# Добавляем текущую директорию в путь для импортов
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from handlers import router
from admin_panel import admin_router
from duels import router as duels_router
from db import init_db

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
      #logging.FileHandler('bot.log', encoding='utf-8')
    ]
)

logger = logging.getLogger(__name__)

# Конфигурация бота ← ИЗМЕНЕНО
BOT_TOKEN = os.getenv("BOT_TOKEN")  # ← ИЗМЕНЕНО


async def setup_bot_commands(bot: Bot):
    """Настройка команд бота для меню"""
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
    """Проверка подключения к базе данных"""
    try:
        from db import db
        await db.connect()

        # Простая проверка - попробуем получить количество пользователей
        user_count = await db.get_total_users_count()
        logger.info(f"✅ База данных подключена. Пользователей в базе: {user_count}")

        await db.close()
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к базе данных: {e}")
        return False


async def check_imports():
    """Проверка всех необходимых импортов"""
    imports_to_check = [
        ("handlers", "router"),
        ("admin_panel", "admin_router"),
        ("duels", "router"),
        ("db", "init_db")
    ]

    all_imports_ok = True
    for module_name, attr_name in imports_to_check:
        try:
            module = __import__(module_name)
            if hasattr(module, attr_name):
                logger.info(f"✅ Импорт {module_name}.{attr_name} успешен")
            else:
                logger.error(f"❌ Не найден атрибут {attr_name} в модуле {module_name}")
                all_imports_ok = False
        except ImportError as e:
            logger.error(f"❌ Ошибка импорта {module_name}: {e}")
            all_imports_ok = False

    return all_imports_ok


async def on_startup(bot: Bot):
    """Действия при запуске бота"""
    logger.info("🤖 Бот запущен и готов к работе!")

    # Проверяем импорты
    if not await check_imports():
        logger.error("❌ Не все импорты загружены корректно!")
        return

    # Проверяем базу данных
    if not await check_database_connection():
        logger.error("❌ Проблемы с подключением к базе данных!")
        return

    # Настраиваем команды бота
    await setup_bot_commands(bot)

    # Запускаем задачи очистки
    try:
        from duels import start_background_tasks
        await start_background_tasks()
        logger.info("✅ Фоновые задачи дуэлей запущены")
    except Exception as cleanup_error:
        logger.error(f"❌ Ошибка запуска фоновых задач дуэлей: {cleanup_error}")

    # Отправляем сообщение о запуске (опционально)
    try:
        # Можно отправить сообщение себе или в канал мониторинга
        # await bot.send_message(ваш_chat_id, "✅ Бот успешно запущен!")
        pass
    except Exception as notification_error:
        logger.warning(f"⚠️ Не удалось отправить уведомление о запуске: {notification_error}")

    logger.info("🎉 Все системы запущены и готовы к работе!")


async def on_shutdown(bot: Bot):
    """Действия при выключении бота"""
    logger.info("🛑 Бот выключается...")

    try:
        # Закрываем соединение с базой данных
        from db import db
        await db.close()
        logger.info("✅ Соединение с базой данных закрыто")
    except Exception as db_error:
        logger.error(f"❌ Ошибка при закрытии базы данных: {db_error}")

    # Очищаем ресурсы дуэлей (если функция существует)
    try:
        from duels import shutdown_duels
        await shutdown_duels()
        logger.info("✅ Ресурсы дуэлей очищены")
    except (ImportError, AttributeError):
        # Если модуль или функция не найдены - это нормально
        logger.info("ℹ️ Функция shutdown_duels не найдена, пропускаем очистку дуэлей")
    except Exception as duel_error:
        logger.error(f"❌ Ошибка при очистке дуэлей: {duel_error}")

    # Очищаем ресурсы бота
    try:
        await bot.session.close()  # ← Здесь используется параметр bot
        logger.info("✅ Сессия бота закрыта")
    except Exception as session_error:
        logger.error(f"❌ Ошибка при закрытии сессии: {session_error}")


def count_handlers(router_obj) -> int:
    """Подсчет количества обработчиков в роутере"""
    try:
        handler_count = 0
        # Проверяем различные типы обработчиков
        handler_types = [
            'message', 'callback_query', 'inline_query', 'chosen_inline_result',
            'channel_post', 'edited_message', 'edited_channel_post',
            'shipping_query', 'pre_checkout_query', 'poll', 'poll_answer',
            'my_chat_member', 'chat_member', 'chat_join_request'
        ]

        for handler_type in handler_types:
            handler_manager = getattr(router_obj, handler_type, None)
            if handler_manager and hasattr(handler_manager, 'handlers'):
                handler_count += len(handler_manager.handlers)

        return handler_count
    except Exception as e:
        logger.warning(f"⚠️ Ошибка подсчета обработчиков: {e}")
        return 0


async def main():
    """Основная функция запуска бота"""
    bot: Optional[Bot] = None

    try:
        # Инициализируем базу данных
        logger.info("🔄 Инициализация базы данных...")
        await init_db()
        logger.info("✅ База данных инициализирована")

        # Создаем бота и диспетчер
        bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
        dp = Dispatcher()

        # Регистрируем мидлвари (если есть)
        # dp.update.middleware.register(YourMiddleware())

        # Регистрируем роутеры
        dp.include_router(router)  # Основные обработчики ПЕРВЫМИ
        dp.include_router(duels_router)  # Дуэли ВТОРЫМИ
        dp.include_router(admin_router)  # Админ панель ПОСЛЕДНИМИ

        # Диагностика роутеров
        logger.info("🔍 Проверка роутеров...")

        routers_info = [
            ("Основные обработчики", router),
            ("Админ панель", admin_router),
            ("Система дуэлей", duels_router)
        ]

        total_handlers = 0
        for name, router_obj in routers_info:
            handler_count = count_handlers(router_obj)
            total_handlers += handler_count
            logger.info(f"✅ {name}: {handler_count} обработчиков")

        logger.info(f"📊 Всего обработчиков: {total_handlers}")

        if total_handlers == 0:
            logger.warning("⚠️ Внимание: не зарегистрировано ни одного обработчика!")

        # Настраиваем обработчики запуска и выключения
        dp.startup.register(on_startup)
        dp.shutdown.register(on_shutdown)

        # Запускаем бота
        logger.info("🚀 Запуск бота...")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

    except Exception as main_error:
        logger.critical(f"💥 Критическая ошибка при запуске бота: {main_error}")

        # Пытаемся корректно закрыть ресурсы при ошибке
        try:
            if bot:
                await bot.session.close()
        except Exception as close_error:
            logger.error(f"❌ Ошибка при закрытии ресурсов: {close_error}")

        raise

    finally:
        logger.info("👋 Бот завершил работу")


if __name__ == "__main__":
    try:
        # Проверяем наличие токена ← ИЗМЕНЕНО
        if not BOT_TOKEN:
            logger.critical("❌ Токен бота не найден в переменных окружения!")
            logger.critical("Создайте файл .env с BOT_TOKEN=your_bot_token")
            sys.exit(1)

        if BOT_TOKEN == "your_bot_token_here" or len(BOT_TOKEN) < 10:
            logger.critical("❌ Токен бота не установлен корректно!")
            logger.critical("Проверьте файл .env")
            sys.exit(1)

        # Проверяем версию Python
        if sys.version_info < (3, 8):
            logger.critical("❌ Требуется Python 3.8 или выше!")
            sys.exit(1)

        logger.info("🐍 Запуск на Python %s", sys.version)

        # Запускаем основную функцию
        asyncio.run(main())

    except KeyboardInterrupt:
        logger.info("⏹️ Работа бота прервана пользователем")
        sys.exit(0)

    except Exception as startup_error:
        logger.critical(f"💥 Непредвиденная ошибка: {startup_error}")
        sys.exit(1)