import aiosqlite
import json
import os
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

# КРИТИЧЕСКИ ВАЖНО ДЛЯ RENDER!
if os.getenv("RENDER"):
    DB_PATH = ":memory:"
else:
    DB_PATH = "quiz.db"

print(f"📁 Используется база данных: {DB_PATH}")
print(f"🌐 Render окружение: {os.getenv('RENDER', 'Нет')}")
print(f"🤖 Токен бота: {'Установлен' if os.getenv('BOT_TOKEN') else 'НЕ УСТАНОВЛЕН!'}")


class Database:  # ← ТОЛЬКО ОДИН РАЗ!
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.conn: Optional[aiosqlite.Connection] = None
        print(f"🔄 Инициализация Database с путем: {db_path}")

    # ДАЛЕЕ ВЕСЬ ОСТАЛЬНОЙ КОД КЛАССА...
    # ---------------- Подключение и инициализация ----------------
    async def connect(self):
        """Устанавливает соединение с БД и инициализирует таблицы."""
        if not self.conn:
            self.conn = await aiosqlite.connect(self.db_path)
            await self.conn.execute("PRAGMA foreign_keys = ON;")
            await self.init_db()

    # ... и весь остальной код без изменений

    async def close(self):
        """Закрывает соединение с БД."""
        if self.conn:
            await self.conn.close()
            self.conn = None

    async def _ensure_connected(self):
        """Гарантирует, что соединение установлено."""
        if not self.conn:
            await self.connect()

    async def _migrate_database(self):
        """Миграция базы данных - добавляет отсутствующие колонки"""
        try:
            migrations = [
                ('users', 'created_at', 'DATETIME DEFAULT CURRENT_TIMESTAMP'),
                ('users', 'last_active', 'DATETIME DEFAULT CURRENT_TIMESTAMP'),
                ('duel_stats', 'average_score', 'REAL DEFAULT 0'),
            ]

            for table, column, definition in migrations:
                async with self.conn.execute(f"PRAGMA table_info({table})") as cursor:
                    columns = [row[1] for row in await cursor.fetchall()]

                if column not in columns:
                    await self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
                    logger.info(f"✅ Добавлена колонка {column} в таблицу {table}")

            await self.conn.commit()

        except Exception as e:
            logger.error("❌ Ошибка миграции базы данных: %s", e)
            # Не прерываем выполнение при ошибке миграции

    async def init_db(self):
        """Создаёт таблицы, если их нет."""
        assert self.conn, "Database connection is not established"

        # Таблица пользователей
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                level INTEGER DEFAULT 1,
                xp INTEGER DEFAULT 0,
                max_combo INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_active DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Таблица достижений
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS achievements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                achievement_id TEXT,
                unlocked_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id),
                UNIQUE(user_id, achievement_id)
            )
        """)

        # Таблица статистики пользователей
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS user_stats (
                user_id INTEGER PRIMARY KEY,
                total_answers INTEGER DEFAULT 0,
                correct_answers INTEGER DEFAULT 0,
                total_combo INTEGER DEFAULT 0,
                perfect_quizzes INTEGER DEFAULT 0,
                categories_completed INTEGER DEFAULT 0,
                last_activity DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        """)

        # Новая таблица для ежедневных наград
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_rewards (
                user_id INTEGER PRIMARY KEY,
                last_reward_date DATE,
                streak_count INTEGER DEFAULT 0,
                total_rewards INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        """)

        # Таблица статистики по категориям
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS category_stats (
                user_id INTEGER,
                category TEXT,
                total_answers INTEGER DEFAULT 0,
                correct_answers INTEGER DEFAULT 0,
                last_played DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, category),
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        """)

        # Таблицы для дуэлей
        await self.create_duels_table()

        # Выполняем миграцию
        await self._migrate_database()

        # Создаем индексы
        await self.conn.execute("CREATE INDEX IF NOT EXISTS idx_users_xp ON users (xp DESC)")
        await self.conn.execute("CREATE INDEX IF NOT EXISTS idx_achievements_user ON achievements (user_id)")
        await self.conn.execute("CREATE INDEX IF NOT EXISTS idx_daily_rewards_date ON daily_rewards (last_reward_date)")
        await self.conn.execute("CREATE INDEX IF NOT EXISTS idx_category_stats_user ON category_stats (user_id)")
        await self.conn.execute("CREATE INDEX IF NOT EXISTS idx_duels_created ON duels (created_at DESC)")
        await self.conn.commit()

    # ---------------- Пользователь ----------------
    async def get_user(self, user_id: int, username: str = "") -> Dict[str, Any]:
        """Возвращает пользователя или создаёт нового, если его нет."""
        await self._ensure_connected()

        async with self.conn.execute(
                "SELECT user_id, username, level, xp, max_combo FROM users WHERE user_id = ?",
                (user_id,)
        ) as cursor:
            row = await cursor.fetchone()

        if row:
            if username and username != row[1]:
                await self.conn.execute(
                    "UPDATE users SET username = ? WHERE user_id = ?",
                    (username, user_id)
                )
                await self.conn.commit()

            # Гарантируем, что статистика существует
            await self.get_user_stats(user_id)

            return {
                "user_id": row[0],
                "username": row[1],
                "level": row[2],
                "xp": row[3],
                "max_combo": row[4],
            }

        # Создаем нового пользователя
        await self.conn.execute(
            "INSERT INTO users (user_id, username, level, xp, max_combo) VALUES (?, ?, ?, ?, ?)",
            (user_id, username, 1, 0, 0)
        )

        # Создаем запись статистики
        await self.conn.execute(
            "INSERT INTO user_stats (user_id) VALUES (?)",
            (user_id,)
        )

        await self.conn.commit()

        return {"user_id": user_id, "username": username, "level": 1, "xp": 0, "max_combo": 0}

    # ---------------- Обновление имени пользователя ----------------
    async def update_username(self, user_id: int, username: str) -> None:
        """Обновляет имя пользователя в базе данных."""
        await self._ensure_connected()

        await self.conn.execute(
            "UPDATE users SET username = ? WHERE user_id = ?",
            (username, user_id)
        )
        await self.conn.commit()

    # ---------------- Добавление XP ----------------
    async def add_xp(self, user_id: int, xp: int) -> tuple[int, int]:
        """Добавляет XP пользователю и возвращает (новый_xp, новый_уровень)."""
        await self._ensure_connected()

        async with self.conn.execute("SELECT xp FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()

        if row:
            new_xp = row[0] + xp
            new_level = new_xp // 100 + 1
            await self.conn.execute(
                "UPDATE users SET xp = ?, level = ? WHERE user_id = ?",
                (new_xp, new_level, user_id)
            )
            await self.conn.commit()
            return new_xp, new_level

        new_level = xp // 100 + 1
        await self.conn.execute(
            "INSERT INTO users (user_id, username, level, xp, max_combo) VALUES (?, ?, ?, ?, ?)",
            (user_id, "", new_level, xp, 0)
        )
        await self.conn.commit()
        return xp, new_level

    # ---------------- Получение XP пользователя ----------------
    async def get_user_xp(self, user_id: int) -> int:
        """Получает текущий XP пользователя."""
        await self._ensure_connected()

        async with self.conn.execute("SELECT xp FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()

        return row[0] if row else 0

    # ---------------- Обновление max_combo ----------------
    async def update_max_combo(self, user_id: int, combo: int):
        """Обновляет max_combo, если новое значение больше текущего."""
        await self._ensure_connected()

        async with self.conn.execute(
                "SELECT max_combo FROM users WHERE user_id = ?",
                (user_id,)
        ) as cursor:
            row = await cursor.fetchone()

        if row and combo > row[0]:
            await self.conn.execute(
                "UPDATE users SET max_combo = ? WHERE user_id = ?",
                (combo, user_id)
            )
            await self.conn.commit()

    async def update_last_activity(self, user_id: int):
        """Обновляет время последней активности пользователя"""
        await self._ensure_connected()

        try:
            await self.conn.execute(
                "UPDATE user_stats SET last_activity = CURRENT_TIMESTAMP WHERE user_id = ?",
                (user_id,)
            )
            # Убираем обновление last_active, если колонки нет
            # await self.conn.execute(
            #     "UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE user_id = ?",
            #     (user_id,)
            # )
            await self.conn.commit()
        except Exception as e:
            logger.debug(f"Не удалось обновить активность для {user_id}: {e}")

    # ---------------- Топ пользователей ----------------
    async def get_top_users(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Возвращает топ пользователей по XP."""
        await self._ensure_connected()

        async with self.conn.execute(
                "SELECT user_id, username, level, xp, max_combo FROM users ORDER BY xp DESC LIMIT ?",
                (limit,)
        ) as cursor:
            rows = await cursor.fetchall()

        return [
            {"user_id": r[0], "username": r[1] or "Аноним", "level": r[2], "xp": r[3], "max_combo": r[4]}
            for r in rows
        ]

    # ---------------- Сброс прогресса ----------------
    async def reset_progress(self, user_id: int):
        """Сбрасывает прогресс пользователя (XP, уровень, max_combo)."""
        await self._ensure_connected()
        await self.conn.execute(
            "UPDATE users SET xp = 0, level = 1, max_combo = 0 WHERE user_id = ?",
            (user_id,)
        )
        # Также удаляем достижения пользователя
        await self.conn.execute(
            "DELETE FROM achievements WHERE user_id = ?",
            (user_id,)
        )
        # Сбрасываем статистику
        await self.conn.execute(
            "DELETE FROM user_stats WHERE user_id = ?",
            (user_id,)
        )
        # Сбрасываем награды
        await self.conn.execute(
            "DELETE FROM daily_rewards WHERE user_id = ?",
            (user_id,)
        )
        # Сбрасываем статистику по категориям
        await self.conn.execute(
            "DELETE FROM category_stats WHERE user_id = ?",
            (user_id,)
        )
        # Сбрасываем статистику дуэлей
        await self.conn.execute(
            "DELETE FROM duel_stats WHERE user_id = ?",
            (user_id,)
        )
        await self.conn.commit()

    # ---------------- СИСТЕМА ДОСТИЖЕНИЙ ----------------

    async def add_achievement(self, user_id: int, achievement_id: str) -> bool:
        """Добавляет достижение пользователю, если его еще нет."""
        await self._ensure_connected()

        # Проверяем, есть ли уже такое достижение
        async with self.conn.execute(
                "SELECT 1 FROM achievements WHERE user_id = ? AND achievement_id = ?",
                (user_id, achievement_id)
        ) as cursor:
            exists = await cursor.fetchone()

        if not exists:
            await self.conn.execute(
                "INSERT INTO achievements (user_id, achievement_id) VALUES (?, ?)",
                (user_id, achievement_id)
            )
            await self.conn.commit()
            return True
        return False

    async def get_user_achievements(self, user_id: int) -> List[Dict[str, Any]]:
        """Получает все достижения пользователя."""
        await self._ensure_connected()

        async with self.conn.execute('''
            SELECT achievement_id, unlocked_at 
            FROM achievements 
            WHERE user_id = ? 
            ORDER BY unlocked_at DESC
        ''', (user_id,)) as cursor:
            rows = await cursor.fetchall()

        achievements = []
        for row in rows:
            achievements.append({
                "achievement_id": row[0],
                "unlocked_at": row[1]
            })
        return achievements

    async def get_achievements_count(self, user_id: int) -> int:
        """Получает количество достижений пользователя."""
        await self._ensure_connected()

        async with self.conn.execute(
                "SELECT COUNT(*) FROM achievements WHERE user_id = ?",
                (user_id,)
        ) as cursor:
            result = await cursor.fetchone()
            return result[0] if result else 0

    # ---------------- СТАТИСТИКА ПО КАТЕГОРИЯМ ----------------

    async def update_user_category_stats(self, user_id: int, category: str, is_correct: bool):
        """Обновляет статистику по категориям"""
        await self._ensure_connected()

        if is_correct:
            await self.conn.execute('''
                INSERT INTO category_stats (user_id, category, total_answers, correct_answers)
                VALUES (?, ?, 1, 1)
                ON CONFLICT(user_id, category) 
                DO UPDATE SET 
                    total_answers = total_answers + 1,
                    correct_answers = correct_answers + 1,
                    last_played = CURRENT_TIMESTAMP
            ''', (user_id, category))
        else:
            await self.conn.execute('''
                INSERT INTO category_stats (user_id, category, total_answers, correct_answers)
                VALUES (?, ?, 1, 0)
                ON CONFLICT(user_id, category) 
                DO UPDATE SET 
                    total_answers = total_answers + 1,
                    last_played = CURRENT_TIMESTAMP
            ''', (user_id, category))

        await self.conn.commit()

    async def get_user_category_stats(self, user_id: int) -> Dict[str, Dict]:
        """Получает статистику пользователя по категориям"""
        await self._ensure_connected()

        async with self.conn.execute('''
            SELECT category, total_answers, correct_answers, last_played
            FROM category_stats 
            WHERE user_id = ?
            ORDER BY total_answers DESC
        ''', (user_id,)) as cursor:
            rows = await cursor.fetchall()

        stats = {}
        for row in rows:
            category, total, correct, last_played = row
            accuracy = round((correct / total * 100), 1) if total > 0 else 0
            stats[category] = {
                "total_answers": total,
                "correct_answers": correct,
                "accuracy": accuracy,
                "last_played": last_played
            }

        return stats

    async def get_user_favorite_category(self, user_id: int) -> str:
        """Возвращает любимую категорию пользователя"""
        stats = await self.get_user_category_stats(user_id)
        if not stats:
            return "не определена"

        favorite = max(stats.items(), key=lambda x: x[1]["total_answers"])
        category_names = {
            "история": "📜 История",
            "наука": "🔬 Наука",
            "искусство": "🎨 Искусство",
            "география": "🌍 География",
            "спорт": "⚽ Спорт"
        }
        return category_names.get(favorite[0], favorite[0])

    # ---------------- СТАТИСТИКА ПОЛЬЗОВАТЕЛЯ ----------------

    async def get_user_stats(self, user_id: int) -> Dict[str, Any]:
        """Получает статистику пользователя."""
        await self._ensure_connected()

        async with self.conn.execute(
                "SELECT * FROM user_stats WHERE user_id = ?",
                (user_id,)
        ) as cursor:
            row = await cursor.fetchone()

        if row:
            return {
                "user_id": row[0],
                "total_answers": row[1],
                "correct_answers": row[2],
                "total_combo": row[3],
                "perfect_quizzes": row[4],
                "categories_completed": row[5],
                "last_activity": row[6]
            }
        else:
            # Создаем запись, если не существует
            await self.conn.execute(
                "INSERT INTO user_stats (user_id) VALUES (?)",
                (user_id,)
            )
            await self.conn.commit()
            return {
                "user_id": user_id,
                "total_answers": 0,
                "correct_answers": 0,
                "total_combo": 0,
                "perfect_quizzes": 0,
                "categories_completed": 0,
                "last_activity": datetime.now().isoformat()
            }

    async def update_user_stats(self, user_id: int, updates: Dict[str, Any]):
        """Обновляет статистику пользователя."""
        await self._ensure_connected()

        # Сначала убедимся, что запись существует
        await self.get_user_stats(user_id)

        set_clause = ', '.join([f"{key} = ?" for key in updates.keys()])
        values = list(updates.values())
        values.append(user_id)

        await self.conn.execute(
            f"UPDATE user_stats SET {set_clause} WHERE user_id = ?",
            values
        )
        await self.conn.commit()

    async def increment_user_stats(self, user_id: int, field: str, value: int = 1):
        """Увеличивает значение поля статистики на указанное число."""
        await self._ensure_connected()

        # Сначала убедимся, что запись существует
        await self.get_user_stats(user_id)

        await self.conn.execute(
            f"UPDATE user_stats SET {field} = {field} + ? WHERE user_id = ?",
            (value, user_id)
        )
        await self.conn.commit()

    # ---------------- ЕЖЕДНЕВНЫЕ НАГРАДЫ ----------------

    async def get_daily_reward_info(self, user_id: int) -> Dict[str, Any]:
        """Получает информацию о ежедневных наградах пользователя."""
        await self._ensure_connected()

        async with self.conn.execute(
                "SELECT last_reward_date, streak_count, total_rewards FROM daily_rewards WHERE user_id = ?",
                (user_id,)
        ) as cursor:
            row = await cursor.fetchone()

        if row:
            return {
                "last_reward_date": row[0],
                "streak_count": row[1],
                "total_rewards": row[2]
            }

        # Создаем запись, если не существует
        await self.conn.execute(
            "INSERT INTO daily_rewards (user_id) VALUES (?)",
            (user_id,)
        )
        await self.conn.commit()

        return {
            "last_reward_date": None,
            "streak_count": 0,
            "total_rewards": 0
        }

    async def claim_daily_reward(self, user_id: int, reward_xp: int) -> Dict[str, Any]:
        """Выдает ежедневную награду и возвращает информацию о награде."""
        await self._ensure_connected()

        reward_info = await self.get_daily_reward_info(user_id)
        today = datetime.now().date()

        # Если уже получал награду сегодня
        if reward_info["last_reward_date"] == str(today):
            return {"success": False, "message": "Сегодня вы уже получали награду"}

        # Проверяем стрик (последовательные дни)
        yesterday = today - timedelta(days=1)
        new_streak = 1

        if reward_info["last_reward_date"] == str(yesterday):
            new_streak = reward_info["streak_count"] + 1
        elif reward_info["last_reward_date"] and reward_info["last_reward_date"] != str(today):
            # Пропустил день - сбрасываем стрик
            new_streak = 1

        # Вычисляем бонус за стрик
        streak_bonus = min(new_streak * 5, 50)  # Макс +50% за 10 дней
        total_xp = reward_xp + (reward_xp * streak_bonus // 100)

        # Обновляем данные
        await self.conn.execute(
            """UPDATE daily_rewards 
               SET last_reward_date = ?, streak_count = ?, total_rewards = total_rewards + 1 
               WHERE user_id = ?""",
            (today, new_streak, user_id)
        )

        # Начисляем XP
        new_xp, new_level = await self.add_xp(user_id, total_xp)

        await self.conn.commit()

        return {
            "success": True,
            "xp_reward": total_xp,
            "base_xp": reward_xp,
            "streak_bonus": streak_bonus,
            "new_streak": new_streak,
            "new_xp": new_xp,
            "new_level": new_level
        }

    # ---------------- ДУЭЛИ ----------------

    async def create_duels_table(self):
        """Создает таблицу для хранения статистики дуэлей"""
        await self._ensure_connected()

        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS duels (
                duel_id TEXT PRIMARY KEY,
                format_type TEXT,
                team_a_players TEXT,  -- JSON список user_id
                team_b_players TEXT,  -- JSON список user_id  
                winner_team TEXT,
                team_a_score INTEGER DEFAULT 0,
                team_b_score INTEGER DEFAULT 0,
                category TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                finished_at DATETIME
            )
        ''')

        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS duel_stats (
                user_id INTEGER,
                total_duels INTEGER DEFAULT 0,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                total_score INTEGER DEFAULT 0,
                average_score REAL DEFAULT 0,
                favorite_format TEXT,
                last_duel DATETIME,
                PRIMARY KEY (user_id),
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')

        await self.conn.commit()

    async def save_duel_result(self, duel_data: Dict):
        """Сохраняет результат дуэли"""
        await self._ensure_connected()

        try:
            await self.conn.execute('''
                INSERT INTO duels (duel_id, format_type, team_a_players, team_b_players, 
                                  winner_team, team_a_score, team_b_score, category, finished_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (
                duel_data['duel_id'],
                duel_data['format_type'],
                json.dumps(duel_data['team_a_players']),
                json.dumps(duel_data['team_b_players']),
                duel_data['winner_team'],
                duel_data['team_a_score'],
                duel_data['team_b_score'],
                duel_data['category']
            ))

            # Обновляем статистику игроков
            for user_id in duel_data['team_a_players'] + duel_data['team_b_players']:
                await self.update_duel_stats(user_id, duel_data['winner_team'], user_id in duel_data['team_a_players'])

            await self.conn.commit()
            logger.info(f"✅ Сохранен результат дуэли {duel_data['duel_id']}")

        except Exception as e:
            logger.error(f"❌ Ошибка сохранения дуэли {duel_data['duel_id']}: {e}")
            await self.conn.rollback()

    async def update_duel_stats(self, user_id: int, winner_team: str, is_team_a: bool):
        """Обновляет статистику дуэлей игрока"""
        await self._ensure_connected()

        won = (winner_team == "team_a" and is_team_a) or (winner_team == "team_b" and not is_team_a)

        await self.conn.execute('''
            INSERT INTO duel_stats (user_id, total_duels, wins, losses, last_duel)
            VALUES (?, 1, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) 
            DO UPDATE SET 
                total_duels = total_duels + 1,
                wins = wins + ?,
                losses = losses + ?,
                last_duel = CURRENT_TIMESTAMP
        ''', (user_id, 1 if won else 0, 0 if won else 1, 1 if won else 0, 0 if won else 1))

        await self.conn.commit()

    async def get_duel_stats(self, user_id: int) -> Dict:
        """Получает статистику дуэлей игрока"""
        await self._ensure_connected()

        async with self.conn.execute(
                "SELECT * FROM duel_stats WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()

        if row:
            return {
                "user_id": row[0],
                "total_duels": row[1],
                "wins": row[2],
                "losses": row[3],
                "total_score": row[4],
                "average_score": row[5],
                "favorite_format": row[6],
                "last_duel": row[7],
                "win_rate": round((row[2] / row[1] * 100) if row[1] > 0 else 0, 1)
            }

        return {
            "user_id": user_id,
            "total_duels": 0,
            "wins": 0,
            "losses": 0,
            "total_score": 0,
            "average_score": 0,
            "favorite_format": None,
            "last_duel": None,
            "win_rate": 0
        }

    async def get_user_duel_history(self, user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Получает историю дуэлей пользователя"""
        await self._ensure_connected()

        async with self.conn.execute('''
            SELECT d.duel_id, d.format_type, d.winner_team, d.team_a_score, d.team_b_score, 
                   d.category, d.created_at,
                   (CASE 
                       WHEN ? IN (SELECT value FROM json_each(d.team_a_players)) THEN 'team_a'
                       ELSE 'team_b' 
                    END) as user_team
            FROM duels d
            WHERE d.team_a_players LIKE ? OR d.team_b_players LIKE ?
            ORDER BY d.created_at DESC
            LIMIT ?
        ''', (user_id, f'%{user_id}%', f'%{user_id}%', limit)) as cursor:
            rows = await cursor.fetchall()

        history = []
        for row in rows:
            duel_id, format_type, winner_team, team_a_score, team_b_score, category, created_at, user_team = row

            history.append({
                "duel_id": duel_id,
                "format_type": format_type,
                "user_team": user_team,
                "user_won": winner_team == user_team,
                "score": f"{team_a_score}-{team_b_score}",
                "category": category,
                "created_at": created_at
            })

        return history

    async def get_duel_leaderboard(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Возвращает таблицу лидеров по дуэлям"""
        await self._ensure_connected()

        async with self.conn.execute('''
            SELECT ds.user_id, u.username, ds.wins, ds.losses, ds.total_duels,
                   ROUND((ds.wins * 100.0 / ds.total_duels), 1) as win_rate,
                   ds.total_score
            FROM duel_stats ds
            JOIN users u ON ds.user_id = u.user_id
            WHERE ds.total_duels >= 5
            ORDER BY win_rate DESC, ds.wins DESC
            LIMIT ?
        ''', (limit,)) as cursor:
            rows = await cursor.fetchall()

        return [
            {
                "user_id": row[0],
                "username": row[1] or "Аноним",
                "wins": row[2],
                "losses": row[3],
                "total_duels": row[4],
                "win_rate": row[5],
                "total_score": row[6]
            }
            for row in rows
        ]

    # ---------------- МЕТОДЫ ДЛЯ АДМИН-ПАНЕЛИ ----------------

    async def get_total_users_count(self) -> int:
        """Возвращает общее количество пользователей"""
        await self._ensure_connected()

        async with self.conn.execute("SELECT COUNT(*) FROM users") as cursor:
            result = await cursor.fetchone()
            return result[0] if result else 0

    async def get_active_users_count(self, days: int = 7) -> int:
        """Возвращает количество активных пользователей за последние N дней"""
        await self._ensure_connected()

        cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')

        async with self.conn.execute('''
            SELECT COUNT(DISTINCT user_id) 
            FROM user_stats 
            WHERE last_activity >= ?
        ''', (cutoff_date,)) as cursor:
            result = await cursor.fetchone()
            return result[0] if result else 0

    async def get_all_users(self) -> List[Dict[str, Any]]:
        """Возвращает список всех пользователей"""
        await self._ensure_connected()

        try:
            # Пробуем выполнить запрос с created_at
            async with self.conn.execute('''
                SELECT u.user_id, u.username, u.level, u.xp, u.max_combo, u.created_at,
                       us.total_answers, us.correct_answers, us.last_activity
                FROM users u
                LEFT JOIN user_stats us ON u.user_id = us.user_id
                ORDER BY u.xp DESC
            ''') as cursor:
                rows = await cursor.fetchall()
        except Exception as e:
            # Если ошибка, выполняем упрощенный запрос без created_at
            logger.warning("⚠️ Ошибка при получении пользователей: %s. Использую упрощенный запрос.", e)
            async with self.conn.execute('''
                SELECT u.user_id, u.username, u.level, u.xp, u.max_combo,
                       us.total_answers, us.correct_answers, us.last_activity
                FROM users u
                LEFT JOIN user_stats us ON u.user_id = us.user_id
                ORDER BY u.xp DESC
            ''') as cursor:
                rows = await cursor.fetchall()

        users = []
        for row in rows:
            # Обрабатываем разное количество колонок в зависимости от запроса
            if len(row) >= 9:  # Запрос с created_at
                user_id, username, level, xp, max_combo, created_at, total_answers, correct_answers, last_activity = row[
                                                                                                                     :9]
            else:  # Упрощенный запрос
                user_id, username, level, xp, max_combo, total_answers, correct_answers, last_activity = row[:8]
                created_at = None

            total_answers = total_answers or 0
            correct_answers = correct_answers or 0
            accuracy = round((correct_answers / total_answers * 100) if total_answers and total_answers > 0 else 0, 1)

            users.append({
                "user_id": user_id,
                "username": username or "Аноним",
                "level": level,
                "xp": xp,
                "max_combo": max_combo,
                "created_at": created_at,
                "total_answers": total_answers,
                "correct_answers": correct_answers,
                "last_activity": last_activity,
                "accuracy": accuracy
            })
        return users

    async def get_user_detailed_stats(self, user_id: int) -> Dict[str, Any]:
        """Получает детальную статистику пользователя для админ-панели"""
        await self._ensure_connected()

        try:
            # Пробуем запрос с created_at
            async with self.conn.execute('''
                SELECT u.user_id, u.username, u.level, u.xp, u.max_combo, u.created_at,
                       us.total_answers, us.correct_answers, us.total_combo, 
                       us.perfect_quizzes, us.categories_completed, us.last_activity,
                       (SELECT COUNT(*) FROM achievements a WHERE a.user_id = u.user_id) as achievements_count,
                       dr.streak_count, dr.total_rewards, dr.last_reward_date,
                       ds.total_duels, ds.wins, ds.losses
                FROM users u
                LEFT JOIN user_stats us ON u.user_id = us.user_id
                LEFT JOIN daily_rewards dr ON u.user_id = dr.user_id
                LEFT JOIN duel_stats ds ON u.user_id = ds.user_id
                WHERE u.user_id = ?
            ''', (user_id,)) as cursor:
                row = await cursor.fetchone()
        except Exception as e:
            # Если ошибка с created_at, используем упрощенный запрос
            logger.warning(f"Использую упрощенный запрос детальной статистики: {e}")
            async with self.conn.execute('''
                SELECT u.user_id, u.username, u.level, u.xp, u.max_combo,
                       us.total_answers, us.correct_answers, us.total_combo, 
                       us.perfect_quizzes, us.categories_completed, us.last_activity,
                       (SELECT COUNT(*) FROM achievements a WHERE a.user_id = u.user_id) as achievements_count,
                       dr.streak_count, dr.total_rewards, dr.last_reward_date,
                       ds.total_duels, ds.wins, ds.losses
                FROM users u
                LEFT JOIN user_stats us ON u.user_id = us.user_id
                LEFT JOIN daily_rewards dr ON u.user_id = dr.user_id
                LEFT JOIN duel_stats ds ON u.user_id = ds.user_id
                WHERE u.user_id = ?
            ''', (user_id,)) as cursor:
                row = await cursor.fetchone()

        if row:
            # Обрабатываем разное количество колонок в зависимости от запроса
            if len(row) >= 19:  # Запрос с created_at
                user_id, username, level, xp, max_combo, created_at, total_answers, correct_answers, total_combo, perfect_quizzes, categories_completed, last_activity, achievements_count, streak_count, total_rewards, last_reward_date, total_duels, wins, losses = row[
                                                                                                                                                                                                                                                                       :19]
            else:  # Упрощенный запрос
                user_id, username, level, xp, max_combo, total_answers, correct_answers, total_combo, perfect_quizzes, categories_completed, last_activity, achievements_count, streak_count, total_rewards, last_reward_date, total_duels, wins, losses = row[
                                                                                                                                                                                                                                                           :18]
                created_at = "Неизвестно"

            total_answers = total_answers or 0
            correct_answers = correct_answers or 0
            accuracy = round((correct_answers / total_answers * 100) if total_answers > 0 else 0, 1)

            total_duels = total_duels or 0
            duel_win_rate = round((wins / total_duels * 100) if total_duels > 0 else 0, 1)

            return {
                "user_id": user_id,
                "username": username or "Аноним",
                "level": level,
                "xp": xp,
                "max_combo": max_combo,
                "created_at": created_at,
                "total_answers": total_answers,
                "correct_answers": correct_answers,
                "total_combo": total_combo or 0,
                "perfect_quizzes": perfect_quizzes or 0,
                "categories_completed": categories_completed or 0,
                "last_activity": last_activity,
                "achievements_count": achievements_count or 0,
                "daily_streak": streak_count or 0,
                "total_rewards": total_rewards or 0,
                "last_reward_date": last_reward_date,
                "total_duels": total_duels,
                "duel_wins": wins or 0,
                "duel_losses": losses or 0,
                "duel_win_rate": duel_win_rate,
                "accuracy": accuracy
            }

        return {}

    async def get_system_stats(self) -> Dict[str, Any]:
        """Возвращает системную статистику для админ-панели"""
        await self._ensure_connected()

        stats = {}

        # Общее количество пользователей
        async with self.conn.execute("SELECT COUNT(*) FROM users") as cursor:
            stats["total_users"] = (await cursor.fetchone())[0]

        # Новые пользователи за сегодня
        today = datetime.now().date()
        async with self.conn.execute(
                "SELECT COUNT(*) FROM users WHERE DATE(created_at) = ?",
                (today,)
        ) as cursor:
            stats["new_users_today"] = (await cursor.fetchone())[0]

        # Активные пользователи за разные периоды
        stats["active_today"] = await self.get_active_users_count(1)
        stats["active_week"] = await self.get_active_users_count(7)
        stats["active_month"] = await self.get_active_users_count(30)

        # Общая статистика ответов
        async with self.conn.execute('''
            SELECT SUM(total_answers), SUM(correct_answers) 
            FROM user_stats
        ''') as cursor:
            result = await cursor.fetchone()
            stats["total_answers"] = result[0] or 0
            stats["total_correct_answers"] = result[1] or 0

        # Статистика достижений
        async with self.conn.execute("SELECT COUNT(*) FROM achievements") as cursor:
            stats["total_achievements_unlocked"] = (await cursor.fetchone())[0]

        # Статистика ежедневных наград
        async with self.conn.execute('''
            SELECT SUM(streak_count), SUM(total_rewards), COUNT(*) 
            FROM daily_rewards 
            WHERE last_reward_date = ?
        ''', (today,)) as cursor:
            result = await cursor.fetchone()
            stats["daily_rewards_today"] = result[2] or 0
            stats["total_rewards_claimed"] = result[1] or 0

        # Статистика дуэлей
        async with self.conn.execute('''
            SELECT COUNT(*), SUM(total_duels), SUM(wins) 
            FROM duel_stats
        ''') as cursor:
            result = await cursor.fetchone()
            stats["total_duels_played"] = result[1] or 0
            stats["total_duel_wins"] = result[2] or 0

        # Топ 5 пользователей
        stats["top_users"] = await self.get_top_users(5)

        return stats

    async def search_users(self, query: str) -> List[Dict[str, Any]]:
        """Поиск пользователей по username или ID"""
        await self._ensure_connected()

        search_term = f"%{query}%"

        try:
            # Пробуем запрос с created_at
            async with self.conn.execute('''
                SELECT u.user_id, u.username, u.level, u.xp, u.created_at
                FROM users u
                WHERE u.username LIKE ? OR CAST(u.user_id AS TEXT) LIKE ?
                ORDER BY u.xp DESC
                LIMIT 20
            ''', (search_term, search_term)) as cursor:
                rows = await cursor.fetchall()
        except Exception as e:
            # Если ошибка с created_at, используем упрощенный запрос
            logger.warning(f"Использую упрощенный запрос поиска: {e}")
            async with self.conn.execute('''
                SELECT u.user_id, u.username, u.level, u.xp
                FROM users u
                WHERE u.username LIKE ? OR CAST(u.user_id AS TEXT) LIKE ?
                ORDER BY u.xp DESC
                LIMIT 20
            ''', (search_term, search_term)) as cursor:
                rows = await cursor.fetchall()

        users = []
        for row in rows:
            # Обрабатываем разное количество колонок в зависимости от запроса
            if len(row) >= 5:  # Запрос с created_at
                user_id, username, level, xp, created_at = row[:5]
            else:  # Упрощенный запрос
                user_id, username, level, xp = row[:4]
                created_at = "Неизвестно"

            users.append({
                "user_id": user_id,
                "username": username or "Аноним",
                "level": level,
                "xp": xp,
                "created_at": created_at
            })

        return users

    async def delete_user(self, user_id: int) -> bool:
        """Удаляет пользователя и все его данные (админская функция)"""
        await self._ensure_connected()

        try:
            # Удаляем все связанные данные пользователя
            await self.conn.execute("DELETE FROM achievements WHERE user_id = ?", (user_id,))
            await self.conn.execute("DELETE FROM user_stats WHERE user_id = ?", (user_id,))
            await self.conn.execute("DELETE FROM daily_rewards WHERE user_id = ?", (user_id,))
            await self.conn.execute("DELETE FROM category_stats WHERE user_id = ?", (user_id,))
            await self.conn.execute("DELETE FROM duel_stats WHERE user_id = ?", (user_id,))
            await self.conn.execute("DELETE FROM users WHERE user_id = ?", (user_id,))

            await self.conn.commit()
            return True
        except Exception as e:
            logger.error("Error deleting user %d: %s", user_id, e)
            return False

    async def get_questions_stats(self) -> Dict[str, Any]:
        """Статистика по вопросам (если вопросы хранятся в БД)"""
        await self._ensure_connected()

        # TODO: Реализовать, когда вопросы будут в БД
        return {
            "total_questions": 0,
            "categories_count": 0,
            "average_difficulty": "N/A"
        }

    async def get_activity_heatmap(self, days: int = 30) -> Dict[str, int]:
        """Возвращает тепловую карту активности за последние N дней"""
        await self._ensure_connected()

        cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        async with self.conn.execute('''
            SELECT DATE(last_activity), COUNT(*) 
            FROM user_stats 
            WHERE last_activity >= ?
            GROUP BY DATE(last_activity)
            ORDER BY DATE(last_activity)
        ''', (cutoff_date,)) as cursor:
            rows = await cursor.fetchall()

        heatmap = {}
        for row in rows:
            heatmap[row[0]] = row[1]

        return heatmap

    async def cleanup_old_data(self, days: int = 30):
        """Очищает устаревшие данные (админская функция)"""
        await self._ensure_connected()

        cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        try:
            # Удаляем старые дуэли
            await self.conn.execute(
                "DELETE FROM duels WHERE created_at < ?",
                (cutoff_date,)
            )

            # Удаляем неактивных пользователей (без статистики и давно не активных)
            await self.conn.execute('''
                DELETE FROM users 
                WHERE user_id NOT IN (SELECT user_id FROM user_stats WHERE last_activity > ?)
                AND created_at < ?
            ''', (cutoff_date, cutoff_date))

            await self.conn.commit()
            logger.info(f"✅ Очищены данные старше {days} дней")

        except Exception as e:
            logger.error(f"❌ Ошибка при очистке данных: {e}")
            await self.conn.rollback()


    async def update_user_level(self, user_id: int, new_level: int):
        """Обновляет уровень пользователя"""
        await self._ensure_connected()
        try:
            await self.conn.execute(
                "UPDATE users SET level = ? WHERE user_id = ?",
                (new_level, user_id)
            )
            await self.conn.commit()
            logger.info(f"✅ Уровень пользователя {user_id} обновлен на {new_level}")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка обновления уровня пользователя {user_id}: {e}")
            return False

    async def update_user_xp(self, user_id: int, new_xp: int):
        """Обновляет XP пользователя"""
        await self._ensure_connected()
        try:
            await self.conn.execute(
                "UPDATE users SET xp = ? WHERE user_id = ?",
                (new_xp, user_id)
            )
            await self.conn.commit()
            logger.info(f"✅ XP пользователя {user_id} обновлен на {new_xp}")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка обновления XP пользователя {user_id}: {e}")
            return False

    async def reset_all_users(self) -> int:
        """
        Полный сброс прогресса всех пользователей
        Возвращает количество сброшенных пользователей
        """
        await self._ensure_connected()

        try:
            # Получаем общее количество пользователей до сброса
            total_users = await self.get_total_users_count()

            # Сбрасываем основные данные пользователей (без last_active)
            await self.conn.execute('''
                UPDATE users 
                SET level = 1, 
                    xp = 0, 
                    max_combo = 0
            ''')

            # Сбрасываем статистику пользователей
            await self.conn.execute('''
                UPDATE user_stats 
                SET total_answers = 0,
                    correct_answers = 0,
                    total_combo = 0,
                    perfect_quizzes = 0,
                    categories_completed = 0,
                    last_activity = CURRENT_TIMESTAMP
            ''')

            # Очищаем достижения
            await self.conn.execute("DELETE FROM achievements")

            # Сбрасываем ежедневные награды
            await self.conn.execute('''
                UPDATE daily_rewards 
                SET last_reward_date = NULL,
                    streak_count = 0,
                    total_rewards = 0
            ''')

            # Очищаем статистику по категориям
            await self.conn.execute("DELETE FROM category_stats")

            # Сбрасываем статистику дуэлей
            await self.conn.execute('''
                UPDATE duel_stats 
                SET total_duels = 0,
                    wins = 0,
                    losses = 0,
                    total_score = 0,
                    average_score = 0,
                    favorite_format = NULL,
                    last_duel = NULL
            ''')

            await self.conn.commit()

            logger.info(f"✅ Полный сброс системы завершен. Сброшено пользователей: {total_users}")
            return total_users

        except Exception as e:
            logger.error(f"❌ Ошибка при полном сбросе системы: {e}")
            await self.conn.rollback()
            raise


# Создаем глобальный экземпляр базы данных
db = Database()

async def init_db():
    """Инициализация базы данных"""
    try:
        await db.connect()
        logger.info("✅ База данных инициализирована")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации базы данных: {e}")
        return False

async def close_db():
    """Закрытие соединения с базой данных"""
    await db.close()

async def _migrate_database(self):
    """Упрощенная миграция базы данных"""
    try:
        # Простая миграция без DEFAULT значений
        migrations = [
            ('users', 'created_at', 'TEXT'),
            ('users', 'last_active', 'TEXT'),
            ('user_stats', 'last_activity', 'TEXT'),
        ]

        for table, column, definition in migrations:
            async with self.conn.execute(f"PRAGMA table_info({table})") as cursor:
                columns = [row[1] for row in await cursor.fetchall()]

            if column not in columns:
                await self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
                logger.info(f"✅ Добавлена колонка {column} в таблицу {table}")

        await self.conn.commit()

    except Exception as e:
        logger.error(f"❌ Ошибка миграции базы данных: {e}")
        # Не прерываем выполнение при ошибке миграции