import logging
import random
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncIterator, Optional, Any

import aiomysql

from shubot.config import DatabaseConfig

logger = logging.getLogger(__name__)


class DatabaseManager:
    _instance: 'DatabaseManager'
    """全局数据库对象"""

    @staticmethod
    def get_instance() -> 'DatabaseManager':
        return DatabaseManager._instance

    _pool: None | aiomysql.Pool

    def __init__(self):
        self._pool = None

    async def init_pool(self, config: DatabaseConfig):
        self._pool = await aiomysql.create_pool(
            host=config.host,
            port=config.port,
            user=config.user,
            password=config.password,
            db=config.db,
            autocommit=False
        )

    @asynccontextmanager
    async def get_cursor(self) -> AsyncIterator[aiomysql.Cursor]:
        async with self._pool.acquire() as conn:  # type: aiomysql.Connection
            async with conn.cursor() as cursor:  # type: aiomysql.Cursor
                yield cursor

    async def is_group_authorized(self, group_id: int) -> bool:
        async with self.get_cursor() as cursor:
            await cursor.execute(
                "SELECT 1 FROM authorized_groups WHERE group_id = %s",
                (group_id,)
            )
            return bool(await cursor.fetchone())

    def get_pool(self) -> aiomysql.Pool:
        return self._pool

    def acquire(self) -> aiomysql.Connection:
        return self._pool.acquire()

    async def add_authorized_group(self, group_id: int, group_name: str):
        pool = self.get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """INSERT INTO authorized_groups (group_id, group_name)
                        VALUES (%s, %s)
                        ON DUPLICATE KEY UPDATE group_name = VALUES(group_name)""",
                    (group_id, group_name)
                )
            await conn.commit()

    async def get_user_state(self, user_id: int) -> dict:
        pool = self.get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """INSERT IGNORE INTO users (user_id, points) 
                       VALUES (%s, 0)""",
                    (user_id,)
                )
                await cursor.execute(
                    """INSERT IGNORE INTO user_cultivation (user_id) 
                       VALUES (%s)""",
                    (user_id,)
                )

                await cursor.execute(
                    "SELECT points FROM users WHERE user_id = %s",
                    (user_id,)
                )
                points_row = await cursor.fetchone()

                await cursor.execute(
                    "SELECT stage, pills, next_cost FROM user_cultivation WHERE user_id = %s",
                    (user_id,)
                )
                cult_row = await cursor.fetchone()

                await conn.commit()

                return {
                    "points": points_row[0] if points_row else 0,
                    "stage": cult_row[0] if cult_row else 0,
                    "pills": cult_row[1] if cult_row else 0,
                    "next_cost": cult_row[2] if cult_row else 10
                }

    async def remove_authorized_group(self, group_id: int):
        pool = self.get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    "DELETE FROM authorized_groups WHERE group_id = %s",
                    (group_id,)
                )
            await conn.commit()

    async def get_all_groups(self):
        pool = self.get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("SELECT group_id FROM authorized_groups")
                return [row[0] for row in await cursor.fetchall()]

    async def record_gua_usage(self, user_id: int, daily_limit: int = 5) -> bool:
        pool = self.get_pool()
        today = datetime.utcnow().date()
        async with pool.acquire() as conn:
            try:
                async with conn.cursor() as cursor:
                    await cursor.execute("""
                        SELECT times_used FROM gua_records
                        WHERE user_id = %s AND date = %s
                        FOR UPDATE
                    """, (user_id, today))
                    result = await cursor.fetchone()

                    current = result[0] if result else 0
                    if current >= daily_limit:
                        return False

                    await cursor.execute("""
                        INSERT INTO gua_records (user_id, date, times_used)
                        VALUES (%s, %s, 1)
                        ON DUPLICATE KEY UPDATE
                        times_used = times_used + 1
                    """, (user_id, today))

                    await conn.commit()
                    return True

            except Exception as e:
                await conn.rollback()
                logger.error(f"记录刮刮乐使用失败：{str(e)}")
                return False

    async def daily_checkin(self, user_id: int, username: str) -> tuple[int, bool]:
        # 签到
        pool = self.get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("SELECT UTC_TIMESTAMP()")
                current_utc = (await cursor.fetchone())[0]
                current_date = current_utc.date()
                await cursor.execute(
                    """SELECT CONVERT_TZ(last_checkin, 
                        @@session.time_zone, '+00:00') 
                       FROM users WHERE user_id = %s""",
                    (user_id,)
                )
                result = await cursor.fetchone()

                # 判断是否已签到
                if result and result[0]:
                    last_checkin_utc = result[0].replace(tzinfo=timezone.utc)
                    if last_checkin_utc.date() == current_date:
                        return 0, False

                # 生成随机积分
                points = random.randint(1, 10)

                await cursor.execute(
                    """""",
                    (user_id, username, points)
                )
                await conn.commit()
                return points, True

    async def deduct_points(self, user_id: int, amount: int) -> bool:
        pool = self.get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    "SELECT points FROM users WHERE user_id = %s FOR UPDATE",
                    (user_id,)
                )
                result = await cursor.fetchone()

                if not result or result[0] < amount:
                    return False

                await cursor.execute(
                    "UPDATE users SET points = points - %s WHERE user_id = %s",
                    (amount, user_id)
                )
                await conn.commit()
                return True

    async def get_cultivation_data(self, user_id: int) -> dict:
        pool = self.get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """INSERT INTO user_cultivation (user_id, stage, pills, next_cost)
                       VALUES (%s, 0, 0, 10)
                       ON DUPLICATE KEY UPDATE
                       user_id = VALUES(user_id)""",
                    (user_id,)
                )
                await cursor.execute(
                    "SELECT stage, pills, next_cost FROM user_cultivation WHERE user_id = %s",
                    (user_id,)
                )
                result = await cursor.fetchone()
                await conn.commit()
                return dict(zip(['stage', 'pills', 'next_cost'], result)) if result else None

    async def update_cultivation_stage(self, user_id: int, new_stage: int, new_cost: int):
        pool = self.get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """UPDATE user_cultivation 
                       SET stage = %s, next_cost = %s 
                       WHERE user_id = %s""",
                    (new_stage, new_cost, user_id)
                )
                await conn.commit()

    async def add_breakthrough_pill(self, user_id: int, amount: int = 1):
        pool = self.get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """UPDATE user_cultivation 
                       SET pills = pills + %s 
                       WHERE user_id = %s""",
                    (amount, user_id)
                )
                await conn.commit()

    async def get_user_points(self, user_id: int) -> int:
        pool = self.get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    "SELECT points FROM users WHERE user_id = %s",
                    (user_id,)
                )
                result = await cursor.fetchone()
                return result[0] if result else 0

    async def modify_points(self, user_id: int, delta: int) -> int:
        pool = self.get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """INSERT INTO users (user_id, points)
                       VALUES (%s, %s)
                       ON DUPLICATE KEY UPDATE
                       username = VALUES(username)""",
                    (user_id, max(delta, 0))
                )

                await cursor.execute(
                    "UPDATE users SET points = GREATEST(points + %s, 0) WHERE user_id = %s",
                    (delta, user_id)
                )

                await cursor.execute(
                    "SELECT points FROM users WHERE user_id = %s",
                    (user_id,)
                )
                result = await cursor.fetchone()
                await conn.commit()
                return result[0] if result else 0

    async def check_md5_exists(self, md5: str) -> bool:
        pool = self.get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("SELECT 1 FROM files WHERE md5 = %s", (md5,))
                return bool(await cursor.fetchone())

    async def update_user_points(self, user_id: int, username: str, points_delta: int = 10):
        # 更新积分
        pool = self.get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """INSERT INTO users (user_id, username, points)
                       VALUES (%s, %s, %s)
                       ON DUPLICATE KEY UPDATE
                       points = points + VALUES(points),
                       username = VALUES(username)""",
                    (user_id, username, points_delta)
                )
            await conn.commit()

    async def record_new_file(self, user_id: int, md5: str):
        # 记录新文件
        pool = self.get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    "INSERT INTO files (md5, user_id) VALUES (%s, %s)",
                    (md5, user_id)
                )
            await conn.commit()

    async def record_rob(self, user_id: int, cooldown: int = 60) -> bool:
        # 记录打劫次数
        pool = self.get_pool()
        now = datetime.utcnow()
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("""
                    CREATE TABLE IF NOT EXISTS rob_records (
                        user_id BIGINT PRIMARY KEY,
                        last_rob TIMESTAMP,
                        count INT DEFAULT 0,
                        FOREIGN KEY (user_id) REFERENCES users(user_id)
                    )
                """)

                await cursor.execute(
                    "SELECT last_rob FROM rob_records WHERE user_id = %s",
                    (user_id,)
                )
                result = await cursor.fetchone()
                if result and (now - result[0]).seconds < cooldown:
                    return False

                await cursor.execute("""
                    INSERT INTO rob_records (user_id, last_rob, count)
                    VALUES (%s, %s, 1)
                    ON DUPLICATE KEY UPDATE
                    last_rob = VALUES(last_rob),
                    count = IF(DATE(last_rob) != CURDATE(), 1, count + 1)
                """, (user_id, now))

                await conn.commit()
                return True

    async def get_rob_count(self, user_id: int) -> int:
        # 获取当日打劫次数
        pool = self.get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    "SELECT count FROM rob_records WHERE user_id = %s",
                    (user_id,)
                )
                result = await cursor.fetchone()
                return result[0] if result else 0

    async def silent_add_points(self, user_id: int, username: str):
        # 水群分
        try:
            pool = self.get_pool()
            async with pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(
                        """INSERT INTO users (user_id, username, points)
                           VALUES (%s, %s, 1)
                           ON DUPLICATE KEY UPDATE
                           points = points + 1,
                           username = VALUES(username)""",
                        (user_id, username)
                    )
                    await conn.commit()
                    return True
        except Exception as e:
            logger.error(f"数据库操作失败：{str(e)}")
            return False

    async def find_one(self, query: str, args: tuple[Any, ...] | None = None) -> Any:
        async with self.get_cursor() as cursor:
            await cursor.execute(query, args)
            return await cursor.fetchone()

    async def update(self, query: str, args: tuple[Any, ...] | None = None) -> int:
        """执行更新操作，返回受影响行数"""
        async with self.acquire() as conn:
            async with conn.cursor() as cursor: # type: aiomysql.Cursor
                await cursor.execute(query, args)
                row_count = cursor.rowcount
                await conn.commit()
                return row_count


DatabaseManager._instance = DatabaseManager()
