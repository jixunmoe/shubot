import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, Any

import aiomysql

from shubot.config import DatabaseConfig
from shubot.model.user import UserModel

logger = logging.getLogger(__name__)


class DatabaseManager:
    _instance: "DatabaseManager"
    """全局数据库对象"""

    @staticmethod
    def get_instance() -> "DatabaseManager":
        return DatabaseManager._instance

    _pool: None | aiomysql.Pool

    User: UserModel

    def __init__(self):
        self._pool = None
        self.User = UserModel(self)

    async def init_pool(self, config: DatabaseConfig):
        self._pool = await aiomysql.create_pool(
            host=config.host,
            port=config.port,
            user=config.user,
            password=config.password,
            db=config.db,
            autocommit=False,
        )

    @asynccontextmanager
    async def get_cursor(self) -> AsyncIterator[aiomysql.Cursor]:
        async with self._pool.acquire() as conn:  # type: aiomysql.Connection
            async with conn.cursor() as cursor:  # type: aiomysql.Cursor
                yield cursor

    def get_pool(self) -> aiomysql.Pool:
        return self._pool

    def acquire(self) -> aiomysql.Connection:
        return self._pool.acquire()

    async def find_one(self, query: str, args: tuple[Any, ...] | None = None) -> Any:
        async with self.get_cursor() as cursor:
            await cursor.execute(query, args)
            return await cursor.fetchone()

    async def update(self, query: str, args: tuple[Any, ...] | None = None) -> int:
        """执行更新操作，返回受影响行数"""
        async with self.acquire() as conn:
            async with conn.cursor() as cursor:  # type: aiomysql.Cursor
                await cursor.execute(query, args)
                row_count = cursor.rowcount
                await conn.commit()
                return row_count


DatabaseManager._instance = DatabaseManager()
