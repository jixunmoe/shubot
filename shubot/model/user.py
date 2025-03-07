from dataclasses import dataclass, field
from os import path
from typing import TYPE_CHECKING

from telegram import User

if TYPE_CHECKING:
    from shubot.database import DatabaseManager


@dataclass
class CultivationRecord:
    """修仙数据记录"""

    user_id: int
    stage: int = field(default=0)
    """当前境界"""
    pills: int = field(default=0)
    """突破丹数量"""
    next_cost: int = field(default=10)
    """下次突破所需积分"""

    @property
    def major_stage(self) -> int:
        """主境界"""
        return self.stage // 3


class UserModel:
    _db: "DatabaseManager"

    def __init__(self, db: "DatabaseManager"):
        self._db = db

    async def init(self):
        init_sql = path.join(path.dirname(__file__), "user_init.sql")
        with open(init_sql, "r", encoding="utf-8") as f:
            await self._db.update(f.read())

    async def ensure_exists_inner(self, user_id: int, username: str):
        """通用函数：确保用户存在 (手动指定信息)"""
        return await self._db.update(
            """
            INSERT IGNORE INTO users (user_id, username)
            VALUES (%s, %s);
            INSERT IGNORE INTO user_cultivation (user_id, pills, stage, next_cost)
            VALUES (%s, 0, 0, 10);
        """,
            (user_id, username, user_id),
        )

    async def ensure_exists(self, user: User):
        """通用函数：确保用户存在"""
        return await self.ensure_exists_inner(user_id=user.id, username=user.username)

    async def get_points(self, user_id: int) -> int:
        """获取用户的积分"""
        result = await self._db.find_one("""SELECT points FROM users WHERE user_id = %s""", (user_id,))
        return result[0] if result else 0

    async def modify_points(self, user_id: int, delta: int):
        """修改用户的积分。若是新的分数为负数，则修改为 0。返回旧的和新的积分。"""
        _, (status, old_points, new_points) = await self._db.call("shubot_common_user_update_pts", user_id, delta)
        if status <= 0:
            raise ValueError("Failed to update points")
        return old_points, new_points

    async def get_cultivation_data(self, user_id: int) -> CultivationRecord:
        """获取用户的修仙数据"""
        data = await self._db.find_one(
            """
            SELECT stage, pills, next_cost
            FROM user_cultivation
            WHERE user_id = %s
        """,
            (user_id,),
        )
        return CultivationRecord(user_id, *(data or []))
