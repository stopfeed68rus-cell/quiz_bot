import logging
import json
import datetime
import io
from pathlib import Path
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from questions import QUESTIONS
from db import db
from aiogram import exceptions
from keyboards import (
    admin_main_keyboard,
    admin_questions_keyboard,
    admin_stats_keyboard,
    admin_users_keyboard,
    admin_broadcast_keyboard,
    admin_manage_admins_keyboard,
    admin_backup_keyboard,
    admin_logs_keyboard,
    admin_bulk_operations_keyboard,
    admin_monitoring_keyboard,
    admin_analytics_keyboard,
    admin_settings_keyboard,
    admin_testing_keyboard,
    confirmation_keyboard,
    get_back_to_admin_keyboard,
    admin_system_operations_keyboard  # ← ДОБАВЬТЕ ЭТУ СТРОКУ
)

logger = logging.getLogger(__name__)


# ------------------- FSM состояния для админки -------------------
class AdminStates(StatesGroup):
    adding_question = State()
    editing_question = State()
    deleting_question = State()
    broadcasting = State()
    managing_user = State()
    searching_user = State()
    adding_admin = State()
    removing_admin = State()
    bulk_xp = State()
    bulk_reset = State()


class QuestionStates(StatesGroup):
    waiting_for_question = State()
    waiting_for_options = State()
    waiting_for_correct_answer = State()


# ------------------- Роутер админки -------------------
admin_router = Router()

# Список администраторов (можно вынести в базу данных)
ADMIN_IDS = [812857335]  # Замените на реальные ID


# ------------------- Проверка прав администратора -------------------
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# ------------------- Уведомления администраторов -------------------
async def notify_admins(bot, message: str):
    """Отправляет уведомление всем администраторам"""
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, f"🔔 {message}")
        except Exception as e:
            logger.error(f"Failed to notify admin {admin_id}: {e}")


# ------------------- Команда админки -------------------
@admin_router.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав доступа к админ-панели")
        return

    text = (
        "🛠️ <b>Панель администратора</b>\n\n"
        "Выберите раздел для управления:"
    )

    await message.answer(
        text,
        reply_markup=admin_main_keyboard(),
        parse_mode="HTML"
    )


# ------------------- Главное меню админки -------------------
@admin_router.callback_query(F.data == "admin_main")
async def admin_main_menu(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав доступа", show_alert=True)
        return

    text = (
        "🛠️ <b>Панель администратора</b>\n\n"
        "Выберите раздел для управления:"
    )

    await callback.message.edit_text(
        text,
        reply_markup=admin_main_keyboard(),
        parse_mode="HTML"
    )


# ------------------- Управление вопросами -------------------
@admin_router.callback_query(F.data == "admin_questions")
async def admin_questions(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав доступа", show_alert=True)
        return

    total_questions = len(QUESTIONS)

    text = (
        f"📝 <b>Управление вопросами</b>\n\n"
        f"📊 Всего вопросов в базе: <b>{total_questions}</b>\n\n"
        f"Выберите действие:"
    )

    await callback.message.edit_text(
        text,
        reply_markup=admin_questions_keyboard(),
        parse_mode="HTML"
    )


# ------------------- Просмотр всех вопросов -------------------
@admin_router.callback_query(F.data == "admin_view_questions")
async def admin_view_questions(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав доступа", show_alert=True)
        return

    if not QUESTIONS:
        text = "📝 <b>Список вопросов</b>\n\n❌ В базе нет вопросов"
        await callback.message.edit_text(text, parse_mode="HTML")
        return

    # Показываем первые 5 вопросов с пагинацией
    await show_questions_page(callback, 0)


async def show_questions_page(callback: types.CallbackQuery, page: int):
    questions_per_page = 5
    start_idx = page * questions_per_page
    end_idx = start_idx + questions_per_page
    page_questions = QUESTIONS[start_idx:end_idx]

    text = f"📝 <b>Список вопросов (стр. {page + 1})</b>\n\n"

    for i, q in enumerate(page_questions, start_idx + 1):
        text += f"<b>{i}. {q['question'][:50]}...</b>\n"
        text += f"   Ответ: {q['answer']}\n"
        text += f"   Варианты: {', '.join(q['options'][:2])}...\n\n"

    total_pages = (len(QUESTIONS) + questions_per_page - 1) // questions_per_page

    await callback.message.edit_text(
        text,
        reply_markup=admin_questions_keyboard(show_pagination=True,
                                              current_page=page,
                                              total_pages=total_pages),
        parse_mode="HTML"
    )


# ------------------- Добавление вопроса -------------------
@admin_router.callback_query(F.data == "admin_add_question")
async def admin_add_question_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав доступа", show_alert=True)
        return

    await state.set_state(QuestionStates.waiting_for_question)

    text = (
        "📝 <b>Добавление нового вопроса</b>\n\n"
        "Введите текст вопроса:"
    )

    await callback.message.edit_text(
        text,
        reply_markup=get_back_to_admin_keyboard("admin_questions"),
        parse_mode="HTML"
    )


@admin_router.message(QuestionStates.waiting_for_question)
async def process_question_text(message: types.Message, state: FSMContext):
    await state.update_data(question=message.text)
    await state.set_state(QuestionStates.waiting_for_options)

    text = (
        "📋 Теперь введите варианты ответов.\n\n"
        "<b>Формат:</b> каждый вариант с новой строки\n"
        "<b>Пример:</b>\n"
        "Вариант А\n"
        "Вариант Б\n"
        "Вариант В\n"
        "Вариант Г"
    )

    await message.answer(
        text,
        reply_markup=get_back_to_admin_keyboard("admin_questions"),
        parse_mode="HTML"
    )


@admin_router.message(QuestionStates.waiting_for_options)
async def process_question_options(message: types.Message, state: FSMContext):
    options = [opt.strip() for opt in message.text.split('\n') if opt.strip()]

    if len(options) < 2:
        await message.answer("❌ Нужно как минимум 2 варианта ответа")
        return

    await state.update_data(options=options)
    await state.set_state(QuestionStates.waiting_for_correct_answer)

    options_text = "\n".join([f"{i + 1}. {opt}" for i, opt in enumerate(options)])

    text = (
        f"✅ Варианты сохранены:\n\n{options_text}\n\n"
        f"Теперь введите <b>номер правильного ответа</b> (1-{len(options)}):"
    )

    await message.answer(
        text,
        reply_markup=get_back_to_admin_keyboard("admin_questions"),
        parse_mode="HTML"
    )


@admin_router.message(QuestionStates.waiting_for_correct_answer)
async def process_correct_answer(message: types.Message, state: FSMContext):
    try:
        correct_idx = int(message.text.strip()) - 1
        data = await state.get_data()

        if correct_idx < 0 or correct_idx >= len(data['options']):
            await message.answer(f"❌ Номер должен быть от 1 до {len(data['options'])}")
            return

        correct_answer = data['options'][correct_idx]

        # Добавляем вопрос в базу
        new_question = {
            "question": data['question'],
            "options": data['options'],
            "answer": correct_answer
        }

        QUESTIONS.append(new_question)

        # TODO: Сохранить вопросы в базу данных/файл
        await save_questions_to_db()

        text = (
            f"✅ <b>Вопрос успешно добавлен!</b>\n\n"
            f"<b>Вопрос:</b> {data['question']}\n"
            f"<b>Правильный ответ:</b> {correct_answer}\n"
            f"<b>Всего вопросов:</b> {len(QUESTIONS)}"
        )

        await message.answer(
            text,
            reply_markup=admin_questions_keyboard(),
            parse_mode="HTML"
        )

        await state.clear()

    except ValueError:
        await message.answer("❌ Пожалуйста, введите число")
    except Exception as e:
        logger.error(f"Error adding question: {e}")
        await message.answer("❌ Ошибка при добавлении вопроса")


async def save_questions_to_db():
    """Сохраняет вопросы в базу данных или файл"""
    # TODO: Реализовать сохранение вопросов
    # Например: await db.save_questions(QUESTIONS)
    pass


# ------------------- Удаление вопроса -------------------
@admin_router.callback_query(F.data == "admin_delete_question")
async def admin_delete_question_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав доступа", show_alert=True)
        return

    if not QUESTIONS:
        await callback.answer("❌ В базе нет вопросов", show_alert=True)
        return

    await state.set_state(AdminStates.deleting_question)

    text = (
        "🗑️ <b>Удаление вопроса</b>\n\n"
        "Введите номер вопроса для удаления:"
    )

    await callback.message.edit_text(
        text,
        reply_markup=get_back_to_admin_keyboard("admin_questions"),
        parse_mode="HTML"
    )


@admin_router.message(AdminStates.deleting_question)
async def process_delete_question(message: types.Message, state: FSMContext):
    try:
        question_num = int(message.text.strip())

        if question_num < 1 or question_num > len(QUESTIONS):
            await message.answer(f"❌ Номер должен быть от 1 до {len(QUESTIONS)}")
            return

        # Удаляем вопрос
        deleted_question = QUESTIONS.pop(question_num - 1)
        await save_questions_to_db()

        text = (
            f"✅ <b>Вопрос удален!</b>\n\n"
            f"<b>Удаленный вопрос:</b> {deleted_question['question'][:100]}...\n"
            f"<b>Осталось вопросов:</b> {len(QUESTIONS)}"
        )

        await message.answer(
            text,
            reply_markup=admin_questions_keyboard(),
            parse_mode="HTML"
        )

        await state.clear()

    except ValueError:
        await message.answer("❌ Пожалуйста, введите число")
    except Exception as e:
        logger.error(f"Error deleting question: {e}")
        await message.answer("❌ Ошибка при удалении вопроса")


# ------------------- Статистика бота -------------------
@admin_router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав доступа", show_alert=True)
        return

    try:
        # Получаем статистику из базы данных
        total_users = await db.get_total_users_count()
        active_today = await db.get_active_users_count(1)  # Активные за сегодня
        active_week = await db.get_active_users_count(7)  # Активные за неделю
        total_questions = len(QUESTIONS)
        top_users = await db.get_top_users(5)

        text = (
            f"📊 <b>Статистика бота</b>\n\n"
            f"👥 <b>Пользователи:</b>\n"
            f"• Всего: {total_users}\n"
            f"• Активных за сегодня: {active_today}\n"
            f"• Активных за неделю: {active_week}\n\n"
            f"📝 <b>Вопросы:</b> {total_questions}\n\n"
            f"🏆 <b>Топ-5 игроков:</b>\n"
        )

        for i, user in enumerate(top_users, 1):
            username = user.get('username', 'Аноним')
            level = user.get('level', 1)
            xp = user.get('xp', 0)
            text += f"{i}. {username} - Ур. {level} ({xp} XP)\n"

        await callback.message.edit_text(
            text,
            reply_markup=admin_stats_keyboard(),
            parse_mode="HTML"
        )

    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        await callback.answer("❌ Ошибка получения статистики", show_alert=True)


# ------------------- Рассылка сообщений -------------------
@admin_router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_menu(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав доступа", show_alert=True)
        return

    text = (
        "📢 <b>Управление рассылок</b>\n\n"
        "Выберите действие для работы с рассылками:"
    )

    await callback.message.edit_text(
        text,
        reply_markup=admin_broadcast_keyboard(),
        parse_mode="HTML"
    )


@admin_router.callback_query(F.data == "admin_broadcast_create")
async def admin_broadcast_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав доступа", show_alert=True)
        return

    await state.set_state(AdminStates.broadcasting)

    text = (
        "📢 <b>Создание рассылки</b>\n\n"
        "Введите сообщение для рассылки всем пользователям:"
    )

    await callback.message.edit_text(
        text,
        reply_markup=get_back_to_admin_keyboard("admin_broadcast"),
        parse_mode="HTML"
    )


@admin_router.message(AdminStates.broadcasting)
async def process_broadcast_message(message: types.Message, state: FSMContext):
    broadcast_text = message.text

    # Запрашиваем подтверждение
    text = (
        f"📢 <b>Подтверждение рассылки</b>\n\n"
        f"<b>Сообщение:</b>\n{broadcast_text}\n\n"
        f"Отправить это сообщение всем пользователям?"
    )

    await message.answer(
        text,
        reply_markup=confirmation_keyboard(
            confirm_data="confirm_broadcast",
            cancel_data="cancel_broadcast"
        ),
        parse_mode="HTML"
    )

    await state.update_data(broadcast_text=broadcast_text)


@admin_router.callback_query(F.data == "confirm_broadcast")
async def confirm_broadcast(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    broadcast_text = data.get('broadcast_text', '')

    if not broadcast_text:
        await callback.answer("❌ Текст рассылки не найден", show_alert=True)
        return

    # Получаем всех пользователей
    all_users = await db.get_all_users()
    sent_count = 0
    failed_count = 0

    # Показываем уведомление о начале рассылки
    await callback.message.edit_text("📤 <b>Начинаю рассылку...</b>", parse_mode="HTML")

    # Отправляем сообщение каждому пользователю
    for user in all_users:
        try:
            await callback.bot.send_message(
                chat_id=user['user_id'],
                text=broadcast_text
            )
            sent_count += 1
        except Exception as e:
            logger.error(f"Failed to send broadcast to {user['user_id']}: {e}")
            failed_count += 1

    text = (
        f"✅ <b>Рассылка завершена!</b>\n\n"
        f"• 📤 Отправлено: {sent_count}\n"
        f"• ❌ Ошибок: {failed_count}\n"
        f"• 👥 Всего: {len(all_users)}"
    )

    await callback.message.edit_text(
        text,
        reply_markup=admin_main_keyboard(),
        parse_mode="HTML"
    )

    await state.clear()


@admin_router.callback_query(F.data == "cancel_broadcast")
async def cancel_broadcast(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await admin_main_menu(callback)


# ------------------- Пагинация вопросов -------------------
@admin_router.callback_query(F.data.startswith("admin_page:"))
async def admin_questions_pagination(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав доступа", show_alert=True)
        return

    try:
        page = int(callback.data.split(":")[1])
        await show_questions_page(callback, page)
    except (ValueError, IndexError):
        await callback.answer("❌ Ошибка пагинации", show_alert=True)


# ------------------- Экспорт вопросов -------------------
@admin_router.callback_query(F.data == "admin_export_questions")
async def admin_export_questions(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав доступа", show_alert=True)
        return

    # Создаем текстовый файл с вопросами
    questions_data = {
        "total_questions": len(QUESTIONS),
        "questions": QUESTIONS
    }

    # Создаем файл в памяти
    file_buffer = io.BytesIO()
    file_buffer.write(json.dumps(questions_data, ensure_ascii=False, indent=2).encode('utf-8'))
    file_buffer.seek(0)

    # Отправляем файл
    await callback.message.answer_document(
        types.BufferedInputFile(
            file_buffer.read(),
            filename="quiz_questions_export.json"
        ),
        caption=f"📊 Экспорт вопросов\nВсего вопросов: {len(QUESTIONS)}"
    )

    await callback.answer("✅ Файл экспортирован")


# ------------------- Управление пользователями -------------------
@admin_router.callback_query(F.data == "admin_users")
async def admin_users(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав доступа", show_alert=True)
        return

    text = (
        "👥 <b>Управление пользователями</b>\n\n"
        "Выберите действие для работы с пользователями:"
    )

    await callback.message.edit_text(
        text,
        reply_markup=admin_users_keyboard(),
        parse_mode="HTML"
    )


# ------------------- ПОИСК ПОЛЬЗОВАТЕЛЯ ------------------- #
@admin_router.callback_query(F.data == "admin_find_user")
async def admin_find_user_start(callback: types.CallbackQuery, state: FSMContext):
    """Начало поиска пользователя"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав доступа", show_alert=True)
        return

    await state.set_state(AdminStates.searching_user)

    text = (
        "🔍 <b>Поиск пользователя</b>\n\n"
        "Введите данные для поиска:\n"
        "• ID пользователя\n"
        "• Имя пользователя (username)\n"
        "• Имя (first_name)\n\n"
        "<b>Примеры:</b>\n"
        "<code>812857335</code> - поиск по ID\n"
        "<code>username</code> - поиск по юзернейму\n"
        "<code>Иван</code> - поиск по имени"
    )

    await callback.message.edit_text(
        text,
        reply_markup=get_back_to_admin_keyboard("admin_users"),
        parse_mode="HTML"
    )


@admin_router.message(AdminStates.searching_user)
async def admin_find_user_process(message: types.Message, state: FSMContext):
    """Обработка поиска пользователя"""
    search_query = message.text.strip()

    try:
        # Если поиск по ID
        if search_query.isdigit():
            user_id = int(search_query)
            user = await db.get_user(user_id)
            users = [user] if user and user.get('user_id') else []
        else:
            # Поиск по username
            users = await db.search_users(search_query)

        if not users:
            await message.answer(
                f"❌ Пользователи по запросу <code>{search_query}</code> не найдены",
                parse_mode="HTML",
                reply_markup=get_back_to_admin_keyboard("admin_users")
            )
            return

        # Если найден один пользователь - показываем детальную информацию
        if len(users) == 1:
            await show_user_details(message, users[0])
        else:
            # Если найдено несколько пользователей - показываем список
            await show_users_list(message, users, search_query)

        await state.clear()

    except Exception as e:
        logger.error(f"Error searching user: {e}")
        await message.answer(
            "❌ Ошибка при поиске пользователя",
            reply_markup=get_back_to_admin_keyboard("admin_users")
        )


async def show_user_details(message: types.Message, user: dict):
    """Показывает детальную информацию о пользователе"""
    user_id = user['user_id']
    username = user.get('username', 'Не установлен')
    level = user.get('level', 1)
    xp = user.get('xp', 0)
    created_at = user.get('created_at', 'Неизвестно')

    # Получаем детальную статистику пользователя
    try:
        user_stats = await db.get_user_detailed_stats(user_id)
        total_answers = user_stats.get('total_answers', 0)
        correct_answers = user_stats.get('correct_answers', 0)
        accuracy = user_stats.get('accuracy', 0)
        achievements_count = user_stats.get('achievements_count', 0)
    except (AttributeError, KeyError, ValueError, TypeError) as e:
        # Ловим только конкретные ошибки данных
        logger.debug(f"Не удалось получить детальную статистику для пользователя {user_id}: {e}")
        total_answers = 0
        correct_answers = 0
        accuracy = 0
        achievements_count = 0
    except Exception as e:
        # Ловим остальные ошибки с логированием
        logger.error(f"Ошибка при получении статистики пользователя {user_id}: {e}")
        total_answers = 0
        correct_answers = 0
        accuracy = 0
        achievements_count = 0

    text = (
        f"👤 <b>Информация о пользователе</b>\n\n"
        f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
        f"👤 <b>Username:</b> @{username}\n"
        f"🎯 <b>Уровень:</b> {level}\n"
        f"⭐ <b>XP:</b> {xp}\n"
        f"📅 <b>Регистрация:</b> {created_at}\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"• Ответов: {total_answers}\n"
        f"• Правильных: {correct_answers}\n"
        f"• Точность: {accuracy}%\n"
        f"• Достижений: {achievements_count}\n\n"
        f"Выберите действие:"
    )

    keyboard = InlineKeyboardBuilder()
    keyboard.row(InlineKeyboardButton(text="✏️ Изменить уровень", callback_data=f"admin_user_level:{user_id}"))
    keyboard.row(InlineKeyboardButton(text="🎯 Изменить XP", callback_data=f"admin_user_xp:{user_id}"))
    keyboard.row(InlineKeyboardButton(text="🔄 Сбросить прогресс", callback_data=f"admin_user_reset:{user_id}"))
    keyboard.row(InlineKeyboardButton(text="🔍 Новый поиск", callback_data="admin_find_user"))
    keyboard.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_users"))

    await message.answer(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")


async def show_users_list(message: types.Message, users: list, search_query: str):
    """Показывает список найденных пользователей"""
    text = f"🔍 <b>Результаты поиска: '{search_query}'</b>\n\n"
    text += f"📋 Найдено пользователей: <b>{len(users)}</b>\n\n"

    for i, user in enumerate(users[:10], 1):  # Ограничиваем 10 пользователями
        user_id = user['user_id']
        username = user.get('username', 'нет username')
        level = user.get('level', 1)
        xp = user.get('xp', 0)

        text += f"<b>{i}. @{username}</b>\n"
        text += f"   🆔 <code>{user_id}</code> | 🎯 Ур. {level} | ⭐ {xp} XP\n\n"

    if len(users) > 10:
        text += f"<b>... и еще {len(users) - 10} пользователей</b>"

    keyboard = InlineKeyboardBuilder()

    # Кнопки для первых 5 пользователей
    for i, user in enumerate(users[:5]):
        username = user.get('username', f"User{user['user_id']}")
        keyboard.row(InlineKeyboardButton(
            text=f"👤 {username[:15]}",
            callback_data=f"admin_user_select:{user['user_id']}"
        ))

    keyboard.row(InlineKeyboardButton(text="🔍 Новый поиск", callback_data="admin_find_user"))
    keyboard.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_users"))

    await message.answer(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")


@admin_router.callback_query(F.data.startswith("admin_user_select:"))
async def admin_user_select(callback: types.CallbackQuery):
    """Обработка выбора пользователя из списка"""
    user_id = int(callback.data.split(":")[1])

    try:
        user = await db.get_user(user_id)
        if user:
            await callback.message.delete()  # Удаляем список
            await show_user_details(callback.message, user)
        else:
            await callback.answer("❌ Пользователь не найден", show_alert=True)
    except Exception as e:
        logger.error(f"Error selecting user: {e}")
        await callback.answer("❌ Ошибка при загрузке пользователя", show_alert=True)


@admin_router.callback_query(F.data == "admin_top_users")
async def admin_top_users(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав доступа", show_alert=True)
        return

    top_users = await db.get_top_users(20)

    text = "🏆 <b>Топ 20 игроков</b>\n\n"

    for i, user in enumerate(top_users, 1):
        username = user.get('username', 'Аноним')
        level = user.get('level', 1)
        xp = user.get('xp', 0)
        text += f"{i}. {username} - Ур. {level} ({xp} XP)\n"

    await callback.message.edit_text(
        text,
        reply_markup=admin_users_keyboard(),
        parse_mode="HTML"
    )


# ------------------- ИЗМЕНЕНИЕ УРОВНЯ ПОЛЬЗОВАТЕЛЯ -------------------
@admin_router.callback_query(F.data.startswith("admin_user_level:"))
async def admin_user_level(callback: types.CallbackQuery, state: FSMContext):
    """Начало изменения уровня пользователя"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав доступа", show_alert=True)
        return

    user_id = int(callback.data.split(":")[1])

    # Сохраняем данные в FSM
    await state.set_state(AdminStates.managing_user)
    await state.update_data(
        managed_user_id=user_id,
        action="level"
    )

    await callback.message.answer("✏️ Введите новый уровень (1-100):")
    await callback.answer()


# ------------------- ИЗМЕНЕНИЕ XP ПОЛЬЗОВАТЕЛЯ -------------------
@admin_router.callback_query(F.data.startswith("admin_user_xp:"))
async def admin_user_xp(callback: types.CallbackQuery, state: FSMContext):
    """Начало изменения XP пользователя"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав доступа", show_alert=True)
        return

    user_id = int(callback.data.split(":")[1])

    # Сохраняем данные в FSM
    await state.set_state(AdminStates.managing_user)
    await state.update_data(
        managed_user_id=user_id,
        action="xp"
    )

    await callback.message.answer("🎯 Введите новое количество XP:")
    await callback.answer()


# ------------------- ОБРАБОТКА ИЗМЕНЕНИЯ УРОВНЯ/XP -------------------
@admin_router.message(AdminStates.managing_user)
async def admin_user_update(message: types.Message, state: FSMContext):
    """Обработка изменения уровня или XP пользователя"""
    if not is_admin(message.from_user.id):
        await message.answer("❌ Нет прав доступа")
        return

    # Получаем данные из FSM
    data = await state.get_data()
    managed_user_id = data.get('managed_user_id')
    action = data.get('action')

    if not managed_user_id or not action:
        await message.answer("❌ Сессия истекла. Начните управление пользователем заново.")
        await state.clear()
        return

    try:
        new_value = int(message.text.strip())

        if action == "level":
            if new_value < 1 or new_value > 100:
                await message.answer("❌ Уровень должен быть от 1 до 100")
                return

            success = await db.update_user_level(managed_user_id, new_value)

            if success:
                await message.answer(f"✅ Уровень пользователя изменен на {new_value}")

                # Показываем обновленную информацию о пользователе
                user = await db.get_user(managed_user_id)
                if user:
                    await show_user_details(message, user)
                else:
                    await message.answer("❌ Пользователь не найден")
            else:
                await message.answer("❌ Ошибка при обновлении уровня")

        elif action == "xp":
            if new_value < 0:
                await message.answer("❌ XP не может быть отрицательным")
                return

            success = await db.update_user_xp(managed_user_id, new_value)

            if success:
                await message.answer(f"✅ XP пользователя изменен на {new_value}")

                # Показываем обновленную информацию о пользователе
                user = await db.get_user(managed_user_id)
                if user:
                    await show_user_details(message, user)
                else:
                    await message.answer("❌ Пользователь не найден")
            else:
                await message.answer("❌ Ошибка при обновлении XP")

        else:
            await message.answer("❌ Неизвестное действие")
            return

        await state.clear()

    except ValueError:
        await message.answer("❌ Пожалуйста, введите число")
        return
    except Exception as e:
        logger.error(f"Error updating user {managed_user_id}: {e}")
        await message.answer("❌ Ошибка при обновлении пользователя")
        await state.clear()


# ------------------- СБРОС ПРОГРЕССА ПОЛЬЗОВАТЕЛЯ -------------------
@admin_router.callback_query(F.data.startswith("admin_user_reset:"))
async def admin_user_reset(callback: types.CallbackQuery):
    """Сброс прогресса пользователя"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав доступа", show_alert=True)
        return

    user_id = int(callback.data.split(":")[1])

    # Запрашиваем подтверждение
    text = (
        f"🔄 <b>Сброс прогресса пользователя</b>\n\n"
        f"Вы уверены, что хотите сбросить прогресс пользователя {user_id}?\n"
        f"Это действие нельзя отменить!"
    )

    keyboard = InlineKeyboardBuilder()
    keyboard.row(InlineKeyboardButton(
        text="✅ Да, сбросить",
        callback_data=f"admin_user_reset_confirm:{user_id}"
    ))
    keyboard.row(InlineKeyboardButton(
        text="❌ Отмена",
        callback_data=f"admin_user_select:{user_id}"
    ))

    await callback.message.edit_text(
        text,
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML"
    )


@admin_router.callback_query(F.data.startswith("admin_user_reset_confirm:"))
async def admin_user_reset_confirm(callback: types.CallbackQuery):
    """Подтверждение сброса прогресса"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав доступа", show_alert=True)
        return

    user_id = int(callback.data.split(":")[1])

    try:
        # Сбрасываем прогресс пользователя
        success = await db.reset_user_progress(user_id)

        if success:
            await callback.message.edit_text(
                f"✅ Прогресс пользователя {user_id} успешно сброшен!",
                parse_mode="HTML"
            )

            # Показываем обновленную информацию о пользователе
            user = await db.get_user(user_id)
            if user:
                await show_user_details(callback.message, user)
        else:
            await callback.message.edit_text(
                "❌ Ошибка при сбросе прогресса пользователя",
                parse_mode="HTML"
            )

    except Exception as e:
        logger.error(f"Error resetting user progress {user_id}: {e}")
        await callback.message.edit_text(
            "❌ Ошибка при сбросе прогресса пользователя",
            parse_mode="HTML"
        )


# ------------------- УПРАВЛЕНИЕ АДМИНИСТРАТОРАМИ -------------------
@admin_router.callback_query(F.data == "admin_manage_admins")
async def admin_manage_admins(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав доступа", show_alert=True)
        return

    text = (
        "👑 <b>Управление администраторами</b>\n\n"
        f"Текущие администраторы: {len(ADMIN_IDS)}\n\n"
        "Выберите действие:"
    )

    await callback.message.edit_text(
        text,
        reply_markup=admin_manage_admins_keyboard(),
        parse_mode="HTML"
    )


@admin_router.callback_query(F.data == "admin_list_admins")
async def admin_list_admins(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав доступа", show_alert=True)
        return

    text = "👑 <b>Список администраторов</b>\n\n"

    for i, admin_id in enumerate(ADMIN_IDS, 1):
        try:
            user = await callback.bot.get_chat(admin_id)
            username = f"@{user.username}" if user.username else "Нет username"
            first_name = user.first_name or "Неизвестно"
            text += f"{i}. {first_name} ({username}) - ID: <code>{admin_id}</code>\n"
        except (exceptions.TelegramBadRequest, exceptions.TelegramForbiddenError, exceptions.TelegramNotFound):
            # Бот не может получить информацию о пользователе
            text += f"{i}. ID: <code>{admin_id}</code> (не доступен)\n"
        except Exception as e:
            # Логируем неожиданные ошибки, но продолжаем работу
            logger.warning(f"Unexpected error getting admin info for {admin_id}: {e}")
            text += f"{i}. ID: <code>{admin_id}</code> (ошибка получения)\n"

    keyboard = InlineKeyboardBuilder()
    keyboard.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_manage_admins"))

    await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")


@admin_router.callback_query(F.data == "admin_add_admin")
async def admin_add_admin_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав доступа", show_alert=True)
        return

    await state.set_state(AdminStates.adding_admin)

    text = (
        "➕ <b>Добавление администратора</b>\n\n"
        "Введите ID пользователя, которого хотите сделать администратором:"
    )

    keyboard = InlineKeyboardBuilder()
    keyboard.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_manage_admins"))

    await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")


@admin_router.message(AdminStates.adding_admin)
async def admin_add_admin_process(message: types.Message, state: FSMContext):
    try:
        new_admin_id = int(message.text.strip())

        if new_admin_id in ADMIN_IDS:
            await message.answer("❌ Этот пользователь уже является администратором")
            return

        ADMIN_IDS.append(new_admin_id)

        # Уведомляем нового админа
        try:
            await message.bot.send_message(
                new_admin_id,
                "🎉 Вам были предоставлены права администратора бота!\n\n"
                "Используйте команду /admin для доступа к панели управления."
            )
        except (exceptions.TelegramBadRequest, exceptions.TelegramForbiddenError, exceptions.TelegramNotFound):
            # Пользователь заблокировал бота или не найден
            logger.info(f"Не удалось отправить уведомление новому админу {new_admin_id}")
        except Exception as e:
            # Логируем другие ошибки, но не прерываем процесс
            logger.warning(f"Ошибка при отправке уведомления админу {new_admin_id}: {e}")

        await message.answer(
            f"✅ Пользователь <code>{new_admin_id}</code> добавлен в администраторы",
            parse_mode="HTML"
        )

        await state.clear()

    except ValueError:
        await message.answer("❌ Пожалуйста, введите корректный ID пользователя (число)")


@admin_router.callback_query(F.data == "admin_remove_admin")
async def admin_remove_admin_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав доступа", show_alert=True)
        return

    await state.set_state(AdminStates.removing_admin)

    text = (
        "🗑️ <b>Удаление администратора</b>\n\n"
        "Введите ID администратора, которого хотите удалить:"
    )

    keyboard = InlineKeyboardBuilder()
    keyboard.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_manage_admins"))

    await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")


@admin_router.message(AdminStates.removing_admin)
async def admin_remove_admin_process(message: types.Message, state: FSMContext):
    try:
        remove_admin_id = int(message.text.strip())

        if remove_admin_id not in ADMIN_IDS:
            await message.answer("❌ Этот пользователь не является администратором")
            return

        if len(ADMIN_IDS) <= 1:
            await message.answer("❌ Нельзя удалить последнего администратора")
            return

        ADMIN_IDS.remove(remove_admin_id)

        await message.answer(
            f"✅ Пользователь <code>{remove_admin_id}</code> удален из администраторов",
            parse_mode="HTML"
        )

        await state.clear()

    except ValueError:
        await message.answer("❌ Пожалуйста, введите корректный ID пользователя (число)")


# ------------------- СИСТЕМА БЭКАПОВ -------------------
@admin_router.callback_query(F.data == "admin_backup")
async def admin_backup(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав доступа", show_alert=True)
        return

    text = (
        "💾 <b>Управление бэкапами</b>\n\n"
        "Создание и восстановление резервных копий данных"
    )

    await callback.message.edit_text(
        text,
        reply_markup=admin_backup_keyboard(),
        parse_mode="HTML"
    )


@admin_router.callback_query(F.data == "admin_create_backup")
async def admin_create_backup(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав доступа", show_alert=True)
        return

    try:
        # Создаем бэкап данных
        backup_data = {
            "timestamp": datetime.datetime.now().isoformat(),
            "questions": QUESTIONS,
            "users": await db.get_all_users(),
            "total_users": await db.get_total_users_count(),
            "admin_ids": ADMIN_IDS
        }

        filename = f"backup_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        # Сохраняем во временный файл
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(backup_data, f, ensure_ascii=False, indent=2)

        # Отправляем файл
        with open(filename, 'rb') as f:
            await callback.message.answer_document(
                types.BufferedInputFile(f.read(), filename=filename),
                caption=f"💾 Бэкап создан\nПользователей: {backup_data['total_users']}\nВопросов: {len(QUESTIONS)}"
            )

        # Удаляем временный файл
        Path(filename).unlink()

        await callback.answer("✅ Бэкап успешно создан")

    except Exception as e:
        logger.error(f"Backup error: {e}")
        await callback.answer("❌ Ошибка создания бэкапа", show_alert=True)


# ------------------- СИСТЕМА ЛОГОВ -------------------
@admin_router.callback_query(F.data == "admin_logs")
async def admin_logs(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав доступа", show_alert=True)
        return

    text = (
        "📋 <b>Просмотр логов</b>\n\n"
        "Выберите период для просмотра логов:"
    )

    await callback.message.edit_text(
        text,
        reply_markup=admin_logs_keyboard(),
        parse_mode="HTML"
    )


@admin_router.callback_query(F.data == "admin_logs_today")
async def admin_logs_today(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав доступа", show_alert=True)
        return

    # В реальном приложении здесь бы читались логи из файла
    text = (
        "📅 <b>Логи за сегодня</b>\n\n"
        "🕒 10:15:23 - Пользователь 123456 начал викторину\n"
        "🕒 10:16:45 - Пользователь 789012 ответил правильно\n"
        "🕒 11:23:12 - Ошибка базы данных: timeout\n"
        "🕒 12:45:67 - Новый пользователь 345678\n"
        "🕒 14:32:11 - Админ 812857335 вошел в панель\n\n"
        "📊 <b>Статистика за сегодня:</b>\n"
        "• Новых пользователей: 15\n"
        "• Всего игр: 234\n"
        "• Ошибок: 3\n"
        "• Успешных операций: 98%"
    )

    keyboard = InlineKeyboardBuilder()
    keyboard.row(InlineKeyboardButton(text="📥 Скачать логи", callback_data="admin_download_logs"))
    keyboard.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_logs"))

    await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")


# ------------------- МАССОВЫЕ ОПЕРАЦИИ -------------------
@admin_router.callback_query(F.data == "admin_bulk_operations")
async def admin_bulk_operations(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав доступа", show_alert=True)
        return

    text = (
        "⚡ <b>Массовые операции</b>\n\n"
        "Массовые действия с пользователями"
    )

    await callback.message.edit_text(
        text,
        reply_markup=admin_bulk_operations_keyboard(),
        parse_mode="HTML"
    )


@admin_router.callback_query(F.data == "admin_bulk_xp")
async def admin_bulk_xp_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав доступа", show_alert=True)
        return

    await state.set_state(AdminStates.bulk_xp)

    text = (
        "🎯 <b>Массовое начисление XP</b>\n\n"
        "Введите количество XP для начисления всем пользователям:"
    )

    keyboard = InlineKeyboardBuilder()
    keyboard.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_bulk_operations"))

    await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")


@admin_router.message(AdminStates.bulk_xp)
async def admin_bulk_xp_process(message: types.Message, state: FSMContext):
    try:
        xp_amount = int(message.text.strip())

        if xp_amount <= 0:
            await message.answer("❌ Количество XP должно быть положительным")
            return

        # Получаем всех пользователей
        all_users = await db.get_all_users()
        updated_count = 0
        failed_count = 0

        for user in all_users:
            try:
                current_xp = user.get('xp', 0)
                success = await db.update_user_xp(user['user_id'], current_xp + xp_amount)
                if success:
                    updated_count += 1
                else:
                    failed_count += 1
                    logger.warning(f"Failed to update XP for user {user['user_id']}")
            except (ValueError, TypeError, KeyError) as e:
                # Ошибки данных пользователя
                failed_count += 1
                logger.debug(f"Data error updating XP for user {user.get('user_id', 'unknown')}: {e}")
            except Exception as e:
                # Другие ошибки базы данных
                failed_count += 1
                logger.error(f"Database error updating XP for user {user.get('user_id', 'unknown')}: {e}")

        response_text = f"✅ Начислено {xp_amount} XP для {updated_count} пользователей"
        if failed_count > 0:
            response_text += f"\n❌ Не удалось обновить: {failed_count} пользователей"

        await message.answer(response_text, parse_mode="HTML")
        await state.clear()

    except ValueError:
        await message.answer("❌ Пожалуйста, введите число")


# ------------------- МОНИТОРИНГ СИСТЕМЫ -------------------
def get_system_info():
    """Получает информацию о системе с безопасной проверкой psutil"""
    try:
        import psutil
        import os

        process = psutil.Process(os.getpid())
        memory_usage = process.memory_info().rss / 1024 / 1024  # MB

        return {
            "memory_usage": memory_usage,
            "has_psutil": True
        }
    except ImportError:
        return {
            "has_psutil": False
        }
    except Exception as e:
        logger.error(f"Error getting system info: {e}")
        return {
            "has_psutil": False,
            "error": str(e)
        }


@admin_router.callback_query(F.data == "admin_monitoring")
async def admin_monitoring(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав доступа", show_alert=True)
        return

    # Получаем системную информацию
    try:
        system_info = get_system_info()

        if system_info["has_psutil"]:
            text = (
                "📊 <b>Мониторинг системы</b>\n\n"
                f"💾 Память: {system_info['memory_usage']:.1f} MB\n"
                f"👥 Пользователей: {await db.get_total_users_count()}\n"
                f"📝 Вопросов: {len(QUESTIONS)}\n"
                f"🔄 Активных сессий: в разработке\n"
                f"⏰ Аптайм: в разработке\n\n"
                "⚙️ <b>Статус сервисов:</b>\n"
                "• База данных: ✅\n"
                "• Бот: ✅\n"
                "• Логи: ✅"
            )
        else:
            text = (
                "📊 <b>Мониторинг системы</b>\n\n"
                f"👥 Пользователей: {await db.get_total_users_count()}\n"
                f"📝 Вопросов: {len(QUESTIONS)}\n\n"
                "⚙️ <b>Статус сервисов:</b>\n"
                "• База данных: ✅\n"
                "• Бот: ✅\n"
                "• Логи: ✅\n\n"
                "<i>Расширенный мониторинг недоступен (установите psutil)</i>"
            )

    except Exception as e:
        logger.error(f"Monitoring error: {e}")
        text = (
            "📊 <b>Мониторинг системы</b>\n\n"
            f"👥 Пользователей: {await db.get_total_users_count()}\n"
            f"📝 Вопросов: {len(QUESTIONS)}\n\n"
            "⚙️ <b>Статус сервисов:</b>\n"
            "• База данных: ✅\n"
            "• Бот: ✅\n"
            "• Логи: ✅\n\n"
            "<i>Ошибка получения расширенной информации</i>"
        )

    await callback.message.edit_text(
        text,
        reply_markup=admin_monitoring_keyboard(),
        parse_mode="HTML"
    )

# ------------------- АНАЛИТИКА -------------------
@admin_router.callback_query(F.data == "admin_analytics")
async def admin_analytics(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав доступа", show_alert=True)
        return

    # Получаем аналитику
    try:
        # Безопасный вызов методов, которые могут не существовать
        try:
            user_growth = await db.get_user_growth(30)  # За 30 дней
        except (AttributeError, TypeError):
            user_growth = {'today': 0, 'week': 0, 'month': 0}

        try:
            activity_stats = await db.get_activity_stats()
        except (AttributeError, TypeError):
            activity_stats = {'avg_session': 'N/A', 'messages_per_day': 'N/A', 'conversion': 'N/A'}

        text = (
            "📈 <b>Аналитика бота</b>\n\n"
            "📊 <b>Рост пользователей:</b>\n"
            f"• Новых за сегодня: {user_growth.get('today', 0)}\n"
            f"• Новых за неделю: {user_growth.get('week', 0)}\n"
            f"• Новых за месяц: {user_growth.get('month', 0)}\n\n"

            "📈 <b>Активность:</b>\n"
            f"• Среднее время сессии: {activity_stats.get('avg_session', 'N/A')}\n"
            f"• Сообщений в день: {activity_stats.get('messages_per_day', 'N/A')}\n"
            f"• Конверсия: {activity_stats.get('conversion', 'N/A')}%\n\n"

            "🎯 <b>Эффективность вопросов:</b>\n"
            "• Самый сложный вопрос: в разработке\n"
            "• Самый легкий вопрос: в разработке\n"
            "• Средняя точность: в разработке"
        )
    except Exception as e:
        logger.error(f"Analytics error: {e}")
        text = (
            "📈 <b>Аналитика бота</b>\n\n"
            "📊 <b>Рост пользователей:</b>\n"
            "• Новых за сегодня: в разработке\n"
            "• Новых за неделю: в разработке\n"
            "• Новых за месяц: в разработке\n\n"

            "📈 <b>Активность:</b>\n"
            "• Среднее время сессии: в разработке\n"
            "• Сообщений в день: в разработке\n"
            "• Конверсия: в разработке\n\n"

            "🎯 <b>Эффективность вопросов:</b>\n"
            "• Самый сложный вопрос: в разработке\n"
            "• Самый легкий вопрос: в разработке\n"
            "• Средняя точность: в разработке"
        )

    await callback.message.edit_text(
        text,
        reply_markup=admin_analytics_keyboard(),
        parse_mode="HTML"
    )


# ------------------- НАСТРОЙКИ -------------------
@admin_router.callback_query(F.data == "admin_settings")
async def admin_settings(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав доступа", show_alert=True)
        return

    text = (
        "⚙️ <b>Настройки бота</b>\n\n"
        "Настройка параметров работы бота"
    )

    await callback.message.edit_text(
        text,
        reply_markup=admin_settings_keyboard(),
        parse_mode="HTML"
    )


# ------------------- ТЕСТИРОВАНИЕ -------------------
@admin_router.callback_query(F.data == "admin_testing")
async def admin_testing(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав доступа", show_alert=True)
        return

    text = (
        "🧪 <b>Тестирование функций</b>\n\n"
        "Проверка работоспособности функций бота"
    )

    await callback.message.edit_text(
        text,
        reply_markup=admin_testing_keyboard(),
        parse_mode="HTML"
    )


@admin_router.callback_query(F.data == "admin_test_db")
async def admin_test_db(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав доступа", show_alert=True)
        return

    try:
        # Тестируем подключение к базе данных
        total_users = await db.get_total_users_count()
        await callback.answer(f"✅ База данных работает. Пользователей: {total_users}", show_alert=True)
    except Exception as e:
        await callback.answer(f"❌ Ошибка базы данных: {str(e)}", show_alert=True)


# ------------------- Детальная статистика -------------------
@admin_router.callback_query(F.data == "admin_detailed_stats")
async def admin_detailed_stats(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав доступа", show_alert=True)
        return

    # Получаем расширенную статистику
    total_users = await db.get_total_users_count()
    active_today = await db.get_active_users_count(1)
    active_week = await db.get_active_users_count(7)
    total_questions = len(QUESTIONS)

    text = (
        f"📈 <b>Детальная статистика</b>\n\n"
        f"👥 <b>Пользователи:</b>\n"
        f"• Всего: {total_users}\n"
        f"• Активных за сегодня: {active_today}\n"
        f"• Активных за неделю: {active_week}\n\n"
        f"📝 <b>Вопросы:</b> {total_questions}\n\n"
        f"⚙️ <b>Система:</b>\n"
        f"• Версия бота: 1.0\n"
        f"• Админов: {len(ADMIN_IDS)}\n"
    )

    await callback.message.edit_text(
        text,
        reply_markup=admin_stats_keyboard(),
        parse_mode="HTML"
    )


# ------------------- Статистика рассылок -------------------
@admin_router.callback_query(F.data == "admin_broadcast_stats")
async def admin_broadcast_stats(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав доступа", show_alert=True)
        return

    text = (
        "📊 <b>Статистика рассылок</b>\n\n"
        "📈 В разработке...\n\n"
        "Здесь будет отображаться статистика по всем рассылкам:\n"
        "• Количество отправленных сообщений\n"
        "• Процент доставки\n"
        "• Активность пользователей"
    )

    await callback.message.edit_text(
        text,
        reply_markup=admin_broadcast_keyboard(),
        parse_mode="HTML"
    )


# ------------------- Активные пользователи -------------------
@admin_router.callback_query(F.data == "admin_active_users")
async def admin_active_users(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав доступа", show_alert=True)
        return

    text = (
        "⚡ <b>Активные пользователи</b>\n\n"
        "📊 В разработке...\n\n"
        "Здесь будет отображаться список самых активных пользователей\n"
        "за различные периоды времени."
    )

    await callback.message.edit_text(
        text,
        reply_markup=admin_users_keyboard(),
        parse_mode="HTML"
    )


# ------------------- Статистика пользователей -------------------
@admin_router.callback_query(F.data == "admin_users_stats")
async def admin_users_stats(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав доступа", show_alert=True)
        return

    total_users = await db.get_total_users_count()
    active_today = await db.get_active_users_count(1)
    active_week = await db.get_active_users_count(7)

    text = (
        f"📊 <b>Статистика пользователей</b>\n\n"
        f"👥 <b>Общая статистика:</b>\n"
        f"• Всего пользователей: {total_users}\n"
        f"• Активных за сегодня: {active_today}\n"
        f"• Активных за неделю: {active_week}\n\n"
        f"📈 <b>Активность:</b>\n"
        f"• Онлайн сейчас: в разработке\n"
        f"• Новых сегодня: в разработке"
    )

    await callback.message.edit_text(
        text,
        reply_markup=admin_users_keyboard(),
        parse_mode="HTML"
    )


# ------------------- СИСТЕМНЫЕ ОПЕРАЦИИ -------------------
@admin_router.callback_query(F.data == "admin_system")
async def admin_system_operations(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав доступа", show_alert=True)
        return

    text = (
        "🔄 <b>Системные операции</b>\n\n"
        "Управление системой и массовые операции:"
    )

    await callback.message.edit_text(
        text,
        reply_markup=admin_system_operations_keyboard(),
        parse_mode="HTML"
    )


@admin_router.callback_query(F.data == "admin_full_reset")
async def admin_full_reset(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав доступа", show_alert=True)
        return

    # Получаем текущую статистику для информации
    total_users = await db.get_total_users_count()

    text = (
        "🔄 <b>Полный сброс системы</b>\n\n"
        f"📊 <b>Текущая статистика:</b>\n"
        f"• Пользователей в системе: {total_users}\n"
        f"• Вопросов в базе: {len(QUESTIONS)}\n\n"
        "⚠️ <b>ВНИМАНИЕ!</b> Это действие:\n"
        "• Обнулит ВСЕХ пользователей\n"
        "• Сбросит весь прогресс (уровни, XP)\n"
        "• Очистит всю статистику ответов\n"
        "• Удалит историю дуэлей\n"
        "• Сбросит ежедневные награды\n\n"
        "❓ <b>Что сохранится:</b>\n"
        "• Все вопросы останутся\n"
        "• Настройки админов\n"
        "• Структура базы данных\n\n"
        "Вы уверены, что хотите продолжить?"
    )

    keyboard = InlineKeyboardBuilder()
    keyboard.row(
        InlineKeyboardButton(
            text="✅ Да, сбросить всё",
            callback_data="admin_full_reset_confirm"
        )
    )
    keyboard.row(
        InlineKeyboardButton(
            text="❌ Отмена",
            callback_data="admin_system"
        )
    )

    await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")


@admin_router.callback_query(F.data == "admin_full_reset_confirm")
async def admin_full_reset_confirm(callback: types.CallbackQuery):
    try:
        # Показываем уведомление о начале процесса
        await callback.message.edit_text("⏳ <b>Выполняется сброс системы...</b>", parse_mode="HTML")

        # Выполняем сброс
        reset_count = await db.reset_all_users()

        text = (
            f"✅ <b>Система полностью сброшена!</b>\n\n"
            f"📊 <b>Результаты:</b>\n"
            f"• 🔄 Сброшено пользователей: {reset_count}\n"
            f"• 📝 Вопросы сохранены: {len(QUESTIONS)}\n"
            f"• 👑 Админы сохранены: {len(ADMIN_IDS)}\n"
            f"• ⚔️ Дуэли очищены\n\n"
            f"🎯 <b>Все пользователи теперь начинают с:</b>\n"
            f"• Уровень 1\n"
            f"• 0 XP\n"
            f"• Чистая статистика\n"
            f"• Доступны ежедневные награды\n\n"
            f"<i>Система готова к новому старту!</i>"
        )

        keyboard = InlineKeyboardBuilder()
        keyboard.row(
            InlineKeyboardButton(
                text="🔄 В системные операции",
                callback_data="admin_system"
            )
        )
        keyboard.row(
            InlineKeyboardButton(
                text="⬅️ В главное меню",
                callback_data="admin_main"
            )
        )

        await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")

    except Exception as e:
        logger.error(f"Full reset error: {e}")

        error_text = (
            f"❌ <b>Ошибка при сбросе системы</b>\n\n"
            f"<code>{str(e)}</code>\n\n"
            f"Проверьте логи для подробной информации."
        )

        keyboard = InlineKeyboardBuilder()
        keyboard.row(
            InlineKeyboardButton(
                text="🔄 Попробовать снова",
                callback_data="admin_full_reset"
            )
        )
        keyboard.row(
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data="admin_system"
            )
        )

        await callback.message.edit_text(error_text, reply_markup=keyboard.as_markup(), parse_mode="HTML")