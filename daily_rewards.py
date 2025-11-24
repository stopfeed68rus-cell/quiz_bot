from datetime import datetime, timedelta
from typing import Dict, Any
from db import db


class DailyRewardSystem:
    def __init__(self):
        self.base_reward = 50  # Базовая награда

    @staticmethod
    async def can_claim_reward(user_id: int) -> Dict[str, Any]:
        """Проверяет, может ли пользователь получить награду."""
        reward_info = await db.get_daily_reward_info(user_id)
        today = datetime.now().date()

        if reward_info["last_reward_date"] == str(today):
            # Вычисляем время до следующей награды
            next_reward = datetime.now() + timedelta(days=1)
            next_reward = next_reward.replace(hour=0, minute=0, second=0, microsecond=0)
            time_until = next_reward - datetime.now()

            hours_until = time_until.seconds // 3600
            minutes_until = (time_until.seconds % 3600) // 60

            return {
                "can_claim": False,
                "hours_until": hours_until,
                "minutes_until": minutes_until,
                "streak": reward_info["streak_count"]
            }

        return {
            "can_claim": True,
            "streak": reward_info["streak_count"]
        }

    async def get_reward_info(self, user_id: int) -> Dict[str, Any]:
        """Возвращает полную информацию о наградах."""
        reward_info = await db.get_daily_reward_info(user_id)
        claim_status = await self.can_claim_reward(user_id)

        # Вычисляем следующую награду
        next_base_reward = self.base_reward
        if claim_status["can_claim"]:
            next_streak = reward_info["streak_count"] + 1
            streak_bonus = min(next_streak * 5, 50)  # Максимум 50% бонус
            next_base_reward += (next_base_reward * streak_bonus // 100)

        return {
            **reward_info,
            **claim_status,
            "base_reward": self.base_reward,
            "next_reward": next_base_reward,
            "max_streak_bonus": 50
        }

    async def claim_reward(self, user_id: int) -> Dict[str, Any]:
        """Выдает ежедневную награду."""
        return await db.claim_daily_reward(user_id, self.base_reward)


# Глобальный экземпляр
daily_rewards = DailyRewardSystem()

# Расписание наград на неделю
WEEKLY_REWARDS = {
    0: {"xp": 50, "name": "Понедельник", "emoji": "🌙"},
    1: {"xp": 60, "name": "Вторник", "emoji": "🔥"},
    2: {"xp": 70, "name": "Среда", "emoji": "💧"},
    3: {"xp": 80, "name": "Четверг", "emoji": "🌿"},
    4: {"xp": 90, "name": "Пятница", "emoji": "⭐"},
    5: {"xp": 100, "name": "Суббота", "emoji": "🎯"},
    6: {"xp": 150, "name": "Воскресенье", "emoji": "🎁"}
}