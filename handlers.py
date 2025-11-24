import random
import asyncio
import logging
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError, TelegramAPIError
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from typing import Dict, Set, List
from datetime import datetime
from achievement_checker import achievement_checker
from achievements import get_achievement_full_info, get_achievement_display, ACHIEVEMENTS
from db import db
from keyboards import quiz_options, main_menu, confirmation_keyboard, \
    achievements_keyboard, daily_reward_keyboard, categories_keyboard, difficulty_keyboard, \
    profile_keyboard
from questions import QUESTIONS_BY_CATEGORY, DIFFICULTY_SETTINGS
from daily_rewards import daily_rewards, WEEKLY_REWARDS

router = Router()

# ------------------- Состояние пользователей -------------------
current_question: Dict[int, dict] = {}
asked_questions: Dict[int, Set[str]] = {}  # Изменено на str для хранения question_id
last_message_id: Dict[int, int] = {}
user_stats: Dict[int, Dict] = {}  # user_id -> {"correct": 0, "total": 0, "combo": 0}
user_quiz_settings: Dict[int, Dict] = {}  # user_id -> {"category": "", "difficulty": ""}

logger = logging.getLogger(__name__)


# ------------------- Вспомогательные функции -------------------
def get_question_id(question: dict) -> str:
    """Генерирует уникальный ID для вопроса"""
    return f"{question.get('category', 'unknown')}_{hash(question.get('question', ''))}"


def get_available_questions(user_id: int, category: str, difficulty: str = "random") -> List[dict]:
    """Получает доступные вопросы для пользователя с учетом уже заданных"""
    asked = asked_questions.get(user_id, set())

    # Получаем вопросы для категории
    if category == "random":
        # Объединяем все вопросы из всех категорий
        all_questions = []
        for cat_questions in QUESTIONS_BY_CATEGORY.values():
            all_questions.extend(cat_questions)
        category_questions = all_questions
    else:
        category_questions = QUESTIONS_BY_CATEGORY.get(category, [])

    # Фильтруем по сложности если нужно
    if difficulty != "random":
        category_questions = [q for q in category_questions if q.get("difficulty") == difficulty]

    # Исключаем уже заданные вопросы
    available_questions = [q for q in category_questions if get_question_id(q) not in asked]

    return available_questions


def reset_user_questions_if_needed(user_id: int, category: str, difficulty: str = "random"):
    """Сбрасывает историю вопросов если все доступные вопросы были использованы"""
    available_questions = get_available_questions(user_id, category, difficulty)

    if not available_questions:
        # Сбрасываем историю вопросов для этой категории/сложности
        if user_id in asked_questions:
            # Удаляем только вопросы относящиеся к текущей категории
            if category == "random":
                asked_questions[user_id].clear()
            else:
                # Удаляем только вопросы из текущей категории
                asked_questions[user_id] = {
                    q_id for q_id in asked_questions[user_id]
                    if not q_id.startswith(f"{category}_")
                }
        logger.info("Reset question history for user %d, category: %s", user_id, category)


# ------------------- FSM для профиля -------------------
class ProfileStates(StatesGroup):
    changing_name = State()


class QuizStates(StatesGroup):
    choosing_category = State()
    choosing_difficulty = State()
    playing_quiz = State()


async def show_achievement_unlocked(message: types.Message, achievement_id: str):
    """Показывает уведомление о разблокированном достижении"""
    try:
        achievement_info = get_achievement_full_info(achievement_id)

        unlock_text = (
            f"🎉 *НОВОЕ ДОСТИЖЕНИЕ!*\n\n"
            f"{achievement_info}\n\n"
            f"💫 Поздравляем с разблокировкой!"
        )

        # Отправляем временное сообщение
        msg = await message.answer(unlock_text)
        # Удаляем через 5 секунд
        await asyncio.sleep(5)
        await msg.delete()
    except TelegramBadRequest:
        logger.warning("Telegram error showing achievement")
    except TelegramNetworkError:
        logger.warning("Network error showing achievement")
    except asyncio.CancelledError:
        logger.info("Achievement notification cancelled")
    except TelegramAPIError as e:
        logger.error("Telegram API error showing achievement: %s", e)
    except Exception as e:
        logger.error("Unexpected error showing achievement: %s", e)


async def check_and_notify_daily_rewards():
    """Проверяет и уведомляет пользователей о доступных наградах"""
    # TODO: Добавить логику массовых уведомлений


async def show_main_menu(bot, chat_id: int, user_id: int, text: str = None) -> int:
    """Улучшенное главное меню с обработкой ошибок"""
    try:
        if text is None:
            user = await db.get_user(user_id)
            achievements_count = await db.get_achievements_count(user_id)
            total_achievements = len(ACHIEVEMENTS)

            # Проверяем доступность награды
            reward_info = await daily_rewards.get_reward_info(user_id)
            reward_indicator = " 🎁" if reward_info["can_claim"] else ""

            text = (
                f"👋 Добро пожаловать в викторину!{reward_indicator}\n\n"
                f"🎯 Твоя статистика:\n"
                f"• 🏅 Уровень: {user.get('level', 1)}\n"
                f"• ✨ XP: {user.get('xp', 0)}\n"
                f"• 🔥 Комбо: {user.get('max_combo', 0)}\n"
                f"• 🏆 Достижения: {achievements_count}/{total_achievements}\n"
                f"• 📅 Стрик наград: {reward_info['streak']} дней\n\n"
                f"Выбери действие ниже 👇"
            )

        # Всегда отправляем новое сообщение для главного меню
        msg = await bot.send_message(
            chat_id,
            text,
            reply_markup=main_menu()
        )
        last_message_id[user_id] = msg.message_id
        return msg.message_id

    except Exception as e:
        logger.error("Error showing main menu for user %d: %s", user_id, e)
        # Пытаемся отправить упрощенное меню
        try:
            msg = await bot.send_message(
                chat_id,
                "👋 Добро пожаловать в викторину!\n\nВыбери действие:",
                reply_markup=main_menu()
            )
            last_message_id[user_id] = msg.message_id
            return msg.message_id
        except Exception as e2:
            logger.error("Critical error showing main menu: %s", e2)
            return 0


async def handle_daily_reward(callback: types.CallbackQuery):
    """Обработчик ежедневных наград"""
    user_id = callback.from_user.id
    reward_info = await daily_rewards.get_reward_info(user_id)

    if reward_info["can_claim"]:
        # Выдаем награду
        result = await daily_rewards.claim_reward(user_id)

        if result["success"]:
            # Красивое сообщение о награде
            day_of_week = datetime.now().weekday()
            day_reward = WEEKLY_REWARDS.get(day_of_week, {"xp": 50, "name": "Сегодня", "emoji": "🎁"})

            reward_text = (
                f"{day_reward['emoji']} *Ежедневная награда!*\n\n"
                f"📅 {day_reward['name']}\n"
                f"💫 +{result['xp_reward']} XP\n"
                f"📊 Из них:\n"
                f"   • Базовая награда: {result['base_xp']} XP\n"
                f"   • Бонус за стрик: +{result['streak_bonus']}%\n"
                f"🔥 Текущий стрик: {result['new_streak']} дней\n\n"
                f"✨ Всего XP: {result['new_xp']}\n"
                f"🏅 Уровень: {result['new_level']}\n\n"
                f"Возвращайся завтра за новой наградой! 🗓️"
            )
        else:
            reward_text = result["message"]
    else:
        # Показываем, когда можно получить следующую награду
        reward_text = (
            f"⏳ *Ежедневная награда*\n\n"
            f"🎁 Сегодня ты уже получал награду!\n"
            f"🔥 Текущий стрик: {reward_info['streak']} дней\n"
            f"⏰ Следующая награда через: {reward_info['hours_until']}ч {reward_info['minutes_until']}м\n\n"
            f"Не пропускай дни для увеличения бонуса! 💫"
        )

    await callback.message.edit_text(
        text=reward_text,
        reply_markup=daily_reward_keyboard(reward_info["can_claim"])
    )


@router.callback_query(F.data == "claim_daily")
async def claim_daily_callback(callback: types.CallbackQuery):
    """Обработчик кнопки получения награды"""
    await handle_daily_reward(callback)


# ------------------- Команды бота -------------------

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    await db.get_user(user_id, message.from_user.username or "")

    # Инициализация статистики
    user_stats[user_id] = {"correct": 0, "total": 0, "combo": 0, "max_combo": 0}

    welcome_text = (
        f"🎉 Привет, {message.from_user.first_name or 'Игрок'}!\n\n"
        f"Я бот-викторина с системой уровней и рейтинга.\n"
        f"Отвечай на вопросы, зарабатывай XP и соревнуйся с другими!"
    )

    last_message_id[user_id] = await show_main_menu(
        message.bot,
        message.chat.id,
        user_id,
        welcome_text
    )


@router.message(Command("menu"))
async def cmd_menu(message: types.Message):
    """Команда для открытия главного меню"""
    user_id = message.from_user.id
    await db.get_user(user_id, message.from_user.username or "")

    # Инициализация статистики если нужно
    if user_id not in user_stats:
        user_stats[user_id] = {"correct": 0, "total": 0, "combo": 0, "max_combo": 0}

    await show_main_menu(message.bot, message.chat.id, user_id)


@router.message(Command("quiz"))
async def cmd_quiz_direct(message: types.Message):
    """Прямой запуск квиза через команду"""
    user_id = message.from_user.id

    # Инициализация пользователя если нужно
    await db.get_user(user_id, message.from_user.username or "")

    # Используем настройки по умолчанию если нет сохраненных
    if user_id not in user_quiz_settings:
        user_quiz_settings[user_id] = {
            "category": "random",
            "difficulty": "random"
        }

    await cmd_quiz(message, user_id)


@router.message(Command("reset"))
async def cmd_reset(message: types.Message):
    """Команда для сброса прогресса"""
    user_id = message.from_user.id

    await message.answer(
        "⚠️ Ты действительно хочешь сбросить весь прогресс?\n\n"
        "❌ Это действие нельзя отменить!\n"
        "Будут удалены:\n"
        "• Весь XP и уровни\n"
        "• Вся статистика\n"
        "• Все достижения\n"
        "• История ответов",
        reply_markup=confirmation_keyboard(
            confirm_data=f"confirm_reset:yes:{user_id}",
            cancel_data=f"confirm_reset:no:{user_id}"
        )
    )

@router.message(Command("help"))
async def cmd_help(message: types.Message):
    """Расширенная справка"""
    text = (
        f"ℹ️ *Помощь по боту викторине*\n\n"
        f"*Основные команды:*\n"
        f"• /start - запустить бота\n"
        f"• /menu - главное меню\n"
        f"• /quiz - начать викторину\n"
        f"• /stats - статистика\n"
        f"• /duels - режим дуэлей\n"
        f"• /reset - сброс прогресса\n"
        f"• /help - эта справка\n\n"
        f"*Быстрые команды:*\n"
        f"• 'квиз', 'играть' - начать викторину\n"
        f"• 'профиль' - личный кабинет\n"
        f"• 'топ' - таблица лидеров\n"
        f"• 'дуэли' - режим дуэлей\n\n"
        f"*Система наград:*\n"
        f"• 🎁 Ежедневные награды\n"
        f"• 🏆 Достижения\n"
        f"• 🔥 Комбо-система\n"
        f"• 🏅 Уровни и XP\n\n"
        f"*Режимы игры:*\n"
        f"• 📚 Викторина (одиночная)\n"
        f"• ⚔️ Дуэли (мультиплеер)\n"
        f"• 🎯 Разные категории\n"
        f"• 🎲 Разная сложность"
    )

    await message.answer(text, parse_mode="Markdown")


# ------------------- Текстовые команды -------------------

@router.message(F.text.in_(["🎮 Начать квиз", "квиз", "играть", "старт"]))
async def text_start_quiz(message: types.Message):
    """Текстовая команда для начала квиза"""
    await cmd_quiz_direct(message)


@router.message(F.text.in_(["👤 Профиль", "профиль", "стата"]))
async def text_profile(message: types.Message):
    """Текстовая команда для профиля"""
    await handle_menu_action_types(message, "profile")


@router.message(F.text.in_(["🏆 Топ", "топ", "лидеры"]))
async def text_top(message: types.Message):
    """Текстовая команда для топа"""
    await handle_menu_action_types(message, "top")


@router.message(F.text.in_(["📊 Статистика", "статистика"]))
async def text_stats(message: types.Message):
    """Текстовая команда для статистики"""
    await cmd_stats(message)


@router.message(F.text.in_(["⚔️ Дуэли", "дуэли"]))
async def text_duels(message: types.Message):
    """Текстовая команда для дуэлей"""
    await duels_command(message)


async def handle_menu_action_types(message: types.Message, action: str):
    """Обработчик текстовых команд меню"""
    user_id = message.from_user.id

    if action == "profile":
        try:
            user = await db.get_user(user_id)
            stats = user_stats.get(user_id, {"correct": 0, "total": 0, "max_combo": 0})
            accuracy = (stats["correct"] / stats["total"] * 100) if stats["total"] > 0 else 0
            favorite_category = await db.get_user_favorite_category(user_id)

            text = (
                f"👤 Личный кабинет\n\n"
                f"📊 Общая статистика:\n"
                f"• 🧍 Ник: {user.get('username') or '—'}\n"
                f"• 🏅 Уровень: {user.get('level', 1)}\n"
                f"• ✨ XP: {user.get('xp', 0)}\n"
                f"• ✅ Правильных ответов: {stats['correct']}\n"
                f"• 📈 Точность: {accuracy:.1f}%\n"
                f"• 🔥 Макс. комбо: {stats['max_combo']}\n"
                f"• 📚 Любимая категория: {favorite_category}\n"
            )

            await message.answer(text, reply_markup=profile_keyboard())
        except Exception as e:
            logger.error("Error loading profile: %s", e)
            await message.answer("❌ Ошибка загрузки профиля. Попробуйте позже.")

    elif action == "top":
        try:
            top_users = await db.get_top_users(10)
            if not top_users:
                text = "🏆 Топ игроков\n\n📊 Пока никто не играл. Будь первым!"
            else:
                lines = []
                medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
                for i, u in enumerate(top_users):
                    medal = medals[i] if i < len(medals) else f"{i + 1}."
                    username = u.get('username') or 'Аноним'
                    level = u.get('level', 1)
                    xp = u.get('xp', 0)
                    lines.append(f"{medal} {username} - Ур. {level} • {xp} XP")

                text = "🏆 Топ 10 игроков\n\n" + "\n".join(lines)

            await message.answer(text)
        except Exception as e:
            logger.error("Error loading top users: %s", e)
            await message.answer("❌ Ошибка загрузки топа игроков. Попробуйте позже.")


# ------------------- Меню категорий -------------------
@router.callback_query(F.data == "menu:categories")
async def categories_menu(callback: types.CallbackQuery):
    """Меню выбора категорий"""

    text = (
        "📚 *Выбери категорию вопросов*\n\n"
        "Каждая категория имеет свои особенности:\n"
        "• 📜 История - исторические события и личности\n"
        "• 🔬 Наука - открытия и факты из мира науки\n"
        "• 🎨 Искусство - живопись, музыка, литература\n"
        "• 🌍 География - страны, города, природа\n"
        "• ⚽ Спорт - спортивные события и рекорды\n\n"
        "Выбери категорию или нажми 'Случайная' 🎲"
    )

    await callback.message.edit_text(
        text,
        reply_markup=categories_keyboard(),
        parse_mode="Markdown"
    )


@router.callback_query(F.data.startswith("category:"))
async def select_category(callback: types.CallbackQuery):
    """Обработчик выбора категории"""
    user_id = callback.from_user.id
    category = callback.data.split(":")[1]

    # Сохраняем выбор категории
    if user_id not in user_quiz_settings:
        user_quiz_settings[user_id] = {}
    user_quiz_settings[user_id]["category"] = category

    category_names = {
        "история": "📜 История",
        "наука": "🔬 Наука",
        "искусство": "🎨 Искусство",
        "география": "🌍 География",
        "спорт": "⚽ Спорт",
        "random": "🎲 Случайная"
    }

    category_name = category_names.get(category, "Категория")

    text = (
        f"✅ Выбрана категория: *{category_name}*\n\n"
        f"Теперь выбери уровень сложности:\n"
        f"• 🟢 Легкий - 15 XP за вопрос\n"
        f"• 🟡 Средний - 25 XP за вопрос\n"
        f"• 🔴 Сложный - 40 XP за вопрос\n"
        f"• 🎲 Любая - случайная сложность\n\n"
        f"*Сложность влияет на количество получаемого опыта!*"
    )

    await callback.message.edit_text(
        text,
        reply_markup=difficulty_keyboard(),
        parse_mode="Markdown"
    )


@router.callback_query(F.data.startswith("difficulty:"))
async def select_difficulty(callback: types.CallbackQuery):
    """Обработчик выбора сложности"""
    user_id = callback.from_user.id
    difficulty = callback.data.split(":")[1]

    # Сохраняем выбор сложности
    if user_id in user_quiz_settings:
        user_quiz_settings[user_id]["difficulty"] = difficulty

    category = user_quiz_settings.get(user_id, {}).get("category", "random")

    category_names = {
        "история": "📜 История",
        "наука": "🔬 Наука",
        "искусство": "🎨 Искусство",
        "география": "🌍 География",
        "спорт": "⚽ Спорт",
        "random": "🎲 Случайная"
    }

    difficulty_names = {
        "легкий": "🟢 Легкий",
        "средний": "🟡 Средний",
        "сложный": "🔴 Сложный",
        "random": "🎲 Любая"
    }

    category_name = category_names.get(category, "Категория")
    difficulty_name = difficulty_names.get(difficulty, "Сложность")

    text = (
        f"🎯 *Настройки викторины*\n\n"
        f"• 📚 Категория: {category_name}\n"
        f"• 🎯 Сложность: {difficulty_name}\n\n"
        f"Готов начать? Нажимай кнопку ниже! 👇"
    )

    keyboard = InlineKeyboardBuilder()
    keyboard.row(
        types.InlineKeyboardButton(
            text="🎮 Начать викторину",
            callback_data=f"start_quiz:{category}:{difficulty}"
        )
    )
    keyboard.row(
        types.InlineKeyboardButton(text="🔙 Изменить категорию", callback_data="menu:categories")
    )

    await callback.message.edit_text(
        text,
        reply_markup=keyboard.as_markup(),
        parse_mode="Markdown"
    )


@router.callback_query(F.data.startswith("start_quiz:"))
async def start_quiz_with_settings(callback: types.CallbackQuery):
    """Запуск квиза с выбранными настройками"""
    user_id = callback.from_user.id
    _, category, difficulty = callback.data.split(":")

    # Сохраняем настройки
    user_quiz_settings[user_id] = {
        "category": category,
        "difficulty": difficulty
    }

    # Удаляем сообщение с настройками
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass

    # Запускаем квиз
    await cmd_quiz(callback.message, user_id)


# ------------------- Улучшенный квиз -------------------
async def cmd_quiz(message: types.Message, user_id: int):
    """Запускает квиз с учетом выбранных настроек"""
    try:
        # Получаем настройки пользователя
        settings = user_quiz_settings.get(user_id, {})
        category = settings.get("category", "random")
        difficulty = settings.get("difficulty", "random")

        # Проверяем и сбрасываем историю вопросов если нужно
        reset_user_questions_if_needed(user_id, category, difficulty)

        # Получаем доступные вопросы
        available_questions = get_available_questions(user_id, category, difficulty)

        if not available_questions:
            await message.answer("❌ В выбранной категории пока нет вопросов")
            return

        # Выбираем случайный вопрос
        question = random.choice(available_questions)
        question_id = get_question_id(question)

        # Сохраняем информацию о заданном вопросе
        if user_id not in asked_questions:
            asked_questions[user_id] = set()
        asked_questions[user_id].add(question_id)
        current_question[user_id] = question

        # Добавляем информацию о категории и сложности
        question_category = category
        question_difficulty = question.get("difficulty", "неизвестно")
        difficulty_emoji = DIFFICULTY_SETTINGS.get(question_difficulty, {}).get("emoji", "⚪")

        # Формируем текст вопроса
        progress = f"📊 Категория: {question_category} {difficulty_emoji}"

        question_text = f"{progress}\n\n{question.get('question', '❌ Вопрос пуст')}"
        options = question.get("options", [])

        if not options:
            await message.answer("❌ Ошибка: вопрос не имеет вариантов ответа")
            return

        # Отправляем вопрос
        try:
            msg = await message.answer(
                question_text,
                reply_markup=quiz_options(options)
            )
            last_message_id[user_id] = msg.message_id
        except (TelegramBadRequest, TelegramNetworkError) as e:
            logger.error("Error sending quiz question: %s", e)
            await message.answer("❌ Ошибка при отправке вопроса. Попробуйте еще раз.")

    except (ValueError, KeyError, IndexError) as e:
        logger.error("Data error in cmd_quiz: %s", e)
        await message.answer("❌ Ошибка в данных вопросов. Попробуйте другую категорию.")
    except TelegramAPIError as e:
        logger.error("Telegram API error in cmd_quiz: %s", e)
        await message.answer("❌ Ошибка связи с Telegram. Попробуйте еще раз.")
    except Exception as e:
        logger.error("Unexpected error in cmd_quiz: %s", e)
        await message.answer("❌ Произошла непредвиденная ошибка. Попробуйте еще раз.")


# ------------------- Улучшенная обработка ответов -------------------
async def handle_quiz_answer(callback: types.CallbackQuery, chosen: str):
    user_id = callback.from_user.id
    await callback.answer()

    if user_id not in current_question:
        await callback.answer("❌ Этот вопрос устарел или уже был обработан", show_alert=True)
        return

    q = current_question.pop(user_id)
    stats = user_stats.setdefault(user_id, {"correct": 0, "total": 0, "combo": 0, "max_combo": 0})
    stats["total"] += 1

    try:
        # Получаем настройки для расчета XP
        question_difficulty = q.get("difficulty", "легкий")
        base_xp = DIFFICULTY_SETTINGS.get(question_difficulty, {}).get("xp", 20)

        # Определяем категорию вопроса
        settings = user_quiz_settings.get(user_id, {})
        question_category = settings.get("category", "random")

        # ДЕБАГ: Логируем данные вопроса и ответа
        logger.info(f"User {user_id} selected option: '{chosen}'")
        logger.info(f"Correct answer should be: '{q.get('answer')}'")
        logger.info(f"Question options: {q.get('options', [])}")

        # ВАЖНО: Исправляем получение ответа пользователя
        # chosen - это индекс выбранного варианта (0, 1, 2, 3)
        options = q.get("options", [])

        if not options:
            await callback.answer("❌ Ошибка: вопрос не имеет вариантов ответа", show_alert=True)
            return

        # Преобразуем chosen в индекс
        try:
            chosen_index = int(chosen)
            if chosen_index < 0 or chosen_index >= len(options):
                raise ValueError("Index out of range")
        except (ValueError, IndexError):
            logger.error(f"Invalid chosen index: {chosen} for options: {options}")
            await callback.answer("❌ Ошибка: неверный вариант ответа", show_alert=True)
            return

        # Получаем текст выбранного ответа
        user_answer_text = options[chosen_index]
        correct_answer_text = q.get("answer", "")

        logger.info(f"User selected text: '{user_answer_text}'")
        logger.info(f"Correct answer text: '{correct_answer_text}'")

        # НОРМАЛИЗАЦИЯ ОТВЕТОВ ДЛЯ ПРАВИЛЬНОГО СРАВНЕНИЯ
        def normalize_answer(text: str) -> str:
            """Нормализует текст для сравнения"""
            import string
            text = text.lower().strip()
            text = text.translate(str.maketrans('', '', string.punctuation))
            return text

        normalized_correct = normalize_answer(correct_answer_text)
        normalized_user = normalize_answer(user_answer_text)

        # Сравниваем нормализованные ответы
        is_correct = normalized_user == normalized_correct

        logger.info(f"Answer comparison: user='{user_answer_text}' vs correct='{correct_answer_text}' -> {is_correct}")
        logger.info(f"Normalized: user='{normalized_user}' vs correct='{normalized_correct}' -> {is_correct}")

        if is_correct:
            # Правильный ответ
            stats["correct"] += 1
            stats["combo"] += 1
            stats["max_combo"] = max(stats["max_combo"], stats["combo"])

            xp_reward = base_xp + (stats["combo"] // 3) * 5  # Бонус за комбо
            new_xp, new_level = await db.add_xp(user_id, xp_reward)

            # Обновляем статистику по категории
            await db.update_user_category_stats(user_id, question_category, True)

            # Проверяем достижения
            unlocked_achievements = await achievement_checker.check_achievements(
                user_id=user_id,
                event_type="answer",
                is_correct=True,
                current_combo=stats["combo"],
                user_xp=new_xp,
                total_answers=stats["total"]
            )

            # Показываем уведомления о достижениях
            for achievement_id in unlocked_achievements:
                await show_achievement_unlocked(callback.message, achievement_id)
                achievement_xp = ACHIEVEMENTS[achievement_id]["xp_reward"]
                await db.add_xp(user_id, achievement_xp)

            combo_bonus = ""
            if stats["combo"] >= 3:
                combo_bonus = f"\n🔥 Комbo: {stats['combo']} +{xp_reward - base_xp} XP"

            result_text = (
                f"✅ Правильно!\n"
                f"📝 Ответ: {correct_answer_text}\n"
                f"💫 +{xp_reward} XP{combo_bonus}\n"
                f"✨ Всего XP: {new_xp}\n"
                f"🏅 Уровень: {new_level}"
            )
        else:
            # Неправильный ответ
            stats["combo"] = 0
            accuracy = (stats["correct"] / stats["total"] * 100) if stats["total"] > 0 else 0

            # Обновляем статистику по категории
            await db.update_user_category_stats(user_id, question_category, False)

            # Проверяем достижения
            await achievement_checker.check_achievements(
                user_id=user_id,
                event_type="answer",
                is_correct=False,
                current_combo=0,
                user_xp=await db.get_user_xp(user_id),
                total_answers=stats["total"]
            )

            result_text = (
                f"❌ Неправильно\n"
                f"📝 Правильный ответ: {correct_answer_text}\n"
                f"💭 Твой ответ: {user_answer_text}\n\n"
                f"📊 Твоя статистика:\n"
                f"• ✅ Правильных: {stats['correct']}/{stats['total']}\n"
                f"• 📈 Точность: {accuracy:.1f}%"
            )

        # Обновляем сообщение
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
            await callback.message.edit_text(text=result_text)
        except (TelegramBadRequest, TelegramNetworkError) as e:
            logger.warning("Error editing message, sending new one: %s", e)
            msg = await callback.message.answer(text=result_text)
            last_message_id[user_id] = msg.message_id

        await asyncio.sleep(2)
        await cmd_quiz(callback.message, user_id)

    except (ValueError, KeyError) as e:
        logger.error("Data error in handle_quiz_answer: %s", e)
        await callback.answer("❌ Ошибка в данных вопроса", show_alert=True)
    except TelegramAPIError as e:
        logger.error("Telegram API error in handle_quiz_answer: %s", e)
        await callback.answer("❌ Ошибка связи с Telegram", show_alert=True)
    except Exception as e:
        logger.error("Unexpected error in handle_quiz_answer: %s", e)
        await callback.answer("❌ Произошла непредвиденная ошибка", show_alert=True)

# ------------------- Улучшенное меню -------------------
async def handle_menu_action(callback: types.CallbackQuery, action: str):
    user_id = callback.from_user.id
    await callback.answer()

    # ------------------- Главное меню -------------------
    if action == "main":
        current_question.pop(user_id, None)

        # Пытаемся удалить предыдущее сообщение с квизом, если есть
        try:
            if last_message_id.get(user_id):
                await callback.bot.delete_message(
                    chat_id=callback.message.chat.id,
                    message_id=last_message_id[user_id]
                )
        except TelegramBadRequest:
            pass  # Игнорируем ошибки удаления

        msg_id = await show_main_menu(callback.message.bot, callback.message.chat.id, user_id)
        last_message_id[user_id] = msg_id
        return

    # ------------------- Начать квиз -------------------
    if action == "start_quiz":
        # Удаляем сообщение с главным меню перед началом квиза
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass  # Игнорируем ошибки удаления

        await cmd_quiz(callback.message, user_id)
        return

    # ------------------- Профиль -------------------
    elif action == "profile":
        try:
            user = await db.get_user(user_id)
            stats = user_stats.get(user_id, {"correct": 0, "total": 0, "max_combo": 0})
            accuracy = (stats["correct"] / stats["total"] * 100) if stats["total"] > 0 else 0

            # Получаем статистику по категориям
            category_stats = await db.get_user_category_stats(user_id)
            favorite_category = await db.get_user_favorite_category(user_id)

            text = (
                f"👤 Личный кабинет\n\n"
                f"📊 Общая статистика:\n"
                f"• 🧍 Ник: {user.get('username') or '—'}\n"
                f"• 🏅 Уровень: {user.get('level', 1)}\n"
                f"• ✨ XP: {user.get('xp', 0)}\n"
                f"• ✅ Правильных ответов: {stats['correct']}\n"
                f"• 📈 Точность: {accuracy:.1f}%\n"
                f"• 🔥 Макс. комбо: {stats['max_combo']}\n"
                f"• 📚 Любимая категория: {favorite_category}\n\n"
            )

            # Добавляем статистику по категориям если есть
            if category_stats:
                text += "📈 Статистика по категориям:\n"
                for category, cat_stats in list(category_stats.items())[:3]:  # Показываем топ-3
                    text += f"• {category}: {cat_stats['accuracy']}% ({cat_stats['correct_answers']}/{cat_stats['total_answers']})\n"

            await callback.message.edit_text(
                text=text,
                reply_markup=profile_keyboard()
            )
        except Exception as e:
            logger.error("Error loading profile: %s", e)
            await callback.message.edit_text(
                "❌ Ошибка загрузки профиля. Попробуйте позже.",
                reply_markup=main_menu()
            )
        return

    # ------------------- Категории -------------------
    elif action == "categories":
        await categories_menu(callback)
        return

    # ------------------- Топ игроков -------------------
    elif action == "top":
        try:
            top_users = await db.get_top_users(10)
            if not top_users:
                text = "🏆 Топ игроков\n\n📊 Пока никто не играл. Будь первым!"
            else:
                lines = []
                medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
                for i, u in enumerate(top_users):
                    medal = medals[i] if i < len(medals) else f"{i + 1}."
                    username = u.get('username') or 'Аноним'
                    level = u.get('level', 1)
                    xp = u.get('xp', 0)
                    lines.append(f"{medal} {username} - Ур. {level} • {xp} XP")

                text = "🏆 Топ 10 игроков\n\n" + "\n".join(lines)

            await callback.message.edit_text(
                text=text,
                reply_markup=main_menu()
            )
        except Exception as e:
            logger.error("Error loading top users: %s", e)
            await callback.message.edit_text(
                "❌ Ошибка загрузки топа игроков. Попробуйте позже.",
                reply_markup=main_menu()
            )
        return

    # ------------------- Статистика -------------------
    elif action == "stats":
        try:
            user = await db.get_user(user_id)
            stats = user_stats.get(user_id, {"correct": 0, "total": 0, "max_combo": 0})
            accuracy = (stats["correct"] / stats["total"] * 100) if stats["total"] > 0 else 0

            text = (
                f"📊 Детальная статистика\n\n"
                f"• 🎯 Всего ответов: {stats['total']}\n"
                f"• ✅ Правильных: {stats['correct']}\n"
                f"• ❌ Неправильных: {stats['total'] - stats['correct']}\n"
                f"• 📈 Точность: {accuracy:.1f}%\n"
                f"• 🔥 Макс. комбо: {stats['max_combo']}\n"
                f"• 🏅 Уровень: {user.get('level', 1)}\n"
                f"• ✨ XP: {user.get('xp', 0)}"
            )

            await callback.message.edit_text(
                text=text,
                reply_markup=main_menu()
            )
        except Exception as e:
            logger.error("Error loading stats: %s", e)
            await callback.message.edit_text(
                "❌ Ошибка загрузки статистики. Попробуйте позже.",
                reply_markup=main_menu()
            )
        return

    # ------------------- Помощь -------------------
    elif action == "help":
        text = (
            f"ℹ️ Помощь по боту\n\n"
            f"Как играть:\n"
            f"• Нажми 🎮 Начать квиз\n"
            f"• Выбирай правильные ответы\n"
            f"• Зарабатывай XP и повышай уровень\n\n"
            f"Система наград:\n"
            f"• ✅ Правильный ответ: 20 XP\n"
            f"• 🔥 Комбо: +5 XP за каждые 3 ответа подряд\n"
            f"• 🏅 Уровень: растет с увеличением XP\n\n"
            f"Команды:\n"
            f"/start - перезапустить бота\n"
            f"/stats - показать статистику"
        )

        await callback.message.edit_text(
            text=text,
            reply_markup=main_menu()
        )
        return

    # ------------------- Настройки -------------------
    elif action == "settings":
        text = (
            f"⚙️ Настройки\n\n"
            f"🔔 Уведомления: Включены\n"
            f"🎨 Тема: Светлая\n"
            f"📱 Вибрация: Выключена\n\n"
            f"В разработке:\n"
            f"• Смена темы\n• Настройка уведомлений\n• Выбор сложности"
        )
        await callback.message.edit_text(
            text=text,
            reply_markup=main_menu()
        )
        return

    # ------------------- Достижения -------------------
    elif action == "achievements":
        try:
            achievements = await db.get_user_achievements(user_id)
            total_achievements = len(ACHIEVEMENTS)
            achievements_count = await db.get_achievements_count(user_id)

            if not achievements:
                text = (
                    "🏆 Твои достижения\n\n"
                    "📭 У тебя пока нет достижений\n\n"
                    f"🎯 Доступно для получения: {total_achievements} достижений\n"
                    "💫 Играй в викторину и открывай новые!"
                )
            else:
                # Показываем список достижений
                achievements_list = []
                for i, ach in enumerate(achievements, 1):
                    ach_display = get_achievement_display(ach['achievement_id'])
                    achievements_list.append(f"{i}. {ach_display}")

                text = (
                    f"🏆 Твои достижения\n\n"
                    f"📊 Получено: {achievements_count}/{total_achievements}\n\n"
                    f"{chr(10).join(achievements_list)}"
                )

            await callback.message.edit_text(
                text=text,
                reply_markup=achievements_keyboard()
            )
        except Exception as e:
            logger.error("Error loading achievements: %s", e)
            await callback.message.edit_text(
                "❌ Ошибка загрузки достижений. Попробуйте позже.",
                reply_markup=main_menu()
            )
        return

    # ------------------- Ежедневные награды -------------------
    elif action == "daily_reward":
        await handle_daily_reward(callback)
        return
    elif action == "duels":
        # Перенаправляем в обработчике дуэлей из duels.py
        from duels import handle_duels_menu
        await handle_duels_menu(callback)
        return


# ------------------- Команда /stats -------------------
@router.message(Command("stats"))
async def cmd_stats(message: types.Message):
    user_id = message.from_user.id
    try:
        user = await db.get_user(user_id)
        stats = user_stats.get(user_id, {"correct": 0, "total": 0, "max_combo": 0})
        accuracy = (stats["correct"] / stats["total"] * 100) if stats["total"] > 0 else 0

        text = (
            f"📊 Детальная статистика\n\n"
            f"• 🎯 Всего ответов: {stats['total']}\n"
            f"• ✅ Правильных: {stats['correct']}\n"
            f"• ❌ Неправильных: {stats['total'] - stats['correct']}\n"
            f"• 📈 Точность: {accuracy:.1f}%\n"
            f"• 🔥 Макс. комбо: {stats['max_combo']}\n"
            f"• 🏅 Уровень: {user.get('level', 1)}\n"
            f"• ✨ XP: {user.get('xp', 0)}"
        )

        await message.answer(
            text,
            reply_markup=main_menu()
        )
    except Exception as e:
        logger.error("Error in /stats command: %s", e)
        await message.answer("❌ Ошибка загрузки статистики. Попробуйте позже.")


# ------------------- Обработчики профиля -------------------
async def handle_profile_actions(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    action = callback.data.split(":", 1)[1]

    if action == "change_name":
        await callback.answer("✏️ Введи новый ник одним сообщением", show_alert=True)
        await state.set_state(ProfileStates.changing_name)
        return

    elif action == "reset_progress":
        await callback.message.edit_text(
            "⚠️ Ты действительно хочешь сбросить весь прогресс?\n\n"
            "❌ Это действие нельзя отменить!",
            reply_markup=confirmation_keyboard(
                confirm_data="confirm_reset:yes",
                cancel_data="confirm_reset:no"
            )
        )


async def handle_confirm_reset(callback: types.CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    choice = callback.data.split(":", 1)[1]

    if choice == "yes":
        try:
            await db.reset_progress(user_id)
            user_stats[user_id] = {"correct": 0, "total": 0, "combo": 0, "max_combo": 0}
            asked_questions.pop(user_id, None)
            current_question.pop(user_id, None)
            await callback.answer("🔄 Прогресс сброшен!", show_alert=True)
            await show_main_menu(callback.message.bot, callback.message.chat.id, user_id)
        except Exception as e:
            logger.error("Error resetting progress: %s", e)
            await callback.answer("❌ Ошибка при сбросе прогресса", show_alert=True)
    else:
        await callback.answer("❌ Сброс отменён", show_alert=True)
        await handle_menu_action(callback, "profile")


@router.message(ProfileStates.changing_name)
async def change_name(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    new_name = message.text.strip()

    if not new_name:
        await message.answer("❌ Имя не может быть пустым")
        return

    if len(new_name) > 32:
        await message.answer("❌ Имя слишком длинное (макс. 32 символа)")
        return

    # Удаляем сообщение с вводом имени
    try:
        await message.delete()
    except TelegramBadRequest:
        # Сообщение уже удалено или недоступно
        pass
    except TelegramAPIError as e:
        logger.error("Telegram API error deleting message: %s", e)
    except Exception as e:
        logger.error("Unexpected error deleting message: %s", e)

    try:
        await db.update_username(user_id, new_name)
        await state.clear()

        # Показываем главное меню с информацией об обновлении ника
        user = await db.get_user(user_id)
        achievements_count = await db.get_achievements_count(user_id)
        total_achievements = len(ACHIEVEMENTS)

        menu_text = (
            f"✅ Ник успешно обновлён на: {new_name}\n\n"
            f"👋 Добро пожаловать в викторину!\n\n"
            f"🎯 Твоя статистика:\n"
            f"• 🏅 Уровень: {user.get('level', 1)}\n"
            f"• ✨ XP: {user.get('xp', 0)}\n"
            f"• 🔥 Комбо: {user.get('max_combo', 0)}\n"
            f"• 🏆 Достижения: {achievements_count}/{total_achievements}\n\n"
            f"Выбери действие ниже 👇"
        )

        await show_main_menu(message.bot, message.chat.id, user_id, menu_text)
    except Exception as e:
        logger.error("Error updating username: %s", e)
        await message.answer("❌ Ошибка при обновлении ника. Попробуйте позже.")


# ------------------- Регистрация колбэков -------------------
@router.callback_query(F.data.startswith("menu:"))
async def menu_callback(callback: types.CallbackQuery):
    action = callback.data.split(":", 1)[1]
    await handle_menu_action(callback, action)


@router.callback_query(F.data.startswith("profile:"))
async def profile_callback(callback: types.CallbackQuery, state: FSMContext):
    await handle_profile_actions(callback, state)


@router.callback_query(F.data.startswith("confirm_reset:"))
async def confirm_reset_callback(callback: types.CallbackQuery):
    await handle_confirm_reset(callback)


@router.callback_query(F.data.startswith("answer:"))
async def quiz_answer_callback(callback: types.CallbackQuery):
    chosen = callback.data.split(":", 1)[1]
    await handle_quiz_answer(callback, chosen)


# ------------------- Дуэли -------------------

@router.message(F.text == "/duels")
async def duels_command(message: types.Message):
    """Обработчик команды /duels"""
    from duels import user_duels, active_duels
    from keyboards import duels_main_keyboard

    user_id = message.from_user.id

    # Проверяем, не участвует ли пользователь уже в дуэли
    if user_id in user_duels:
        duel_id = user_duels[user_id]
        if duel_id in active_duels:
            duel = active_duels[duel_id]
            if duel["status"] == "waiting":
                await message.answer("❌ Ты уже в лобби дуэли!")
                return
            elif duel["status"] == "active":
                await message.answer("❌ Ты уже в активной дуэли!")
                return

    text = (
        "⚔️ *Режим Дуэлей*\n\n"
        "Сразитесь с другими игроками в командных битвах!\n\n"
        "🎯 *Форматы:*\n"
        "• 1️⃣ 1 vs 1 - классическая дуэль\n"
        "• 2️⃣ 2 vs 2 - командная битва\n"
        "• 3️⃣ 3 vs 3 - тактические сражения\n"
        "• 4️⃣ 4 vs 4 - масштабные баталии\n\n"
        "🏆 *Награды:*\n"
        "• +25 XP за победу\n"
        "• +10 XP за участие\n"
        "• Бонусы за серии побед\n"
        "• Рейтинговые очки\n\n"
        "Выбери режим:"
    )

    await message.answer(
        text,
        reply_markup=duels_main_keyboard(),
        parse_mode="Markdown"
    )


@router.message(F.text == "⚔️ Дуэли")
async def duels_text_command(message: types.Message):
    """Обработчик текстовой команды 'Дуэли'"""
    await duels_command(message)



@router.callback_query(F.data == "no_action")
async def handle_no_action(callback: types.CallbackQuery):
    """Обработчик для кнопок-заглушек"""
    await callback.answer()

@router.callback_query(F.data.startswith("debug:"))
async def debug_callback(callback: types.CallbackQuery):
    """Временный отладочный обработчик"""
    await callback.answer(f"Callback received: {callback.data}", show_alert=True)


@router.message(Command("debug_questions"))
async def debug_questions(message: types.Message):
    """Отладочная команда для проверки структуры вопросов"""

    debug_text = "🔍 Детальная отладка структуры вопросов:\n\n"

    total_questions = 0
    categories_with_issues = []

    for category, questions in QUESTIONS_BY_CATEGORY.items():
        total_questions += len(questions)
        debug_text += f"📚 {category.upper()} ({len(questions)} вопросов):\n"

        if not questions:
            debug_text += "   ❌ НЕТ ВОПРОСОВ\n\n"
            categories_with_issues.append(category)
            continue

        # Проверяем первые 2 вопроса в каждой категории
        for i, question in enumerate(questions[:2]):
            debug_text += f"   Вопрос #{i + 1}:\n"
            debug_text += f"      Текст: {question.get('question', 'N/A')[:60]}...\n"
            debug_text += f"      Ответ: '{question.get('answer', 'N/A')}'\n"

            options = question.get('options', [])
            debug_text += f"      Варианты ({len(options)}): {options}\n"

            # Проверяем, есть ли правильный ответ среди вариантов
            correct_answer = question.get('answer', '')
            if correct_answer and options:
                if correct_answer not in options:
                    debug_text += f"      ⚠️  ОШИБКА: ответ '{correct_answer}' отсутствует в вариантах!\n"
                    categories_with_issues.append(category)

            debug_text += f"      Сложность: {question.get('difficulty', 'N/A')}\n"
            debug_text += f"      ID: {get_question_id(question)}\n\n"

    # Сводка
    debug_text += f"📊 СВОДКА:\n"
    debug_text += f"• Всего категорий: {len(QUESTIONS_BY_CATEGORY)}\n"
    debug_text += f"• Всего вопросов: {total_questions}\n"
    debug_text += f"• Категории с проблемами: {categories_with_issues if categories_with_issues else 'нет'}\n"

    await message.answer(debug_text)
# ------------------- Фоновые задачи -------------------

async def cleanup_old_data():
    """Периодическая очистка устаревших данных"""
    while True:
        await asyncio.sleep(3600)  # Каждый час

        try:
            current_time = datetime.now()
            users_to_clean = []

            # Очищаем пользователей, неактивных более 24 часов
            for user_id, stats in user_stats.items():
                # Проверяем время последней активности (примерная логика)
                if user_id in last_message_id:
                    # Здесь должна быть реальная проверка времени
                    # Например, если у вас есть время последней активности:
                    # last_active = get_last_activity_time(user_id)
                    # if (current_time - last_active).total_seconds() > 86400:  # 24 часа
                    users_to_clean.append(user_id)

            # Логируем время очистки
            logger.info("Cleanup started at %s", current_time.strftime("%Y-%m-%d %H:%M:%S"))

            # Очищаем данные
            for user_id in users_to_clean[:10]:
                asked_questions.pop(user_id, None)
                current_question.pop(user_id, None)
                user_stats.pop(user_id, None)
                user_quiz_settings.pop(user_id, None)

            if users_to_clean:
                logger.info("Cleaned up data for %d inactive users at %s",
                            len(users_to_clean), current_time.strftime("%H:%M:%S"))

        except Exception as e:
            logger.error("Error in cleanup task: %s", e)