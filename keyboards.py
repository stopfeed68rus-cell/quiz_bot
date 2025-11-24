from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from typing import Optional, List


def main_menu() -> InlineKeyboardMarkup:
    """Главное меню с новой кнопкой дуэлей"""
    keyboard = InlineKeyboardBuilder()

    keyboard.row(
        InlineKeyboardButton(text="🎮 Начать квиз", callback_data="menu:categories"),
        InlineKeyboardButton(text="🎁 Ежедневная награда", callback_data="menu:daily_reward")
    )
    keyboard.row(
        InlineKeyboardButton(text="👤 Профиль", callback_data="menu:profile"),
        InlineKeyboardButton(text="🏆 Достижения", callback_data="menu:achievements")
    )
    keyboard.row(
        InlineKeyboardButton(text="⚔️ Дуэли", callback_data="menu:duels"),
        InlineKeyboardButton(text="📊 Топ игроков", callback_data="menu:top")
    )
    keyboard.row(
        InlineKeyboardButton(text="ℹ️ Помощь", callback_data="menu:help")
    )

    return keyboard.as_markup()


def quiz_options(options: list, for_duel: bool = False, prefix: str = "answer") -> InlineKeyboardMarkup:
    """Клавиатура с вариантами ответов для квиза"""
    keyboard = InlineKeyboardBuilder()

    # Используем переданный префикс или выбираем автоматически
    if for_duel:
        callback_prefix = "duel_answer"  # Префикс для дуэлей
    else:
        callback_prefix = prefix

    # Добавляем варианты ответов с правильными индексами
    for index, option in enumerate(options):
        callback_data = f"{callback_prefix}:{index}"
        keyboard.row(
            InlineKeyboardButton(
                text=str(option),
                callback_data=callback_data
            )
        )

    # Добавляем кнопку "Назад" только для обычных квизов, не для дуэлей
    if not for_duel:
        keyboard.row(
            InlineKeyboardButton(text="🔙 Назад в меню", callback_data="menu:main")
        )

    return keyboard.as_markup()

def profile_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура профиля"""
    keyboard = InlineKeyboardBuilder()

    keyboard.row(
        InlineKeyboardButton(text="✏️ Сменить ник", callback_data="profile:change_name"),
        InlineKeyboardButton(text="🔄 Сбросить прогресс", callback_data="profile:reset_progress")
    )
    keyboard.row(
        InlineKeyboardButton(text="🔙 Назад", callback_data="menu:main")
    )

    return keyboard.as_markup()


def confirmation_keyboard(confirm_data: str, cancel_data: str) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения действия"""
    keyboard = InlineKeyboardBuilder()

    keyboard.row(
        InlineKeyboardButton(text="✅ Да", callback_data=confirm_data),
        InlineKeyboardButton(text="❌ Нет", callback_data=cancel_data)
    )

    return keyboard.as_markup()


def get_keyboard(keyboard_type: str) -> InlineKeyboardMarkup:
    """Универсальная функция для получения клавиатур"""
    keyboard_map = {
        "stats": main_menu(),
        "profile": profile_keyboard(),
    }
    return keyboard_map.get(keyboard_type, main_menu())


def achievements_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура достижений"""
    keyboard = InlineKeyboardBuilder()

    keyboard.row(
        InlineKeyboardButton(text="🔙 Назад", callback_data="menu:main")
    )

    return keyboard.as_markup()


def daily_reward_keyboard(can_claim: bool) -> InlineKeyboardMarkup:
    """Клавиатура для ежедневных наград"""
    keyboard = InlineKeyboardBuilder()

    if can_claim:
        keyboard.row(
            InlineKeyboardButton(text="🎁 Получить награду", callback_data="claim_daily")
        )

    keyboard.row(
        InlineKeyboardButton(text="🔙 Назад", callback_data="menu:main")
    )

    return keyboard.as_markup()


def categories_keyboard(selected_category: Optional[str] = None) -> InlineKeyboardMarkup:
    """Клавиатура выбора категорий"""
    keyboard = InlineKeyboardBuilder()

    categories = [
        ("📜 История", "история"),
        ("🔬 Наука", "наука"),
        ("🎨 Искусство", "искусство"),
        ("🌍 География", "география"),
        ("⚽ Спорт", "спорт"),
        ("🎲 Случайная", "random")
    ]

    # Добавляем кнопки категорий в 2 колонки
    buttons = []
    for name, category in categories:
        emoji = "✅" if selected_category == category else ""
        buttons.append(InlineKeyboardButton(
            text=f"{emoji} {name}".strip(),
            callback_data=f"category:{category}"
        ))

    # Распределяем по 2 кнопки в ряд
    for i in range(0, len(buttons), 2):
        row = buttons[i:i + 2]
        keyboard.row(*row)

    # Кнопка подтверждения выбора (если категория выбрана)
    if selected_category:
        category_names = {
            "история": "📜 История",
            "наука": "🔬 Наука",
            "искусство": "🎨 Искусство",
            "география": "🌍 География",
            "спорт": "⚽ Спорт",
            "random": "🎲 Случайная"
        }
        selected_name = category_names.get(selected_category, selected_category)

        keyboard.row(
            InlineKeyboardButton(
                text=f"🎮 Начать: {selected_name}",
                callback_data=f"start_quiz:{selected_category}:random"
            )
        )

    keyboard.row(
        InlineKeyboardButton(text="🔙 Назад", callback_data="menu:main")
    )

    return keyboard.as_markup()


def difficulty_keyboard(selected_difficulty: Optional[str] = None) -> InlineKeyboardMarkup:
    """Клавиатура выбора сложности"""
    keyboard = InlineKeyboardBuilder()

    difficulties = [
        ("🟢 Легкий", "легкий"),
        ("🟡 Средний", "средний"),
        ("🔴 Сложный", "сложный"),
        ("🎲 Любая", "random")
    ]

    for name, difficulty in difficulties:
        emoji = "✅" if selected_difficulty == difficulty else ""
        keyboard.row(InlineKeyboardButton(
            text=f"{emoji} {name}".strip(),
            callback_data=f"difficulty:{difficulty}"
        ))

    keyboard.row(
        InlineKeyboardButton(text="🔙 Назад", callback_data="menu:categories")
    )

    return keyboard.as_markup()


# ------------------- ДУЭЛИ КЛАВИАТУРЫ -------------------

def duels_main_keyboard() -> InlineKeyboardMarkup:
    """Главное меню дуэлей"""
    keyboard = InlineKeyboardBuilder()

    keyboard.row(
        InlineKeyboardButton(text="🎯 Быстрый поиск", callback_data="duel:quick_menu"),
        InlineKeyboardButton(text="👥 Создать комнату", callback_data="duel:create")
    )
    keyboard.row(
        InlineKeyboardButton(text="🔍 Присоединиться по ID", callback_data="duel:join_menu"),
        InlineKeyboardButton(text="📊 Мои дуэли", callback_data="duel:my_duels")
    )
    keyboard.row(
        InlineKeyboardButton(text="❓ Правила", callback_data="duel:rules"),
        InlineKeyboardButton(text="🏆 Статистика", callback_data="duel:stats")
    )
    keyboard.row(
        InlineKeyboardButton(text="🔙 Назад", callback_data="menu:main")
    )
    return keyboard.as_markup()


def duel_quick_menu_keyboard() -> InlineKeyboardMarkup:
    """Меню быстрого поиска дуэли"""
    keyboard = InlineKeyboardBuilder()

    keyboard.row(
        InlineKeyboardButton(text="⚡ 1 vs 1", callback_data="duel:quick_join:1v1"),
        InlineKeyboardButton(text="⚡ 2 vs 2", callback_data="duel:quick_join:2v2")
    )
    keyboard.row(
        InlineKeyboardButton(text="⚡ 3 vs 3", callback_data="duel:quick_join:3v3"),
        InlineKeyboardButton(text="⚡ 4 vs 4", callback_data="duel:quick_join:4v4")
    )
    keyboard.row(
        InlineKeyboardButton(text="🔙 Назад", callback_data="menu:duels")
    )

    return keyboard.as_markup()


def duel_formats_keyboard() -> InlineKeyboardMarkup:
    """Выбор формата дуэли"""
    keyboard = InlineKeyboardBuilder()
    keyboard.row(
        InlineKeyboardButton(text="1️⃣ 1 vs 1", callback_data="duel_format:1v1"),
        InlineKeyboardButton(text="2️⃣ 2 vs 2", callback_data="duel_format:2v2")
    )
    keyboard.row(
        InlineKeyboardButton(text="3️⃣ 3 vs 3", callback_data="duel_format:3v3"),
        InlineKeyboardButton(text="4️⃣ 4 vs 4", callback_data="duel_format:4v4")
    )
    keyboard.row(
        InlineKeyboardButton(text="🔙 Назад", callback_data="menu:duels")
    )
    return keyboard.as_markup()


def duel_categories_keyboard(selected_category: Optional[str] = None) -> InlineKeyboardMarkup:
    """Выбор категории для дуэли"""
    keyboard = InlineKeyboardBuilder()

    categories = [
        ("📜 История", "история"),
        ("🔬 Наука", "наука"),
        ("🎨 Искусство", "искусство"),
        ("🌍 География", "география"),
        ("⚽ Спорт", "спорт"),
        ("🎲 Случайная", "random")
    ]

    buttons = []
    for name, category in categories:
        emoji = "✅" if selected_category == category else ""
        buttons.append(InlineKeyboardButton(
            text=f"{emoji} {name}".strip(),
            callback_data=f"duel_category:{category}"
        ))

    # Распределяем по 2 кнопки в ряд
    for i in range(0, len(buttons), 2):
        row = buttons[i:i + 2]
        keyboard.row(*row)

    if selected_category:
        keyboard.row(
            InlineKeyboardButton(
                text="🎮 Начать с этой категорией",
                callback_data=f"duel_start_category:{selected_category}"
            )
        )

    keyboard.row(
        InlineKeyboardButton(text="🔙 Назад", callback_data="duel:create")
    )

    return keyboard.as_markup()


def duel_lobby_keyboard(duel_id: str, players_count: int, max_players: int,
                        is_creator: bool = False) -> InlineKeyboardMarkup:
    """Клавиатура лобби дуэли"""
    keyboard = InlineKeyboardBuilder()

    # Информация о игроках
    keyboard.row(
        InlineKeyboardButton(
            text=f"👥 Игроки: {players_count}/{max_players}",
            callback_data="duel:refresh"
        )
    )

    # Кнопка приглашения
    keyboard.row(
        InlineKeyboardButton(
            text="🔗 Поделиться ссылкой",
            callback_data=f"duel:invite:{duel_id}"
        )
    )

    # Кнопка начала для создателя или когда комната заполнена
    if is_creator and players_count >= 2:  # Минимум 2 игрока для старта
        keyboard.row(
            InlineKeyboardButton(
                text="🎮 Начать дуэль!",
                callback_data=f"duel:start:{duel_id}"
            )
        )
    elif players_count == max_players and is_creator:
        keyboard.row(
            InlineKeyboardButton(
                text="🎮 Начать дуэль! (все на месте)",
                callback_data=f"duel:start:{duel_id}"
            )
        )

    keyboard.row(
        InlineKeyboardButton(text="🔄 Обновить", callback_data="duel:refresh"),
        InlineKeyboardButton(text="🚪 Покинуть лобби", callback_data="duel:leave")
    )

    return keyboard.as_markup()


def duel_join_menu_keyboard() -> InlineKeyboardMarkup:
    """Меню присоединения к дуэли"""
    keyboard = InlineKeyboardBuilder()

    keyboard.row(
        InlineKeyboardButton(text="📝 Ввести ID вручную", callback_data="duel:join_input"),
        InlineKeyboardButton(text="🔍 Активные дуэли", callback_data="duel:active_list")
    )
    keyboard.row(
        InlineKeyboardButton(text="🔙 Назад", callback_data="menu:duels")
    )

    return keyboard.as_markup()


def duel_active_list_keyboard(active_duels_list: list) -> InlineKeyboardMarkup:
    """Список активных дуэлей для присоединения"""
    keyboard = InlineKeyboardBuilder()

    for duel in active_duels_list[:10]:  # Ограничиваем 10 дуэлями
        duel_id = duel["duel_id"]
        format_type = duel["format_type"]
        players_count = len(duel["players"])
        max_players = int(format_type[0]) * 2

        keyboard.row(
            InlineKeyboardButton(
                text=f"{format_type.upper()} ({players_count}/{max_players})",
                callback_data=f"duel:join:{duel_id}"
            )
        )

    keyboard.row(
        InlineKeyboardButton(text="🔄 Обновить", callback_data="duel:active_list"),
        InlineKeyboardButton(text="🔙 Назад", callback_data="duel:join_menu")
    )

    return keyboard.as_markup()


def duel_invite_keyboard(duel_id: str) -> InlineKeyboardMarkup:
    """Клавиатура для приглашения в дуэль"""
    keyboard = InlineKeyboardBuilder()

    keyboard.row(
        InlineKeyboardButton(
            text="🎮 Присоединиться к дуэли",
            callback_data=f"duel:join:{duel_id}"
        )
    )
    keyboard.row(
        InlineKeyboardButton(
            text="📋 Скопировать ID",
            callback_data=f"duel:copy_id:{duel_id}"
        )
    )

    return keyboard.as_markup()


def duel_in_game_keyboard(duel_id: str) -> InlineKeyboardMarkup:
    """Клавиатура во время дуэли"""
    keyboard = InlineKeyboardBuilder()

    keyboard.row(
        InlineKeyboardButton(text="📊 Текущий счет", callback_data=f"duel:score:{duel_id}"),
        InlineKeyboardButton(text="👥 Участники", callback_data=f"duel:players:{duel_id}")
    )
    keyboard.row(
        InlineKeyboardButton(text="🚪 Сдаться", callback_data="duel:surrender")
    )

    return keyboard.as_markup()


def duel_results_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура после завершения дуэли"""
    keyboard = InlineKeyboardBuilder()

    keyboard.row(
        InlineKeyboardButton(text="🔄 Сыграть еще", callback_data="menu:duels"),
        InlineKeyboardButton(text="📊 Статистика", callback_data="duel:stats")
    )
    keyboard.row(
        InlineKeyboardButton(text="🎮 В главное меню", callback_data="menu:main")
    )

    return keyboard.as_markup()


def duel_settings_keyboard() -> InlineKeyboardMarkup:
    """Настройки дуэли"""
    keyboard = InlineKeyboardBuilder()

    keyboard.row(
        InlineKeyboardButton(text="📚 Категории", callback_data="duel:category_settings"),
        InlineKeyboardButton(text="⏱️ Время на ответ", callback_data="duel:time_settings")
    )
    keyboard.row(
        InlineKeyboardButton(text="❓ Количество вопросов", callback_data="duel:questions_settings"),
        InlineKeyboardButton(text="🎯 Сложность", callback_data="duel:difficulty_settings")
    )
    keyboard.row(
        InlineKeyboardButton(text="🔙 Назад", callback_data="duel:create")
    )

    return keyboard.as_markup()


def duel_time_settings_keyboard() -> InlineKeyboardMarkup:
    """Настройки времени для дуэли"""
    keyboard = InlineKeyboardBuilder()

    times = [10, 15, 20, 30, 45, 60]

    buttons = []
    for time in times:
        buttons.append(InlineKeyboardButton(
            text=f"⏱️ {time} сек",
            callback_data=f"duel_time:{time}"
        ))

    # Распределяем по 3 кнопки в ряд
    for i in range(0, len(buttons), 3):
        row = buttons[i:i + 3]
        keyboard.row(*row)

    keyboard.row(
        InlineKeyboardButton(text="🔙 Назад", callback_data="duel:settings")
    )

    return keyboard.as_markup()


def duel_questions_settings_keyboard() -> InlineKeyboardMarkup:
    """Настройки количества вопросов"""
    keyboard = InlineKeyboardBuilder()

    questions_count = [5, 10, 15, 20, 25, 30]

    buttons = []
    for count in questions_count:
        buttons.append(InlineKeyboardButton(
            text=f"❓ {count} вопросов",
            callback_data=f"duel_questions:{count}"
        ))

    # Распределяем по 3 кнопки в ряд
    for i in range(0, len(buttons), 3):
        row = buttons[i:i + 3]
        keyboard.row(*row)

    keyboard.row(
        InlineKeyboardButton(text="🔙 Назад", callback_data="duel:settings")
    )

    return keyboard.as_markup()


def duel_stats_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура статистики дуэлей"""
    keyboard = InlineKeyboardBuilder()

    keyboard.row(
        InlineKeyboardButton(text="📈 Общая статистика", callback_data="duel:stats_general"),
        InlineKeyboardButton(text="🏆 История дуэлей", callback_data="duel:stats_history")
    )
    keyboard.row(
        InlineKeyboardButton(text="📊 По форматам", callback_data="duel:stats_formats"),
        InlineKeyboardButton(text="🎯 По категориям", callback_data="duel:stats_categories")
    )
    keyboard.row(
        InlineKeyboardButton(text="🔙 Назад", callback_data="menu:duels")
    )

    return keyboard.as_markup()


# ------------------- АДМИН-ПАНЕЛЬ КЛАВИАТУРЫ -------------------

def admin_main_keyboard() -> InlineKeyboardMarkup:
    """Главное меню админ-панели"""
    keyboard = InlineKeyboardBuilder()

    keyboard.row(
        InlineKeyboardButton(text="📝 Вопросы", callback_data="admin_questions"),
        InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users")
    )
    keyboard.row(
        InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats"),
        InlineKeyboardButton(text="📢 Рассылки", callback_data="admin_broadcast")
    )
    keyboard.row(
        InlineKeyboardButton(text="👑 Админы", callback_data="admin_manage_admins"),
        InlineKeyboardButton(text="💾 Бэкапы", callback_data="admin_backup")
    )
    keyboard.row(
        InlineKeyboardButton(text="📋 Логи", callback_data="admin_logs"),
        InlineKeyboardButton(text="⚡ Массовые операции", callback_data="admin_bulk_operations")
    )
    keyboard.row(
        InlineKeyboardButton(text="🔄 Системные операции", callback_data="admin_system"),
        InlineKeyboardButton(text="📊 Мониторинг", callback_data="admin_monitoring")
    )
    keyboard.row(
        InlineKeyboardButton(text="📈 Аналитика", callback_data="admin_analytics"),
        InlineKeyboardButton(text="⚙️ Настройки", callback_data="admin_settings")
    )
    keyboard.row(
        InlineKeyboardButton(text="🧪 Тестирование", callback_data="admin_testing"),
        InlineKeyboardButton(text="⚔️ Управление дуэлями", callback_data="admin_duels")
    )
    keyboard.row(
        InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:main")
    )

    return keyboard.as_markup()


def admin_questions_keyboard(show_pagination: bool = False, current_page: int = 0,
                             total_pages: int = 1) -> InlineKeyboardMarkup:
    """Клавиатура управления вопросами"""
    keyboard = InlineKeyboardBuilder()

    keyboard.row(
        InlineKeyboardButton(text="👁️ Просмотреть все", callback_data="admin_view_questions")
    )
    keyboard.row(
        InlineKeyboardButton(text="➕ Добавить вопрос", callback_data="admin_add_question"),
        InlineKeyboardButton(text="🗑️ Удалить вопрос", callback_data="admin_delete_question")
    )
    keyboard.row(
        InlineKeyboardButton(text="📤 Экспорт вопросов", callback_data="admin_export_questions"),
        InlineKeyboardButton(text="📥 Импорт вопросов", callback_data="admin_import_questions")
    )

    if show_pagination:
        pagination_buttons = []
        if current_page > 0:
            pagination_buttons.append(
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data=f"admin_page:{current_page - 1}"
                )
            )
        if current_page < total_pages - 1:
            pagination_buttons.append(
                InlineKeyboardButton(
                    text="Вперед ➡️",
                    callback_data=f"admin_page:{current_page + 1}"
                )
            )

        if pagination_buttons:
            keyboard.row(*pagination_buttons)

    keyboard.row(
        InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_main")
    )

    return keyboard.as_markup()


def admin_stats_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура статистики"""
    keyboard = InlineKeyboardBuilder()

    keyboard.row(
        InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_stats"),
        InlineKeyboardButton(text="📈 Детальная статистика", callback_data="admin_detailed_stats")
    )
    keyboard.row(
        InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_main")
    )

    return keyboard.as_markup()


def admin_users_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура управления пользователями"""
    keyboard = InlineKeyboardBuilder()

    keyboard.row(
        InlineKeyboardButton(text="📊 Общая статистика", callback_data="admin_users_stats"),
        InlineKeyboardButton(text="👤 Поиск пользователя", callback_data="admin_find_user")
    )
    keyboard.row(
        InlineKeyboardButton(text="⚡ Активные пользователи", callback_data="admin_active_users"),
        InlineKeyboardButton(text="🎯 Топ игроков", callback_data="admin_top_users")
    )
    keyboard.row(
        InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_main")
    )

    return keyboard.as_markup()


def admin_duels_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура управления дуэлями"""
    keyboard = InlineKeyboardBuilder()

    keyboard.row(
        InlineKeyboardButton(text="📊 Статистика дуэлей", callback_data="admin_duels_stats"),
        InlineKeyboardButton(text="👁️ Активные дуэли", callback_data="admin_active_duels")
    )
    keyboard.row(
        InlineKeyboardButton(text="🛑 Завершить все дуэли", callback_data="admin_stop_all_duels"),
        InlineKeyboardButton(text="🧹 Очистка дуэлей", callback_data="admin_cleanup_duels")
    )
    keyboard.row(
        InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_main")
    )

    return keyboard.as_markup()


def admin_broadcast_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура рассылки"""
    keyboard = InlineKeyboardBuilder()

    keyboard.row(
        InlineKeyboardButton(text="📢 Создать рассылку", callback_data="admin_broadcast_create"),
        InlineKeyboardButton(text="📊 Статистика рассылок", callback_data="admin_broadcast_stats")
    )
    keyboard.row(
        InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_main")
    )

    return keyboard.as_markup()


def admin_manage_admins_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура управления администраторами"""
    keyboard = InlineKeyboardBuilder()

    keyboard.row(
        InlineKeyboardButton(text="➕ Добавить админа", callback_data="admin_add_admin"),
        InlineKeyboardButton(text="🗑️ Удалить админа", callback_data="admin_remove_admin")
    )
    keyboard.row(
        InlineKeyboardButton(text="📋 Список админов", callback_data="admin_list_admins")
    )
    keyboard.row(
        InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_main")
    )

    return keyboard.as_markup()


def admin_backup_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура управления бэкапами"""
    keyboard = InlineKeyboardBuilder()

    keyboard.row(
        InlineKeyboardButton(text="📦 Создать бэкап", callback_data="admin_create_backup"),
        InlineKeyboardButton(text="🔄 Восстановить", callback_data="admin_restore_backup")
    )
    keyboard.row(
        InlineKeyboardButton(text="📋 Список бэкапов", callback_data="admin_list_backups")
    )
    keyboard.row(
        InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_main")
    )

    return keyboard.as_markup()


def admin_logs_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура просмотра логов"""
    keyboard = InlineKeyboardBuilder()

    keyboard.row(
        InlineKeyboardButton(text="📅 Сегодня", callback_data="admin_logs_today"),
        InlineKeyboardButton(text="📆 Последние 7 дней", callback_data="admin_logs_week")
    )
    keyboard.row(
        InlineKeyboardButton(text="🐛 Ошибки", callback_data="admin_logs_errors"),
        InlineKeyboardButton(text="📊 Статистика логов", callback_data="admin_logs_stats")
    )
    keyboard.row(
        InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_main")
    )

    return keyboard.as_markup()


def admin_bulk_operations_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура массовых операций"""
    keyboard = InlineKeyboardBuilder()

    keyboard.row(
        InlineKeyboardButton(text="🎯 Начислить XP всем", callback_data="admin_bulk_xp"),
        InlineKeyboardButton(text="🔄 Сбросить прогресс неактивным", callback_data="admin_bulk_reset")
    )
    keyboard.row(
        InlineKeyboardButton(text="🧹 Удалить неактивных", callback_data="admin_bulk_clean")
    )
    keyboard.row(
        InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_main")
    )

    return keyboard.as_markup()


def admin_monitoring_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура мониторинга"""
    keyboard = InlineKeyboardBuilder()

    keyboard.row(
        InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_monitoring")
    )
    keyboard.row(
        InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_main")
    )

    return keyboard.as_markup()


def admin_analytics_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура аналитики"""
    keyboard = InlineKeyboardBuilder()

    keyboard.row(
        InlineKeyboardButton(text="📅 По дням", callback_data="admin_analytics_daily"),
        InlineKeyboardButton(text="📊 Графики", callback_data="admin_analytics_charts")
    )
    keyboard.row(
        InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_main")
    )

    return keyboard.as_markup()


def admin_settings_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура настроек бота"""
    keyboard = InlineKeyboardBuilder()

    keyboard.row(
        InlineKeyboardButton(text="📝 Настройки вопросов", callback_data="admin_settings_questions"),
        InlineKeyboardButton(text="🎮 Настройки игры", callback_data="admin_settings_game")
    )
    keyboard.row(
        InlineKeyboardButton(text="🔔 Уведомления", callback_data="admin_settings_notifications"),
        InlineKeyboardButton(text="🌐 Язык", callback_data="admin_settings_language")
    )
    keyboard.row(
        InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_main")
    )

    return keyboard.as_markup()


def admin_testing_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура тестирования"""
    keyboard = InlineKeyboardBuilder()

    keyboard.row(
        InlineKeyboardButton(text="🔍 Тест базы данных", callback_data="admin_test_db"),
        InlineKeyboardButton(text="📨 Тест уведомлений", callback_data="admin_test_notify")
    )
    keyboard.row(
        InlineKeyboardButton(text="🎮 Тест игры", callback_data="admin_test_game"),
        InlineKeyboardButton(text="📊 Тест аналитики", callback_data="admin_test_analytics")
    )
    keyboard.row(
        InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_main")
    )

    return keyboard.as_markup()


def get_back_to_admin_keyboard(target_menu: str = "admin_main") -> InlineKeyboardMarkup:
    """Клавиатура для возврата в админ-меню"""
    keyboard = InlineKeyboardBuilder()

    keyboard.row(
        InlineKeyboardButton(text="❌ Отмена", callback_data=target_menu)
    )

    return keyboard.as_markup()


def admin_confirm_broadcast_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура подтверждения рассылки"""
    keyboard = InlineKeyboardBuilder()

    keyboard.row(
        InlineKeyboardButton(text="✅ Отправить", callback_data="confirm_broadcast"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_broadcast")
    )

    return keyboard.as_markup()


def admin_pagination_keyboard(current_page: int, total_pages: int, prefix: str = "admin",
                              additional_buttons: List[InlineKeyboardButton] = None) -> InlineKeyboardMarkup:
    """Улучшенная клавиатура пагинации с дополнительными кнопками"""
    keyboard = InlineKeyboardBuilder()

    buttons = []

    if current_page > 0:
        buttons.append(
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=f"{prefix}_page:{current_page - 1}"
            )
        )

    buttons.append(
        InlineKeyboardButton(
            text=f"📄 {current_page + 1}/{total_pages}",
            callback_data="no_action"
        )
    )

    if current_page < total_pages - 1:
        buttons.append(
            InlineKeyboardButton(
                text="Вперед ➡️",
                callback_data=f"{prefix}_page:{current_page + 1}"
            )
        )

    keyboard.row(*buttons)

    # Добавляем дополнительные кнопки если есть
    if additional_buttons:
        keyboard.row(*additional_buttons)

    return keyboard.as_markup()


def admin_system_keyboard():
    """Клавиатура для системных операций"""
    keyboard = InlineKeyboardBuilder()

    keyboard.button(text="🔄 Полный сброс пользователей", callback_data="admin_full_reset")
    keyboard.button(text="⬅️ Назад в главное меню", callback_data="admin_main")

    keyboard.adjust(1)
    return keyboard.as_markup()

# ------------------- ДОПОЛНИТЕЛЬНЫЕ УЛУЧШЕНИЯ -------------------

def get_empty_keyboard() -> InlineKeyboardMarkup:
    """Пустая клавиатура (убирает предыдущую)"""
    return InlineKeyboardMarkup(inline_keyboard=[])


def get_loading_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с одной кнопкой загрузки"""
    keyboard = InlineKeyboardBuilder()
    keyboard.row(
        InlineKeyboardButton(text="⏳ Загрузка...", callback_data="no_action")
    )
    return keyboard.as_markup()


def cancel_keyboard(cancel_data: str = "menu:main") -> InlineKeyboardMarkup:
    """Простая клавиатура для отмены действия"""
    keyboard = InlineKeyboardBuilder()
    keyboard.row(
        InlineKeyboardButton(text="❌ Отмена", callback_data=cancel_data)
    )
    return keyboard.as_markup()


def settings_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура настроек"""
    keyboard = InlineKeyboardBuilder()

    keyboard.row(
        InlineKeyboardButton(text="🔔 Уведомления", callback_data="settings:notifications"),
        InlineKeyboardButton(text="🎨 Тема", callback_data="settings:theme")
    )
    keyboard.row(
        InlineKeyboardButton(text="🌐 Язык", callback_data="settings:language"),
        InlineKeyboardButton(text="📱 Интерфейс", callback_data="settings:interface")
    )
    keyboard.row(
        InlineKeyboardButton(text="🔙 Назад", callback_data="menu:main")
    )


    return keyboard.as_markup()

def admin_system_operations_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура системных операций"""
    keyboard = InlineKeyboardBuilder()

    keyboard.row(
        InlineKeyboardButton(text="🔄 Полный сброс пользователей", callback_data="admin_full_reset"),
        InlineKeyboardButton(text="🧹 Очистить тестовых", callback_data="admin_clean_testers")
    )
    keyboard.row(
        InlineKeyboardButton(text="📊 Сбросить статистику", callback_data="admin_reset_stats"),
        InlineKeyboardButton(text="⚔️ Сбросить дуэли", callback_data="admin_reset_duels")
    )
    keyboard.row(
        InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_main")
    )

    return keyboard.as_markup()