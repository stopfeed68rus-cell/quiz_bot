from typing import Dict, Any
from enum import Enum

class AchievementType(Enum):
    FIRST_STEPS = "first_steps"
    COMBO_MASTER = "combo_master"
    PERFECTIONIST = "perfectionist"
    QUIZ_MARATHON = "quiz_marathon"
    KNOWLEDGE_SEEKER = "knowledge_seeker"
    SPEED_DEMON = "speed_demon"
    CONSISTENCY_KING = "consistency_king"
    EARLY_BIRD = "early_bird"
    NIGHT_OWL = "night_owl"
    VETERAN = "veteran"
    DAILY_LEARNER = "daily_learner"
    STREAK_MASTER = "streak_master"
    REWARD_COLLECTOR = "reward_collector"

ACHIEVEMENTS: Dict[str, Dict[str, Any]] = {
    AchievementType.FIRST_STEPS.value: {
        "name": "🎯 Первые шаги",
        "description": "Правильно ответить на первый вопрос",
        "icon": "🎯",
        "rarity": "common",
        "xp_reward": 50
    },
    AchievementType.COMBO_MASTER.value: {
        "name": "🔥 Мастер комбо",
        "description": "Достичь комбо из 10 правильных ответов подряд",
        "icon": "🔥",
        "rarity": "rare",
        "xp_reward": 100
    },
    AchievementType.PERFECTIONIST.value: {
        "name": "💎 Перфекционист",
        "description": "Ответить правильно на 20 вопросов подряд",
        "icon": "💎",
        "rarity": "epic",
        "xp_reward": 200
    },
    AchievementType.QUIZ_MARATHON.value: {
        "name": "🏃 Марафонец",
        "description": "Ответить на 100 вопросов в общей сложности",
        "icon": "🏃",
        "rarity": "rare",
        "xp_reward": 150
    },
    AchievementType.KNOWLEDGE_SEEKER.value: {
        "name": "📚 Искатель знаний",
        "description": "Заработать 1000 XP",
        "icon": "📚",
        "rarity": "common",
        "xp_reward": 100
    },
    AchievementType.SPEED_DEMON.value: {
        "name": "⚡ Скорострел",
        "description": "Ответить на 10 вопросов за 2 минуты",
        "icon": "⚡",
        "rarity": "epic",
        "xp_reward": 250
    },
    AchievementType.CONSISTENCY_KING.value: {
        "name": "👑 Король последовательности",
        "description": "Играть 7 дней подряд",
        "icon": "👑",
        "rarity": "rare",
        "xp_reward": 150
    },
    AchievementType.EARLY_BIRD.value: {
        "name": "🌅 Ранняя пташка",
        "description": "Сыграть в викторину между 6:00 и 9:00 утра",
        "icon": "🌅",
        "rarity": "uncommon",
        "xp_reward": 75
    },
    AchievementType.NIGHT_OWL.value: {
        "name": "🌙 Ночная сова",
        "description": "Сыграть в викторину между 23:00 и 4:00",
        "icon": "🌙",
        "rarity": "uncommon",
        "xp_reward": 75
    },
    AchievementType.VETERAN.value: {
        "name": "🎖️ Ветеран",
        "description": "Достичь 10 уровня",
        "icon": "🎖️",
        "rarity": "legendary",
        "xp_reward": 500
    },
    # Новые достижения для ежедневных наград
    AchievementType.DAILY_LEARNER.value: {
        "name": "📅 Ежедневный ученик",
        "description": "Получить ежедневную награду 7 дней подряд",
        "icon": "📅",
        "rarity": "rare",
        "xp_reward": 100
    },
    AchievementType.STREAK_MASTER.value: {
        "name": "🔥 Мастер стриков",
        "description": "Достичь стрика из 30 дней",
        "icon": "🔥",
        "rarity": "epic",
        "xp_reward": 300
    },
    AchievementType.REWARD_COLLECTOR.value: {
        "name": "🎁 Коллекционер наград",
        "description": "Получить 100 ежедневных наград",
        "icon": "🎁",
        "rarity": "legendary",
        "xp_reward": 500
    }
}

def get_achievement_display(achievement_id: str) -> str:
    achievement = ACHIEVEMENTS.get(achievement_id, {})
    return f"{achievement.get('icon', '🏆')} {achievement.get('name', 'Неизвестно')}"

def get_achievement_full_info(achievement_id: str) -> str:
    achievement = ACHIEVEMENTS.get(achievement_id, {})
    return (
        f"{achievement.get('icon', '🏆')} *{achievement.get('name', 'Неизвестно')}*\n"
        f"📝 {achievement.get('description', '')}\n"
        f"🎯 Редкость: {achievement.get('rarity', 'common').title()}\n"
        f"✨ Награда: +{achievement.get('xp_reward', 0)} XP"
    )