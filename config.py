import os

# Безопасное получение токена из переменных окружения
API_TOKEN = os.getenv("BOT_TOKEN")
if not API_TOKEN:
    raise ValueError("❌ BOT_TOKEN не найден в переменных окружения!")

# ID администраторов
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "812857335").split(",")]

# Путь к базе данных
DB_PATH = os.getenv("DB_PATH", "quiz.db")

# Настройки дуэлей
DUEL_MAX_QUESTIONS = int(os.getenv("DUEL_MAX_QUESTIONS", "10"))
DUEL_QUESTION_TIMEOUT = int(os.getenv("DUEL_QUESTION_TIMEOUT", "20"))

# Настройки квиза
QUIZ_BASE_XP = int(os.getenv("QUIZ_BASE_XP", "20"))

# Дополнительные настройки для деплоя
IS_PRODUCTION = os.getenv('RAILWAY_ENVIRONMENT') or os.getenv('RENDER') or os.getenv('DYNO')

# Логирование
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

print(f"✅ Конфигурация загружена. Режим: {'PRODUCTION' if IS_PRODUCTION else 'DEVELOPMENT'}")
print(f"✅ Админы: {ADMIN_IDS}")