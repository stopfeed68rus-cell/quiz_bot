import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from aiogram import Router, types, F
from keyboards import (
    duel_formats_keyboard,
    duel_lobby_keyboard,
    duel_join_menu_keyboard,
    duel_active_list_keyboard,
    duel_quick_menu_keyboard,
    duels_main_keyboard,
    quiz_options
)
from questions import get_random_question


router = Router()
logger = logging.getLogger(__name__)


# ------------------- Конфигурация -------------------
class DuelConfig:
    MAX_QUESTIONS = 10
    QUESTION_TIMEOUT = 20
    MAX_WAIT_TIME = 30
    CLEANUP_INTERVAL = 3600
    STALE_DUEL_TIMEOUT = 3600
    USER_CACHE_TTL = 300

    @classmethod
    def get_max_players(cls, format_type: str) -> int:
        return int(format_type[0]) * 2


# ------------------- Кэш пользователей -------------------
class UserCache:
    def __init__(self):
        self._cache = {}
        self._ttl = DuelConfig.USER_CACHE_TTL

    async def get_user_name(self, bot, user_id: int) -> str:
        if user_id in self._cache:
            name, timestamp = self._cache[user_id]
            if (datetime.now().timestamp() - timestamp) < self._ttl:
                return name

        try:
            user = await bot.get_chat(user_id)
            name = user.first_name or f"Игрок {user_id}"
            self._cache[user_id] = (name, datetime.now().timestamp())
            return name
        except Exception as e:
            logger.debug(f"Не удалось получить имя пользователя {user_id}: {e}")
            return f"Игрок {user_id}"

    def clear_expired(self):
        current_time = datetime.now().timestamp()
        expired_users = [
            user_id for user_id, (_, timestamp) in self._cache.items()
            if (current_time - timestamp) >= self._ttl
        ]
        for user_id in expired_users:
            del self._cache[user_id]


user_cache = UserCache()


# ------------------- Статистика -------------------
class DuelStatistics:
    def __init__(self):
        self.duels_created = 0
        self.duels_completed = 0
        self.players_joined = 0
        self.questions_answered = 0
        self.correct_answers = 0
        self.duels_won = 0
        self.duels_lost = 0
        self.duels_draw = 0

    def increment_duels_created(self):
        self.duels_created += 1

    def increment_duels_completed(self):
        self.duels_completed += 1

    def increment_players_joined(self):
        self.players_joined += 1

    def increment_questions_answered(self):
        self.questions_answered += 1

    def increment_correct_answers(self):
        self.correct_answers += 1

    def increment_duels_won(self):
        self.duels_won += 1

    def increment_duels_lost(self):
        self.duels_lost += 1

    def increment_duels_draw(self):
        self.duels_draw += 1

    def get_stats(self) -> str:
        accuracy = (self.correct_answers / self.questions_answered * 100) if self.questions_answered > 0 else 0
        total_duels = self.duels_won + self.duels_lost + self.duels_draw
        win_rate = (self.duels_won / (total_duels or 1) * 100)

        stats_text = (
            f"📊 *Статистика дуэлей*\n\n"
            f"• 🎮 Создано дуэлей: {self.duels_created}\n"
            f"• ✅ Завершено дуэлей: {self.duels_completed}\n"
            f"• 🏆 Побед: {self.duels_won}\n"
            f"• 💔 Поражений: {self.duels_lost}\n"
            f"• 🤝 Ничьих: {self.duels_draw}\n"
            f"• 📈 Винрейт: {win_rate:.1f}%\n"
            f"• 👥 Присоединилось к дуэлям: {self.players_joined}\n"
            f"• ❓ Ответов на вопросы: {self.questions_answered}\n"
            f"• ✅ Правильных ответов: {self.correct_answers}\n"
            f"• 🎯 Точность: {accuracy:.1f}%\n"
        )

        return stats_text

# Персональная статистика пользователей
user_duel_stats: Dict[int, DuelStatistics] = {}

# Функция для получения статистики пользователя
def get_user_duel_stats(user_id: int) -> DuelStatistics:
    if user_id not in user_duel_stats:
        user_duel_stats[user_id] = DuelStatistics()
    return user_duel_stats[user_id]

# Глобальная статистика (для обратной совместимости)
duel_stats = DuelStatistics()


# ------------------- Структуры данных для дуэлей -------------------
active_duels: Dict[str, Dict] = {}
duel_queues: Dict[str, List[int]] = {
    "1v1": [],
    "2v2": [],
    "3v3": [],
    "4v4": []
}
user_duels: Dict[int, str] = {}
quick_search_tasks: Dict[int, asyncio.Task] = {}
lobby_messages: Dict[str, Dict[int, int]] = {}  # duel_id -> {user_id: message_id}
active_questions: Dict[str, Dict[int, int]] = {}  # duel_id -> {user_id: message_id}

# Блокировки для thread-safe операций
duel_locks: Dict[str, asyncio.Lock] = {}
global_lock = asyncio.Lock()
# ------------------- Вспомогательные функции -------------------
async def safe_delete_message(bot, chat_id: int, message_id: int):
    """Безопасное удаление сообщения"""
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception as e:
        logger.debug(f"Не удалось удалить сообщение {message_id} для {chat_id}: {e}")


def validate_duel_format(format_type: str) -> bool:
    """Проверяет корректность формата дуэли"""
    valid_formats = {"1v1", "2v2", "3v3", "4v4"}
    return format_type in valid_formats


async def get_duel_lock(duel_id: str) -> asyncio.Lock:
    """Получает или создает блокировку для дуэли"""
    async with global_lock:
        if duel_id not in duel_locks:
            duel_locks[duel_id] = asyncio.Lock()
        return duel_locks[duel_id]


async def cleanup_user_resources(user_id: int, bot):
    """Полная очистка ресурсов пользователя"""
    # Выход из всех очередей
    for format_type in duel_queues:
        if user_id in duel_queues[format_type]:
            duel_queues[format_type].remove(user_id)

    # Отмена задач поиска
    if user_id in quick_search_tasks:
        quick_search_tasks[user_id].cancel()
        del quick_search_tasks[user_id]

    # Выход из дуэли
    if user_id in user_duels:
        duel_id = user_duels[user_id]
        if duel_id in active_duels:
            async with await get_duel_lock(duel_id):
                duel = active_duels[duel_id]
                if user_id in duel["players"]:
                    duel["players"].remove(user_id)

                    # Удаляем из команд
                    if user_id in duel["teams"]["team_a"]:
                        duel["teams"]["team_a"].remove(user_id)
                    elif user_id in duel["teams"]["team_b"]:
                        duel["teams"]["team_b"].remove(user_id)

                    # Удаляем счет
                    if user_id in duel["player_scores"]:
                        del duel["player_scores"][user_id]

                # Если дуэль пустая - удаляем ее
                if not duel["players"]:
                    await complete_duel_cleanup(duel_id)
                else:
                    # Обновляем лобби для оставшихся игроков
                    await update_lobby_for_all_players(duel_id, bot)

        del user_duels[user_id]


async def complete_duel_cleanup(duel_id: str):
    """Полная очистка дуэли"""
    if duel_id in lobby_messages:
        del lobby_messages[duel_id]
    if duel_id in active_questions:
        del active_questions[duel_id]
    if duel_id in active_duels:
        del active_duels[duel_id]
    if duel_id in duel_locks:
        del duel_locks[duel_id]


# ------------------- Основные функции для дуэлей -------------------
def create_duel_data(duel_id: str, format_type: str, creator_id: int) -> Dict:
    # Обновляем статистику создателя
    creator_stats = get_user_duel_stats(creator_id)
    creator_stats.increment_duels_created()

    return {
        "duel_id": duel_id,
        "format_type": format_type,
        "creator_id": creator_id,
        "teams": {"team_a": [creator_id], "team_b": []},
        "players": [creator_id],
        "team_scores": {"team_a": 0, "team_b": 0},
        "player_scores": {creator_id: 0},
        "current_question": None,
        "answered_players": set(),
        "player_answers": {},
        "status": "waiting",
        "category": None,
        "questions_asked": 0,
        "max_questions": DuelConfig.MAX_QUESTIONS,
        "created_at": datetime.now(),
        "question_start_time": None
    }


def add_player_to_duel(duel: Dict, user_id: int) -> bool:
    if user_id in duel["players"]:
        return False

    # Обновляем статистику игрока
    player_stats = get_user_duel_stats(user_id)
    player_stats.increment_players_joined()

    # Распределяем по командам для баланса
    if len(duel["teams"]["team_a"]) <= len(duel["teams"]["team_b"]):
        duel["teams"]["team_a"].append(user_id)
    else:
        duel["teams"]["team_b"].append(user_id)

    duel["players"].append(user_id)
    duel["player_scores"][user_id] = 0
    duel_stats.increment_players_joined()
    return True


def get_player_team(duel: Dict, user_id: int) -> str:
    """Возвращает команду игрока"""
    if user_id in duel["teams"]["team_a"]:
        return "team_a"
    elif user_id in duel["teams"]["team_b"]:
        return "team_b"
    return ""


def is_duel_full(duel: Dict) -> bool:
    """Проверяет, заполнена ли дуэль"""
    max_players = DuelConfig.get_max_players(duel["format_type"])
    return len(duel["players"]) >= max_players


def get_available_duels(format_type: str = None) -> List[Dict]:
    """Возвращает список доступных дуэлей"""
    available = []
    for duel_id, duel in active_duels.items():
        if (duel["status"] == "waiting" and
                not is_duel_full(duel) and
                (format_type is None or duel["format_type"] == format_type)):
            available.append(duel)
    return available


async def update_lobby_for_all_players(duel_id: str, bot, new_player_name: str = None):
    """Обновляет лобби для всех игроков в дуэли"""
    if duel_id not in active_duels:
        return

    duel = active_duels[duel_id]
    players_count = len(duel["players"])
    max_players = DuelConfig.get_max_players(duel["format_type"])

    # Формируем текст лобби
    text = (
        f"🎮 *Лобби дуэли {duel['format_type'].upper()}*\n\n"
        f"👥 **Игроки:** {players_count}/{max_players}\n"
        f"⚔️ **Формат:** {duel['format_type']}\n"
        f"👑 **Создатель:** {'Вы' if duel['creator_id'] == duel['players'][0] else 'ID ' + str(duel['creator_id'])}\n\n"
    )

    if new_player_name:
        text += f"✅ *{new_player_name} присоединился!*\n\n"

    text += f"🔗 ID комнаты: `{duel_id}`\n\n"

    # Добавляем список игроков
    if duel["players"]:
        text += "📋 **Участники:**\n"
        for i, player_id in enumerate(duel["players"], 1):
            try:
                player_name = await user_cache.get_user_name(bot, player_id)
                team = get_player_team(duel, player_id)
                team_emoji = "🟦" if team == "team_a" else "🟥" if team == "team_b" else "⚪"
                text += f"{i}. {team_emoji} {player_name}\n"
            except Exception as e:
                logger.error(f"Ошибка при получении имени игрока {player_id}: {e}")
                text += f"{i}. ⚪ Игрок {player_id}\n"

    # Обновляем сообщения для всех игроков
    for user_id in duel["players"]:
        try:
            is_creator = (user_id == duel["creator_id"])
            keyboard = duel_lobby_keyboard(duel_id, players_count, max_players, is_creator)

            # Если есть сохраненное сообщение - редактируем его
            if duel_id in lobby_messages and user_id in lobby_messages[duel_id]:
                message_id = lobby_messages[duel_id][user_id]
                await bot.edit_message_text(
                    chat_id=user_id,
                    message_id=message_id,
                    text=text,
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )
            else:
                # Или отправляем новое сообщение
                msg = await bot.send_message(
                    user_id,
                    text,
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )
                # Сохраняем ID сообщения
                if duel_id not in lobby_messages:
                    lobby_messages[duel_id] = {}
                lobby_messages[duel_id][user_id] = msg.message_id

        except Exception as e:
            logger.error(f"Не удалось обновить лобби для игрока {user_id}: {e}")


async def find_or_create_quick_duel(user_id: int, format_type: str, bot) -> Optional[str]:
    """Находит существующую дуэль или создает новую для быстрого поиска"""
    if not validate_duel_format(format_type):
        logger.error(f"Неверный формат дуэли: {format_type}")
        return None

    # Ищем доступные дуэли этого формата
    available_duels = get_available_duels(format_type)

    for duel in available_duels:
        # Проверяем, есть ли место в дуэли
        if not is_duel_full(duel) and user_id not in duel["players"]:
            # Присоединяемся к существующей дуэли
            async with await get_duel_lock(duel["duel_id"]):
                add_player_to_duel(duel, user_id)
            user_duels[user_id] = duel["duel_id"]

            # Обновляем лобби для всех игроков
            try:
                player_name = await user_cache.get_user_name(bot, user_id)
                await update_lobby_for_all_players(duel["duel_id"], bot, player_name)
            except Exception as e:
                logger.error(f"Ошибка при обновлении лобби: {e}")

            return duel["duel_id"]

    # Если подходящей дуэли нет - создаем новую
    duel_id = f"quick_{user_id}_{int(datetime.now().timestamp())}"
    async with await get_duel_lock(duel_id):
        active_duels[duel_id] = create_duel_data(duel_id, format_type, user_id)
    user_duels[user_id] = duel_id

    # Добавляем в очередь быстрого поиска
    if user_id not in duel_queues[format_type]:
        duel_queues[format_type].append(user_id)

    return duel_id


async def quick_search_timer(user_id: int, format_type: str, bot, message: types.Message = None):
    """Таймер для быстрого поиска"""
    try:
        search_start = datetime.now()
        max_wait_time = DuelConfig.MAX_WAIT_TIME

        while (datetime.now() - search_start).total_seconds() < max_wait_time:
            # Проверяем, нашли ли мы дуэль
            if user_id not in duel_queues[format_type]:
                return

            # Обновляем сообщение о поиске
            elapsed = int((datetime.now() - search_start).total_seconds())
            if message:
                await message.edit_text(
                    f"🔍 *Поиск противника...*\n\n"
                    f"⚔️ Формат: {format_type.upper()}\n"
                    f"⏰ Ожидание: {elapsed}/{max_wait_time} сек\n\n"
                    f"🔄 Ищем подходящих соперников...",
                    parse_mode="Markdown"
                )

            # Ищем доступные дуэли
            available_duels = get_available_duels(format_type)
            for duel in available_duels:
                if duel["creator_id"] != user_id and not is_duel_full(duel):
                    # Нашли подходящую дуэль - присоединяемся
                    async with await get_duel_lock(duel["duel_id"]):
                        add_player_to_duel(duel, user_id)
                    user_duels[user_id] = duel["duel_id"]

                    # Удаляем из очереди
                    if user_id in duel_queues[format_type]:
                        duel_queues[format_type].remove(user_id)

                    # Обновляем лобби для всех игроков
                    try:
                        player_name = await user_cache.get_user_name(bot, user_id)
                        await update_lobby_for_all_players(duel["duel_id"], bot, player_name)
                    except Exception as e:
                        logger.error(f"Ошибка при обновлении лобби: {e}")

                    return

            await asyncio.sleep(2)

        # Если время вышло - создаем свою дуэль
        if user_id in duel_queues[format_type]:
            duel_queues[format_type].remove(user_id)

            duel_id = f"quick_{user_id}_{int(datetime.now().timestamp())}"
            async with await get_duel_lock(duel_id):
                active_duels[duel_id] = create_duel_data(duel_id, format_type, user_id)
            user_duels[user_id] = duel_id

            if message:
                await update_lobby_for_all_players(duel_id, bot)

    except Exception as e:
        logger.error(f"Ошибка в таймере быстрого поиска: {e}")
        if user_id in duel_queues[format_type]:
            duel_queues[format_type].remove(user_id)


# ------------------- Функции для вопросов и ответов -------------------
def get_correct_answer_index(question: Dict) -> int:
    """Возвращает индекс правильного ответа"""
    correct_answer = question["answer"]
    for i, option in enumerate(question["options"]):
        if option == correct_answer:
            return i
    return -1


def is_answer_correct(question: Dict, answer_index: int) -> bool:
    """Проверяет, правильный ли ответ"""
    correct_index = get_correct_answer_index(question)
    return answer_index == correct_index


async def process_player_answer(duel: Dict, user_id: int, answer_index: int, answer_time: datetime) -> Tuple[bool, str]:
    """Обрабатывает ответ игрока"""
    if not duel["current_question"]:
        return False, "❌ Вопрос не активен"

    if user_id in duel["answered_players"]:
        return False, "❌ Ты уже ответил на этот вопрос"

    question = duel["current_question"]

    # Проверяем корректность индекса ответа
    if answer_index < 0 or answer_index >= len(question["options"]):
        return False, "❌ Неверный вариант ответа"

    # Проверяем ответ
    is_correct = is_answer_correct(question, answer_index)

    # Сохраняем ответ игрока
    duel["answered_players"].add(user_id)
    duel["player_answers"][user_id] = {
        "answer_index": answer_index,
        "is_correct": is_correct,
        "timestamp": answer_time,
        "response_time": (answer_time - duel["question_start_time"]).total_seconds()
    }

    # ОБНОВЛЕНО: Используем персональную статистику вместо глобальной
    player_stats = get_user_duel_stats(user_id)
    player_stats.increment_questions_answered()

    if is_correct:
        # Начисляем очки команде
        team = get_player_team(duel, user_id)
        if team:
            duel["team_scores"][team] += 1
            duel["player_scores"][user_id] += 1

        # ОБНОВЛЕНО: Персональная статистика правильных ответов
        player_stats.increment_correct_answers()
        return True, "✅ Правильно! +1 очко твоей команде"
    else:
        correct_answer = question["answer"]
        return False, f"❌ Неправильно! Правильный ответ: {correct_answer}"


async def handle_question_completion(duel_id: str, bot):
    """Обрабатывает завершение вопроса"""
    if duel_id not in active_duels:
        return

    duel = active_duels[duel_id]
    question = duel["current_question"]

    if not question:
        return

    correct_answer = question["answer"]
    answered_count = len(duel["answered_players"])
    total_players = len(duel["players"])

    # Анализируем результаты вопроса
    correct_players = [uid for uid, answer in duel["player_answers"].items() if answer["is_correct"]]
    incorrect_players = [uid for uid, answer in duel["player_answers"].items() if not answer["is_correct"]]

    result_text = (
        f"⏰ Время вышло!\n\n"
        f"📝 **Правильный ответ:** {correct_answer}\n"
        f"🎯 **Ответили:** {answered_count}/{total_players} игроков\n"
        f"✅ **Правильно:** {len(correct_players)} игроков\n"
        f"❌ **Неправильно:** {len(incorrect_players)} игроков\n\n"
        f"⚔️ **Текущий счет:** 🟦 {duel['team_scores']['team_a']} - {duel['team_scores']['team_b']} 🟥"
    )

    # Очищаем данные вопроса
    duel["current_question"] = None
    duel["answered_players"] = set()
    duel["player_answers"] = {}
    duel["question_start_time"] = None

    # Отправляем результат всем игрокам
    for user_id in duel["players"]:
        try:
            await bot.send_message(user_id, result_text, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Не удалось отправить результат игроку {user_id}: {e}")

    # Следующий вопрос
    await asyncio.sleep(3)
    await ask_duel_question(duel_id, bot)

@router.callback_query(F.data == "menu:duels")
async def handle_duels_menu(callback: types.CallbackQuery):
    """Обработчик кнопки Дуэли из главного меню"""
    print("✅ Обработчик дуэлей вызван!")
    await callback.answer("✅ Дуэли работают!", show_alert=True)
    """Обработчик кнопки Дуэли из главного меню"""
    try:
        user_id = callback.from_user.id

        # Проверяем, не участвует ли пользователь уже в дуэли
        if user_id in user_duels:
            duel_id = user_duels[user_id]
            if duel_id in active_duels:
                duel = active_duels[duel_id]
                if duel["status"] == "waiting":
                    await callback.answer("❌ Ты уже в лобби дуэли!", show_alert=True)
                    return
                elif duel["status"] == "active":
                    await callback.answer("❌ Ты уже в активной дуэли!", show_alert=True)
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

        await callback.message.edit_text(
            text,
            reply_markup=duels_main_keyboard(),
            parse_mode="Markdown"
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Error in duels menu: {e}")
        await callback.answer("❌ Ошибка при открытии меню дуэлей", show_alert=True)


@router.callback_query(F.data == "duel:quick_menu")
async def quick_duel_menu(callback: types.CallbackQuery):
    """Меню быстрого поиска дуэли"""
    text = (
        "⚡ *Быстрый поиск дуэли*\n\n"
        "Выбери формат для быстрого поиска:\n\n"
        "• ⚡ **1 vs 1** - мгновенная дуэль\n"
        "• ⚡ **2 vs 2** - быстрая командная игра\n"
        "• ⚡ **3 vs 3** - тактическая битва\n"
        "• ⚡ **4 vs 4** - масштабное сражение\n\n"
        "🎯 Система автоматически найдет тебе противников!"
    )

    try:
        await callback.message.edit_text(
            text,
            reply_markup=duel_quick_menu_keyboard(),
            parse_mode="Markdown"
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при отображении меню быстрого поиска: {e}")
        await callback.answer("❌ Ошибка при загрузке меню", show_alert=True)


@router.callback_query(F.data.startswith("duel:quick_join:"))
async def quick_join_duel(callback: types.CallbackQuery):
    """Быстрое присоединение к дуэли"""
    user_id = callback.from_user.id
    format_type = callback.data.split(":")[2]

    if not validate_duel_format(format_type):
        await callback.answer("❌ Неверный формат дуэли", show_alert=True)
        return

    logger.info(f"Пользователь {user_id} начал быстрый поиск дуэли {format_type}")

    # Проверяем, не участвует ли уже в дуэли
    if user_id in user_duels:
        await callback.answer("❌ Ты уже участвуешь в дуэли!", show_alert=True)
        return

    # Отправляем сообщение о начале поиска
    search_message = await callback.message.edit_text(
        f"🔍 *Поиск противника...*\n\n"
        f"⚔️ Формат: {format_type.upper()}\n"
        f"⏰ Ожидание: 0/{DuelConfig.MAX_WAIT_TIME} сек\n\n"
        f"🔄 Ищем подходящих соперников...",
        parse_mode="Markdown"
    )

    # Запускаем быстрый поиск
    duel_id = await find_or_create_quick_duel(user_id, format_type, callback.bot)

    if duel_id and user_id not in duel_queues[format_type]:
        await update_lobby_for_all_players(duel_id, callback.bot)
    else:
        search_task = asyncio.create_task(
            quick_search_timer(user_id, format_type, callback.bot, search_message)
        )
        quick_search_tasks[user_id] = search_task

    await callback.answer()


@router.callback_query(F.data == "duel:create")
async def create_duel(callback: types.CallbackQuery):
    """Создание дуэли"""
    text = (
        "🎮 *Создание дуэли*\n\n"
        "Выбери формат сражения:\n\n"
        "• 1️⃣ **1 vs 1** - быстрая дуэль\n"
        "• 2️⃣ **2 vs 2** - командная игра\n"
        "• 3️⃣ **3 vs 3** - тактическая битва\n"
        "• 4️⃣ **4 vs 4** - масштабное сражение\n\n"
        "⚡ Чем больше команда - тем интереснее!"
    )

    try:
        await callback.message.edit_text(
            text,
            reply_markup=duel_formats_keyboard(),
            parse_mode="Markdown"
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при создании дуэли: {e}")
        await callback.answer("❌ Ошибка при создании дуэли", show_alert=True)


@router.callback_query(F.data.startswith("duel_format:"))
async def select_duel_format(callback: types.CallbackQuery):
    """Выбор формата дуэли"""
    user_id = callback.from_user.id
    format_type = callback.data.split(":")[1]

    if not validate_duel_format(format_type):
        await callback.answer("❌ Неверный формат дуэли", show_alert=True)
        return

    logger.info(f"Пользователь {user_id} выбрал формат {format_type}")

    # Создаем ID дуэли
    duel_id = f"duel_{user_id}_{int(datetime.now().timestamp())}"

    # Создаем дуэль
    async with await get_duel_lock(duel_id):
        active_duels[duel_id] = create_duel_data(duel_id, format_type, user_id)
    user_duels[user_id] = duel_id

    # Обновляем лобби для создателя
    await update_lobby_for_all_players(duel_id, callback.bot)
    await callback.answer(f"✅ Создана дуэль {format_type}")


@router.callback_query(F.data == "duel:join_menu")
async def join_duel_menu(callback: types.CallbackQuery):
    """Меню присоединения к дуэли"""
    text = (
        "🔍 *Присоединение к дуэли*\n\n"
        "Выбери способ поиска:\n\n"
        "• 📝 **Ввести ID** - присоединиться по коду комнаты\n"
        "• 🔍 **Активные дуэли** - посмотреть список доступных дуэлей\n\n"
        "Или создай свою дуэль!"
    )

    try:
        await callback.message.edit_text(
            text,
            reply_markup=duel_join_menu_keyboard(),
            parse_mode="Markdown"
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при отображении меню присоединения: {e}")
        await callback.answer("❌ Ошибка при загрузке меню", show_alert=True)


@router.callback_query(F.data == "duel:active_list")
async def show_active_duels(callback: types.CallbackQuery):
    """Показывает список активных дуэлей"""
    available_duels = get_available_duels()

    if not available_duels:
        text = (
            "📭 *Активные дуэли*\n\n"
            "Сейчас нет доступных дуэлей для присоединения.\n\n"
            "🎮 Создай свою дуэль и пригласи друзей!"
        )

        try:
            await callback.message.edit_text(
                text,
                reply_markup=duel_join_menu_keyboard(),
                parse_mode="Markdown"
            )
            await callback.answer("❌ Нет доступных дуэлей")
        except Exception as e:
            logger.error(f"Ошибка при отображении пустого списка дуэлей: {e}")
            await callback.answer("❌ Ошибка при загрузке списка", show_alert=True)
        return

    text = (
        "🔍 *Активные дуэли*\n\n"
        "Выбери дуэль для присоединения:\n\n"
        f"⚡ Доступно дуэлей: {len(available_duels)}\n"
        "🎮 Нажми на формат для присоединения"
    )

    try:
        await callback.message.edit_text(
            text,
            reply_markup=duel_active_list_keyboard(available_duels),
            parse_mode="Markdown"
        )
        await callback.answer(f"✅ Найдено {len(available_duels)} дуэлей")
    except Exception as e:
        logger.error(f"Ошибка при отображении списка дуэлей: {e}")
        await callback.answer("❌ Ошибка при загрузке списка", show_alert=True)


@router.callback_query(F.data.startswith("duel:join:"))
async def join_duel(callback: types.CallbackQuery):
    """Присоединение к дуэли по ID"""
    user_id = callback.from_user.id
    duel_id = callback.data.split(":")[2]

    logger.info(f"Пользователь {user_id} присоединяется к дуэли {duel_id}")

    if duel_id not in active_duels:
        await callback.answer("❌ Дуэль не найдена или уже началась", show_alert=True)
        return

    duel = active_duels[duel_id]

    # Проверяем, не присоединен ли уже
    if user_id in duel["players"]:
        await callback.answer("❌ Ты уже в этой дуэли", show_alert=True)
        return

    # Проверяем количество игроков
    max_players = DuelConfig.get_max_players(duel["format_type"])
    if len(duel["players"]) >= max_players:
        await callback.answer("❌ В дуэли уже максимальное количество игроков", show_alert=True)
        return

    # Добавляем игрока в дуэль
    async with await get_duel_lock(duel_id):
        add_player_to_duel(duel, user_id)
    user_duels[user_id] = duel_id

    # Обновляем лобби для всех игроков
    try:
        player_name = await user_cache.get_user_name(callback.bot, user_id)
        await update_lobby_for_all_players(duel_id, callback.bot, player_name)
        await callback.answer("✅ Ты присоединился к дуэли!")
    except Exception as e:
        logger.error(f"Ошибка при присоединении к дуэли: {e}")
        await callback.answer("❌ Ошибка при присоединении", show_alert=True)


@router.callback_query(F.data == "duel:join_input")
async def join_duel_input(callback: types.CallbackQuery):
    """Запрос ID дуэли для присоединения"""
    text = (
        "📝 *Присоединение по ID*\n\n"
        "Введи ID дуэли для присоединения:\n\n"
        "🔗 ID обычно выглядит так: `duel_123456789_1234567890`\n\n"
        "❌ Для отмены нажми /menu"
    )

    try:
        await callback.message.edit_text(
            text,
            parse_mode="Markdown"
        )
        await callback.answer("✏️ Введи ID дуэли")
    except Exception as e:
        logger.error(f"Ошибка при запросе ID дуэли: {e}")
        await callback.answer("❌ Ошибка при запросе ID", show_alert=True)


@router.message(F.text.startswith("duel_"))
async def join_duel_by_id(message: types.Message):
    """Присоединение к дуэли по введенному ID"""
    user_id = message.from_user.id
    duel_id = message.text.strip()

    logger.info(f"Пользователь {user_id} пытается присоединиться к дуэли {duel_id}")

    if duel_id not in active_duels:
        await message.answer("❌ Дуэль не найдена или уже началась")
        return

    duel = active_duels[duel_id]

    # Проверяем, не присоединен ли уже
    if user_id in duel["players"]:
        await message.answer("❌ Ты уже в этой дуэли")
        return

    # Проверяем количество игроков
    max_players = DuelConfig.get_max_players(duel["format_type"])
    if len(duel["players"]) >= max_players:
        await message.answer("❌ В дуэли уже максимальное количество игроков")
        return

    # Добавляем игрока в дуэль
    async with await get_duel_lock(duel_id):
        add_player_to_duel(duel, user_id)
    user_duels[user_id] = duel_id

    # Обновляем лобби для всех игроков
    try:
        player_name = await user_cache.get_user_name(message.bot, user_id)
        await update_lobby_for_all_players(duel_id, message.bot, player_name)
        await message.answer("✅ Ты присоединился к дуэли!")
    except Exception as e:
        logger.error(f"Ошибка при присоединении к дуэли: {e}")
        await message.answer("❌ Ошибка при присоединении")


@router.callback_query(F.data.startswith("duel:start:"))
async def start_duel_handler(callback: types.CallbackQuery):
    """Обработчик начала дуэли"""
    duel_id = callback.data.split(":")[2]
    user_id = callback.from_user.id

    logger.info(f"Пользователь {user_id} запускает дуэль {duel_id}")

    if duel_id not in active_duels:
        await callback.answer("❌ Дуэль не найдена", show_alert=True)
        return

    duel = active_duels[duel_id]

    # Проверяем, что дуэль еще не начата
    if duel["status"] != "waiting":
        await callback.answer("❌ Дуэль уже начата или завершена", show_alert=True)
        return

    # Проверяем, что пользователь - создатель дуэли
    if duel["creator_id"] != user_id:
        await callback.answer("❌ Только создатель может начать дуэль", show_alert=True)
        return

    # Проверяем минимальное количество игроков
    if len(duel["players"]) < 2:
        await callback.answer("❌ Нужно минимум 2 игрока для начала", show_alert=True)
        return

    # Запускаем дуэль
    await start_duel(duel_id, callback.bot)
    await callback.answer("🎮 Дуэль начинается!")


@router.callback_query(F.data == "duel:leave")
async def leave_duel(callback: types.CallbackQuery):
    """Выход из дуэли"""
    user_id = callback.from_user.id

    logger.info(f"Пользователь {user_id} покидает дуэль")

    await cleanup_user_resources(user_id, callback.bot)
    await callback.answer("🚪 Ты вышел из дуэли", show_alert=True)

    # Вместо duels_menu вызываем главное меню
    from keyboards import main_menu
    await callback.message.edit_text(
        "👋 Ты вышел из дуэли. Возвращаемся в главное меню...",
        reply_markup=main_menu()
    )

@router.callback_query(F.data == "duel:cancel_search")
async def cancel_quick_search(callback: types.CallbackQuery):
    """Отмена быстрого поиска"""
    user_id = callback.from_user.id

    await cleanup_user_resources(user_id, callback.bot)
    await callback.answer("❌ Поиск отменен", show_alert=True)
    await quick_duel_menu(callback)


@router.callback_query(F.data == "duel:refresh")
async def refresh_lobby(callback: types.CallbackQuery):
    """Обновление лобби"""
    user_id = callback.from_user.id

    if user_id not in user_duels:
        await callback.answer("❌ Ты не в дуэли", show_alert=True)
        return

    duel_id = user_duels[user_id]

    if duel_id in active_duels:
        await update_lobby_for_all_players(duel_id, callback.bot)
        await callback.answer("🔄 Лобби обновлено")
    else:
        await callback.answer("❌ Дуэль не найдена", show_alert=True)


# ------------------- Игровые функции -------------------
async def start_duel(duel_id: str, bot):
    """Запускает дуэль"""
    logger.info(f"Запуск дуэли {duel_id}")

    if duel_id not in active_duels:
        logger.error(f"Дуэль {duel_id} не найдена при запуске")
        return

    duel = active_duels[duel_id]
    duel["status"] = "active"

    # Удаляем сообщения лобби
    if duel_id in lobby_messages:
        for user_id, message_id in lobby_messages[duel_id].items():
            await safe_delete_message(bot, user_id, message_id)
        del lobby_messages[duel_id]

    # Выбираем категорию
    duel["category"] = "random"

    # Уведомляем всех игроков
    for user_id in duel["players"]:
        try:
            await bot.send_message(
                user_id,
                "🎮 *Дуэль начинается!*\n\n"
                f"⚔️ Формат: {duel['format_type']}\n"
                f"📚 Категория: {duel['category']}\n"
                f"👥 Игроков: {len(duel['players'])}\n"
                f"❓ Вопросов: {duel['max_questions']}\n\n"
                "Готовься к первому вопросу!",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Не удалось уведомить игрока {user_id}: {e}")

    # Запускаем первый вопрос
    await asyncio.sleep(3)
    await ask_duel_question(duel_id, bot)


async def ask_duel_question(duel_id: str, bot):
    """Задает вопрос в дуэли"""
    try:
        if duel_id not in active_duels:
            return

        duel = active_duels[duel_id]

        # Проверяем, не достигли ли максимума вопросов
        if duel["questions_asked"] >= duel["max_questions"]:
            logger.info(f"Достигнут максимум вопросов для дуэли {duel_id}")
            await finish_duel(duel_id, bot)
            return

        # Получаем случайный вопрос
        question = get_random_question(duel["category"])
        if not question:
            logger.error(f"Не удалось получить вопрос для категории: {duel['category']}")
            await asyncio.sleep(2)
            await ask_duel_question(duel_id, bot)
            return

        # Обновляем состояние дуэли
        duel["current_question"] = question
        duel["answered_players"] = set()
        duel["player_answers"] = {}
        duel["questions_asked"] += 1
        duel["question_start_time"] = datetime.now()

        current_question = duel["questions_asked"]
        max_questions = duel["max_questions"]

        question_text = (
            f"❓ *Вопрос {current_question}/{max_questions}*\n\n"
            f"{question['question']}\n\n"
            f"⚔️ Текущий счет: 🟦 {duel['team_scores']['team_a']} - {duel['team_scores']['team_b']} 🟥"
        )

        logger.info(f"Отправляем вопрос {current_question}/{max_questions} для дуэли {duel_id}")

        # Отправляем вопрос всем игрокам
        sent_messages = {}
        for user_id in duel["players"]:
            try:
                # ИСПРАВЛЕНИЕ: передаем for_duel=True
                msg = await bot.send_message(
                    user_id,
                    question_text,
                    reply_markup=quiz_options(question["options"], for_duel=True, prefix="duel_answer"),
                    parse_mode="Markdown"
                )
                sent_messages[user_id] = msg.message_id
            except Exception as e:
                logger.error(f"Не удалось отправить вопрос игроку {user_id}: {e}")

        # Сохраняем ID сообщений с вопросами
        active_questions[duel_id] = sent_messages

        # Запускаем таймер
        asyncio.create_task(duel_question_timer(duel_id, bot))

    except Exception as e:
        logger.error(f"Ошибка в ask_duel_question: {e}", exc_info=True)


async def duel_question_timer(duel_id: str, bot, duration: int = DuelConfig.QUESTION_TIMEOUT):
    """Таймер для вопроса в дуэли"""
    try:
        await asyncio.sleep(duration)

        if duel_id not in active_duels:
            return

        duel = active_duels[duel_id]

        if duel["status"] != "active" or not duel["current_question"]:
            return

        # Удаляем клавиатуры у всех игроков
        if duel_id in active_questions:
            for user_id, message_id in active_questions[duel_id].items():
                try:
                    await bot.edit_message_reply_markup(
                        chat_id=user_id,
                        message_id=message_id,
                        reply_markup=None
                    )
                except Exception as e:
                    logger.debug(f"Не удалось удалить клавиатуру у игрока {user_id}: {e}")

        # Обрабатываем завершение вопроса
        await handle_question_completion(duel_id, bot)

    except Exception as e:
        logger.error(f"Ошибка в duel_question_timer: {e}", exc_info=True)


@router.callback_query(F.data.startswith("duel_answer:"))
async def handle_duel_answer(callback: types.CallbackQuery):
    """Обработка ответов в дуэли"""
    try:
        user_id = callback.from_user.id

        # Парсим индекс ответа
        try:
            chosen_answer_index = int(callback.data.split(":")[1])
        except (IndexError, ValueError) as e:
            logger.error(f"Ошибка парсинга callback data: {e}")
            await callback.answer("❌ Ошибка обработки ответа", show_alert=True)
            return

        # Находим дуэль пользователя
        if user_id not in user_duels:
            await callback.answer("❌ Ты не участвуешь в дуэли", show_alert=True)
            return

        duel_id = user_duels[user_id]

        if duel_id not in active_duels:
            await callback.answer("❌ Дуэль не найдена", show_alert=True)
            return

        duel = active_duels[duel_id]

        # Проверяем, активна ли дуэль
        if duel["status"] != "active":
            await callback.answer("❌ Дуэль не активна", show_alert=True)
            return

        # Проверяем, есть ли текущий вопрос
        if not duel["current_question"]:
            await callback.answer("❌ Сейчас нет активного вопроса", show_alert=True)
            return

        # Проверяем, не ответил ли уже пользователь
        if user_id in duel["answered_players"]:
            await callback.answer("❌ Ты уже ответил на этот вопрос", show_alert=True)
            return

        # Проверяем валидность индекса ответа
        question = duel["current_question"]
        if chosen_answer_index < 0 or chosen_answer_index >= len(question["options"]):
            await callback.answer("❌ Неверный вариант ответа", show_alert=True)
            return

        # Обрабатываем ответ
        answer_time = datetime.now()
        is_correct, message = await process_player_answer(duel, user_id, chosen_answer_index, answer_time)

        await callback.answer(message, show_alert=True)

        # Удаляем клавиатуру у пользователя
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception as e:
            logger.debug(f"Не удалось удалить клавиатуру у пользователя {user_id}: {e}")

        # Проверяем, все ли ответили
        total_players = len(duel["players"])
        answered_players = len(duel["answered_players"])

        if answered_players == total_players:
            # Удаляем клавиатуры у всех игроков
            if duel_id in active_questions:
                for player_id, message_id in active_questions[duel_id].items():
                    try:
                        await callback.bot.edit_message_reply_markup(
                            chat_id=player_id,
                            message_id=message_id,
                            reply_markup=None
                        )
                    except Exception as e:
                        logger.debug(f"Не удалось удалить клавиатуру у игрока {player_id}: {e}")

            # ДАЕМ ИГРОКАМ ВРЕМЯ УВИДЕТЬ РЕЗУЛЬТАТЫ - 5 секунд
            await asyncio.sleep(3)

            # Затем переходим к следующему вопросу
            await handle_question_completion(duel_id, callback.bot)

    except Exception as e:
        logger.error(f"Ошибка обработки ответа в дуэли: {e}", exc_info=True)
        await callback.answer("❌ Произошла ошибка при обработке ответа", show_alert=True)


async def finish_duel(duel_id: str, bot):
    """Завершает дуэль и выдает результаты"""
    try:
        if duel_id not in active_duels:
            return

        duel = active_duels[duel_id]

        if duel["status"] == "finished":
            return

        duel["status"] = "finished"
        duel_stats.increment_duels_completed()

        # Определяем победителя
        team_a_score = duel["team_scores"]["team_a"]
        team_b_score = duel["team_scores"]["team_b"]

        if team_a_score > team_b_score:
            winner = "team_a"
            winner_text = "🟦 Команда A"
        elif team_b_score > team_a_score:
            winner = "team_b"
            winner_text = "🟥 Команда B"
        else:
            winner = "draw"
            winner_text = "🤝 Ничья"

        # ДОБАВЛЕНО: Обновляем персональную статистику игроков
        for user_id in duel["players"]:
            player_stats = get_user_duel_stats(user_id)
            player_stats.increment_duels_completed()

            team = get_player_team(duel, user_id)
            if winner == "draw":
                player_stats.increment_duels_draw()
            elif team == winner:
                player_stats.increment_duels_won()
            else:
                player_stats.increment_duels_lost()

        # Отправляем результаты всем игрокам
        for user_id in duel["players"]:
            try:
                team = get_player_team(duel, user_id)
                personal_score = duel["player_scores"][user_id]
                is_winner = (winner == "draw") or (team == winner)

                # Формируем список игроков для отображения
                team_a_players = []
                for player_id in duel["teams"]["team_a"]:
                    name = await user_cache.get_user_name(bot, player_id)
                    score = duel["player_scores"].get(player_id, 0)
                    team_a_players.append(f"{name} ({score})")

                team_b_players = []
                for player_id in duel["teams"]["team_b"]:
                    name = await user_cache.get_user_name(bot, player_id)
                    score = duel["player_scores"].get(player_id, 0)
                    team_b_players.append(f"{name} ({score})")

                result_text = (
                    f"🏆 *Дуэль завершена!*\n\n"
                    f"⚔️ **Финальные результаты:**\n"
                    f"🟦 Команда A: {team_a_score} очков\n"
                    f"🟥 Команда B: {team_b_score} очков\n\n"
                    f"🎯 **Победитель:** {winner_text}\n"
                    f"📊 Твой счет: {personal_score} очков\n\n"
                    f"👥 **Составы команд:**\n"
                    f"🟦 Команда A: {', '.join(team_a_players)}\n"
                    f"🟥 Команда B: {', '.join(team_b_players)}\n\n"
                )

                if is_winner and winner != "draw":
                    result_text += "🎉 Твоя команда победила! +25 XP"
                elif winner == "draw":
                    result_text += "🤝 Ничья! +10 XP"
                else:
                    result_text += "💪 Ты проиграл, но получил опыт! +10 XP"

                await bot.send_message(user_id, result_text, parse_mode="Markdown")

            except Exception as e:
                logger.error(f"Не удалось отправить результаты игроку {user_id}: {e}")

        # Очищаем данные дуэли
        for user_id in duel["players"]:
            if user_id in user_duels and user_duels[user_id] == duel_id:
                del user_duels[user_id]

        await complete_duel_cleanup(duel_id)

    except Exception as e:
        logger.error(f"Ошибка в finish_duel: {e}", exc_info=True)


# ------------------- Фоновые задачи -------------------
async def cleanup_stale_duels():
    """Очистка зависших дуэлей"""
    while True:
        await asyncio.sleep(DuelConfig.CLEANUP_INTERVAL)
        current_time = datetime.now()
        stale_duels = []

        for duel_id, duel in active_duels.items():
            time_diff = (current_time - duel["created_at"]).total_seconds()
            if time_diff > DuelConfig.STALE_DUEL_TIMEOUT:
                stale_duels.append(duel_id)

        for duel_id in stale_duels:
            logger.info(f"Очистка зависшей дуэли: {duel_id}")
            await complete_duel_cleanup(duel_id)

        # Очищаем expired кэш
        user_cache.clear_expired()


# Запуск фоновых задач при старте бота
async def start_background_tasks():
    """Запускает фоновые задачи"""
    asyncio.create_task(cleanup_stale_duels())
    logger.info("Фоновые задачи дуэлей запущены")

# Алиас для обратной совместимости
async def start_cleanup_task():
    """Алиас для обратной совместимости"""
    await start_background_tasks()

# Добавь этот код в конец duels.py для запуска фоновых задач

@router.startup()
async def on_startup():
    """Запускается при старте бота"""
    await start_background_tasks()
    logger.info("Модуль дуэлей инициализирован")

@router.shutdown()
async def on_shutdown():
    """Запускается при выключении бота"""
    logger.info("Модуль дуэлей завершает работу")


@router.callback_query(F.data == "duel:my_duels")
async def my_duels_handler(callback: types.CallbackQuery):
    """Обработчик кнопки 'Мои дуэли'"""
    user_id = callback.from_user.id

    try:
        print(f"✅ Кнопка 'Мои дуэли' нажата пользователем {user_id}")

        # Проверяем, участвует ли пользователь в дуэли
        if user_id in user_duels:
            duel_id = user_duels[user_id]
            if duel_id in active_duels:
                duel = active_duels[duel_id]

                if duel["status"] == "waiting":
                    # Показываем лобби дуэли
                    await update_lobby_for_all_players(duel_id, callback.bot)
                    await callback.answer("✅ Переходим в лобби дуэли")
                    return
                elif duel["status"] == "active":
                    # Показываем активную дуэль
                    text = (
                        "🎮 *Текущая дуэль*\n\n"
                        f"⚔️ Формат: {duel['format_type']}\n"
                        f"📚 Категория: {duel['category']}\n"
                        f"👥 Игроков: {len(duel['players'])}\n"
                        f"❓ Вопрос: {duel['questions_asked']}/{duel['max_questions']}\n\n"
                        f"⚔️ Счет: 🟦 {duel['team_scores']['team_a']} - {duel['team_scores']['team_b']} 🟥"
                    )

                    await callback.message.edit_text(
                        text,
                        parse_mode="Markdown"
                    )
                    await callback.answer()
                    return

        # Если пользователь не в дуэли
        text = (
            "📭 *Мои дуэли*\n\n"
            "Сейчас ты не участвуешь в дуэлях.\n\n"
            "🎯 Доступные действия:\n"
            "• 🎯 Быстрый поиск - найди противника за 30 сек\n"
            "• 👥 Создать комнату - создай свою дуэль\n"
            "• 🔍 Присоединиться - найди готовые дуэли\n\n"
            "Выбери действие ниже 👇"
        )

        await callback.message.edit_text(
            text,
            reply_markup=duels_main_keyboard(),
            parse_mode="Markdown"
        )
        await callback.answer("❌ Ты не участвуешь в дуэлях")

    except Exception as e:
        logger.error(f"Ошибка в обработчике моих дуэлей: {e}")
        await callback.answer("❌ Ошибка при загрузке дуэлей", show_alert=True)


@router.callback_query(F.data == "duel:stats")
async def duel_stats_handler(callback: types.CallbackQuery):
    """Обработчик кнопки 'Статистика' в дуэлях"""
    try:
        user_id = callback.from_user.id
        user_stats = get_user_duel_stats(user_id)

        # Получаем персональную статистику
        full_text = user_stats.get_stats()

        # Добавляем информацию о текущих дуэлях пользователя
        user_active_duels = []
        for duel_id, duel in active_duels.items():
            if user_id in duel["players"]:
                user_active_duels.append(duel)

        # Формируем информацию о текущих дуэлях
        if user_active_duels:
            current_info = f"\n🎮 *Твои текущие дуэли:* {len(user_active_duels)}\n"
            for duel in user_active_duels[:3]:
                status_emoji = "⏳" if duel["status"] == "waiting" else "🎯"
                current_info += f"• {status_emoji} {duel['format_type']} ({duel['status']})\n"
            full_text += current_info
        else:
            full_text += "\n📭 *Сейчас ты не участвуешь в дуэлях*"

        await callback.message.edit_text(
            full_text,
            reply_markup=duels_main_keyboard(),
            parse_mode="Markdown"
        )
        await callback.answer("📊 Твоя статистика дуэлей")

    except Exception as e:
        logger.error(f"Ошибка в обработчике статистики дуэлей: {e}")
        await callback.answer("❌ Ошибка при загрузке статистики", show_alert=True)


# Добавьте в конец duels.py

async def shutdown_duels():
    """Очистка ресурсов дуэлей при выключении бота"""
    logger.info("🛑 Очистка ресурсов дуэлей...")

    try:
        # Отменяем все задачи быстрого поиска
        for user_id, task in quick_search_tasks.items():
            if not task.done():
                task.cancel()

        # Очищаем все активные дуэли
        for duel_id in list(active_duels.keys()):
            await complete_duel_cleanup(duel_id)

        # Очищаем очереди
        for format_type in duel_queues:
            duel_queues[format_type].clear()

        # Очищаем пользовательские данные
        user_duels.clear()
        quick_search_tasks.clear()
        lobby_messages.clear()
        active_questions.clear()
        duel_locks.clear()

        logger.info("✅ Ресурсы дуэлей очищены")
    except Exception as e:
        logger.error(f"❌ Ошибка при очистке дуэлей: {e}")