from typing import TYPE_CHECKING

from async_lru import alru_cache

if TYPE_CHECKING:
    from shubot.database import DatabaseManager


class GroupAuthModel:
    """群组验证模型"""

    _db: "DatabaseManager"

    def __init__(self, db: "DatabaseManager"):
        self._db = db

    async def init(self):
        pass

    @alru_cache(16)
    async def is_group_authorized(self, group_id: int):
        """检查群组是否已授权。该方法会缓存结果，以减少数据库查询次数来提高性能。"""
        result = await self._db.find_one("SELECT added_at FROM authorized_groups WHERE group_id = %s", (group_id,))
        return bool(result)

    async def set_group_auth(self, group_id: int, group_name: str = "", auth: bool = False):
        """设置群组授权状态"""
        if auth:
            rowcount = await self._db.update(
                """
                    INSERT INTO authorized_groups (group_id, group_name)
                    VALUES (%s, %s)
                    ON DUPLICATE KEY UPDATE
                        group_name = %s,
                        added_at = UTC_TIMESTAMP();
                """,
                (group_id, group_name, group_name),
            )
        else:
            rowcount = await self._db.update(
                """
                    DELETE FROM authorized_groups WHERE group_id = %s;
                    """,
                (group_id,),
            )

        # 清除授权状态缓存
        self.is_group_authorized.cache_invalidate(group_id)
        return rowcount > 0

    async def allow_group(self, group_id: int, name: str):
        """授权一个群组使用机器人"""
        await self.set_group_auth(group_id, name, True)

    async def disallow_group(self, group_id: int):
        """取消授权一个群组使用机器人"""
        await self.set_group_auth(group_id, "", False)
