import asyncio
from datetime import datetime, time
from typing import Dict, Any, List
from db import db
from achievements import ACHIEVEMENTS, AchievementType


class AchievementChecker:
    def __init__(self):
        self.user_sessions: Dict[int, Dict] = {}
        self._achievement_cache: Dict[int, List[str]] = {}  # Кэш достижений пользователя

    async def check_achievements(self, user_id: int, event_type: str, **kwargs) -> List[str]:
        """Основной метод проверки достижений"""
        unlocked = []

        # Инициализируем сессию пользователя
        session = await self._get_user_session(user_id)
        session['last_activity'] = datetime.now()

        # Проверяем достижения по типу события
        if event_type == "answer":
            unlocked = await self._check_answer_achievements(user_id, session, **kwargs)
        elif event_type == "login":
            unlocked = await self._check_login_achievements()
        elif event_type == "level_up":
            unlocked = await self._check_level_achievements(user_id, **kwargs)

        return unlocked

    async def _get_user_session(self, user_id: int) -> Dict[str, Any]:
        """Получает или создает сессию пользователя"""
        if user_id not in self.user_sessions:
            self.user_sessions[user_id] = {
                'session_start': datetime.now(),
                'answers_count': 0,
                'correct_answers': 0,
                'last_activity': datetime.now(),
                'achievements_checked': set()
            }
        return self.user_sessions[user_id]

    async def _check_answer_achievements(self, user_id: int, session: Dict, **kwargs) -> List[str]:
        """Проверяет достижения, связанные с ответами на вопросы"""
        unlocked = []
        is_correct = kwargs.get('is_correct', False)
        current_combo = kwargs.get('current_combo', 0)
        user_xp = kwargs.get('user_xp', 0)
        total_answers = kwargs.get('total_answers', 0)

        # Обновляем статистику сессии
        session['answers_count'] += 1
        if is_correct:
            session['correct_answers'] += 1

        # 🎯 Первые шаги
        if is_correct and total_answers == 1:
            if await self._try_unlock_achievement(user_id, AchievementType.FIRST_STEPS.value):
                unlocked.append(AchievementType.FIRST_STEPS.value)

        # 🔥 Мастер комбо
        if current_combo >= 10:
            if await self._try_unlock_achievement(user_id, AchievementType.COMBO_MASTER.value):
                unlocked.append(AchievementType.COMBO_MASTER.value)

        # 💎 Перфекционист
        if current_combo >= 20:
            if await self._try_unlock_achievement(user_id, AchievementType.PERFECTIONIST.value):
                unlocked.append(AchievementType.PERFECTIONIST.value)

        # 🏃 Марафонец
        if total_answers >= 100:
            if await self._try_unlock_achievement(user_id, AchievementType.QUIZ_MARATHON.value):
                unlocked.append(AchievementType.QUIZ_MARATHON.value)

        # 📚 Искатель знаний
        if user_xp >= 1000:
            if await self._try_unlock_achievement(user_id, AchievementType.KNOWLEDGE_SEEKER.value):
                unlocked.append(AchievementType.KNOWLEDGE_SEEKER.value)

        # ⚡ Скорострел
        session_time = (datetime.now() - session['session_start']).total_seconds()
        if session['answers_count'] >= 10 and session_time <= 120:
            if await self._try_unlock_achievement(user_id, AchievementType.SPEED_DEMON.value):
                unlocked.append(AchievementType.SPEED_DEMON.value)

        # 🌅 Ранняя пташка и 🌙 Ночная сова
        current_time = datetime.now().time()
        if time(6, 0) <= current_time <= time(9, 0):
            if await self._try_unlock_achievement(user_id, AchievementType.EARLY_BIRD.value):
                unlocked.append(AchievementType.EARLY_BIRD.value)
        elif time(23, 0) <= current_time or current_time <= time(4, 0):
            if await self._try_unlock_achievement(user_id, AchievementType.NIGHT_OWL.value):
                unlocked.append(AchievementType.NIGHT_OWL.value)

        return unlocked

    @staticmethod
    async def _check_login_achievements() -> List[str]:
        """Проверяет достижения, связанные с входом в систему"""
        unlocked = []
        # Здесь можно добавить логику для ежедневных достижений
        return unlocked

    async def _check_level_achievements(self, user_id: int, **kwargs) -> List[str]:
        """Проверяет достижения, связанные с уровнями"""
        unlocked = []
        level = kwargs.get('level', 1)

        # 🎖️ Ветеран
        if level >= 10:
            if await self._try_unlock_achievement(user_id, AchievementType.VETERAN.value):
                unlocked.append(AchievementType.VETERAN.value)

        return unlocked

    async def _try_unlock_achievement(self, user_id: int, achievement_id: str) -> bool:
        """Пытается разблокировать достижение и возвращает успешность"""
        # Проверяем кэш, чтобы избежать лишних запросов к БД
        if user_id not in self._achievement_cache:
            user_achievements = await db.get_user_achievements(user_id)
            self._achievement_cache[user_id] = [ach['achievement_id'] for ach in user_achievements]

        # Если достижение уже есть в кэше, не разблокируем снова
        if achievement_id in self._achievement_cache[user_id]:
            return False

        # Пытаемся добавить достижение
        success = await db.add_achievement(user_id, achievement_id)
        if success:
            # Обновляем кэш
            self._achievement_cache[user_id].append(achievement_id)
            return True

        return False

    async def clear_user_cache(self, user_id: int):
        """Очищает кэш пользователя (например, при сбросе прогресса)"""
        if user_id in self._achievement_cache:
            del self._achievement_cache[user_id]
        if user_id in self.user_sessions:
            del self.user_sessions[user_id]

    @staticmethod
    async def get_user_progress(user_id: int) -> Dict[str, Any]:
        """Возвращает прогресс пользователя по достижениям"""
        user_achievements = await db.get_user_achievements(user_id)
        unlocked_ids = {ach['achievement_id'] for ach in user_achievements}

        progress = {}
        for achievement_id, achievement_data in ACHIEVEMENTS.items():
            progress[achievement_id] = {
                'unlocked': achievement_id in unlocked_ids,
                'name': achievement_data['name'],
                'description': achievement_data['description'],
                'icon': achievement_data['icon'],
                'rarity': achievement_data['rarity'],
                'xp_reward': achievement_data['xp_reward']
            }

        return progress

    async def cleanup_old_sessions(self, hours_old: int = 24):
        """Очищает старые сессии для экономии памяти"""
        now = datetime.now()
        users_to_remove = []

        for user_id, session in self.user_sessions.items():
            session_age = (now - session['last_activity']).total_seconds() / 3600
            if session_age > hours_old:
                users_to_remove.append(user_id)

        for user_id in users_to_remove:
            del self.user_sessions[user_id]


# Глобальный экземпляр проверщика
achievement_checker = AchievementChecker()


# Функция для периодической очистки старых сессий
async def start_session_cleanup_task():
    """Запускает фоновую задачу для очистки старых сессий"""
    while True:
        await asyncio.sleep(3600)  # Проверяем каждый час
        await achievement_checker.cleanup_old_sessions()