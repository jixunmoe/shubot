import enum
import logging
from functools import lru_cache
from typing import cast

import aiomysql
from telegram import Update, User
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.ext.filters import ChatType
from telegram.helpers import escape_markdown

from shubot.config import Config
from shubot.database import DatabaseManager
from shubot.ext.command import BotCommandHandlerMixin
from shubot.ext.cult_helper import CultivationHelperMixin

logger = logging.getLogger(__name__)


class BreakThoughStatus(enum.IntEnum):
    """突破状态"""

    OK = 0
    """条件满足，进行了一次突破"""
    LEVEL_TOO_HIGH = 1
    """已达到最大境界"""
    INSUFFICIENT_PILLS = 2
    """丹药不足"""
    INSUFFICIENT_POINTS = 3
    """积分不足"""
    ACCOUNT_MISSING = 5
    """没有积分帐号"""


class CultivationCommand(BotCommandHandlerMixin, CultivationHelperMixin):
    _app: Application
    _config: Config
    _db: DatabaseManager

    def __init__(self, app: Application, config: Config, db: DatabaseManager | None = None):
        self._db = db or DatabaseManager.get_instance()
        self._app = app
        self._config = config

        self._app.add_handler(CommandHandler("breakthrough", self._handle_breakthrough, filters=ChatType.GROUPS))

    async def _handle_breakthrough(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """境界突破指令"""
        user = update.effective_user
        message = update.message

        await self._db.User.ensure_exists(user)

        msgs = self._config.cultivation.messages
        match await self._breakthrough(user, self._rnd.random()):
            case (BreakThoughStatus.ACCOUNT_MISSING,):
                return await self.reply(message, msgs.account_missing)

            case (BreakThoughStatus.LEVEL_TOO_HIGH, _):
                return await self.reply(message, msgs.level_too_high)

            case (BreakThoughStatus.INSUFFICIENT_PILLS, pill_cost, pills):
                return await self.reply(message, msgs.insufficient_pills.format(cost=pill_cost, pills=pills))

            case (BreakThoughStatus.INSUFFICIENT_POINTS, _, stage, cost, points):
                return await self.reply(
                    message,
                    msgs.insufficient_pts.format(
                        stage=escape_markdown(self._get_cult_stage_name(stage), 2),
                        cost=cost,
                        points=points,
                        missing=cost - points,
                    ),
                )

            case (BreakThoughStatus.OK, success, _, stage, stage_delta, pill_cost, cost, next_cost):
                stage_name = self._get_cult_stage_name(stage)
                next_stage = self._get_cult_stage_name(stage + stage_delta)
                tpl_vars = dict(
                    stage=escape_markdown(stage_name, 2),
                    next_stage=escape_markdown(next_stage, 2),
                    name=escape_markdown(user.full_name, 2),
                    pill_cost=pill_cost,
                    cost=cost,
                    next_cost=next_cost,
                )
                if success:
                    header = self._rnd.choice(msgs.breakthrough_success_header).format(**tpl_vars)
                    text = msgs.breakthrough_success.format(**tpl_vars, header=header)
                else:
                    reason = self._rnd.choice(msgs.breakthrough_fail_reason)
                    text = msgs.breakthrough_fail.format(**tpl_vars, reason=reason)
                return await self.reply(message, text, parse_mode=ParseMode.MARKDOWN_V2)

    async def _breakthrough(self, user: User, chance_value: float) -> tuple[int, ...]:
        """进行一次突破"""
        async with self._db.acquire() as conn:  # type: aiomysql.Connection
            async with conn.cursor() as cursor:  # type: aiomysql.Cursor
                await cursor.execute(
                    """
                    SELECT uc.stage, uc.next_cost, uc.pills, u.points
                    FROM user_cultivation uc
                    JOIN users u ON u.user_id = uc.user_id
                    WHERE uc.user_id = %s
                    FOR UPDATE
                """,
                    (user.id,),
                )

                initial_fetch = cast(tuple[int, int, int, int], await cursor.fetchone())
                if not initial_fetch:
                    return (BreakThoughStatus.ACCOUNT_MISSING,)

                stage, cost, pills, points = initial_fetch
                is_major = stage in self.major_levels
                pill_cost = self._config.cultivation.major_pill_cost if is_major else 0

                if stage >= self.max_cult_stage:
                    return BreakThoughStatus.LEVEL_TOO_HIGH, stage
                if is_major and pills < pill_cost:
                    return BreakThoughStatus.INSUFFICIENT_PILLS, pill_cost, pills
                if points < cost:
                    return BreakThoughStatus.INSUFFICIENT_POINTS, is_major, stage, cost, points

                chance = self._get_breakthrough_chance(stage)
                success = chance_value <= chance

                pt_cost = int(cost * 0.3) if not success else cost
                stage_delta = 1 if success else 0
                next_cost = int(cost * (2 if is_major else 1.5)) if success else cost
                await cursor.execute(
                    """
                        UPDATE user_cultivation uc
                        JOIN users u ON u.user_id = uc.user_id
                        SET u.points = u.points - %s,
                            uc.stage = uc.stage + %s, uc.pills = uc.pills - %s, uc.next_cost = %s
                        WHERE uc.user_id = %s;
                    """,
                    (pt_cost, stage_delta, pill_cost, next_cost, user.id),
                )
                await conn.commit()
        return BreakThoughStatus.OK, success, is_major, stage, stage_delta, pill_cost, pt_cost, next_cost

    @lru_cache
    def _get_breakthrough_chance(self, stage: int) -> float:
        """获取突破成功率"""
        return next((c.chance for c in self._config.cultivation.major_level_up_chances if c.level == stage), 1.0)

    @property
    @lru_cache
    def major_levels(self):
        """大境界等级列表"""
        return list(c.level for c in self._config.cultivation.major_level_up_chances)
