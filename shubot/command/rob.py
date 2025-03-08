import asyncio
import enum
import logging
from asyncio import Future
from dataclasses import dataclass
from math import copysign
from os import path
from typing import cast

import aiomysql
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, Message
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
from telegram.ext.filters import ChatType

from shubot.config import Config
from shubot.database import DatabaseManager
from shubot.ext.command import BotCommandHandlerMixin
from shubot.ext.cult_helper import CultivationHelperMixin
from shubot.util import reply as del_and_reply, defer_delete

logger = logging.getLogger(__name__)


class RobResult(enum.IntEnum):
    """从数据库获得的打劫结果"""

    EXCEPTION = 0
    """发生异常"""
    FIRST_TIME_SUCCESS = 1
    """初次打劫"""
    NEW_DAY_SUCCESS = 2
    """当日第一次打劫"""
    SAME_DAY_SUCCESS = 3
    """当日多次打劫"""
    LIMIT_REACHED = -1
    """达到当日打劫次数上限"""
    COOLDOWN = -2
    """冷却中"""


class RobTransferResult(enum.IntEnum):
    """从数据库获得的打劫结果"""

    EXCEPTION = 0
    """发生异常"""
    SUCCESS = 1
    """转账成功"""
    LOSER_NO_MONEY = -1
    """输家没钱"""
    STOLEN_ZERO = -2
    """偷盗 0 灵石，如偷"""


@dataclass
class RobActionPayload:
    """打劫操作的数据载荷"""

    action: str
    winner_id: int
    loser_id: int


class RobCommand(BotCommandHandlerMixin, CultivationHelperMixin):
    """打劫模块"""

    _app: Application
    _config: Config
    _db: DatabaseManager

    def __init__(self, app: Application, config: Config, db: DatabaseManager | None = None):
        self._db = db or DatabaseManager.get_instance()
        self._app = app
        self._config = config

        self._app.add_handler(CommandHandler(["rob", "dajie"], self._handle_rob, filters=ChatType.GROUPS))
        self._app.add_handler(CallbackQueryHandler(self._handle_rob_action, pattern=r"^rob_"))

    async def init_db(self):
        init_sql = path.join(path.dirname(__file__), "rob_init.sql")
        with open(init_sql, "r", encoding="utf-8") as f:
            await self._db.update(f.read())

    async def _handle_rob(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # 打劫
        message = update.message
        reply_to = message.reply_to_message

        if not reply_to or reply_to.from_user.is_bot:
            reply = await del_and_reply(message, "🦹 请对目标修士的消息回复使用此命令")
            return defer_delete(context.job_queue, reply, 10)

        robber_user = message.from_user
        victim_user = reply_to.from_user

        if robber_user.id == victim_user.id:
            return await self.reply(message, "🤡 道友为何要自劫？")

        # 检查次数限制
        result, today_count = await self._try_rob(robber_user.id)
        match result:
            case RobResult.COOLDOWN:
                return await self.reply(
                    message,
                    reply="🛑 今日打劫次数已用尽，明日请早",
                    del_source_timeout=0,
                )
            case RobResult.LIMIT_REACHED:
                return await self.reply(
                    message,
                    reply="🚧 道友出手太快，需调息片刻",
                    del_source_timeout=0,
                )

        # 获取境界
        [victim_cult, robber_cult] = await asyncio.gather(
            self._db.User.get_cultivation_data(victim_user.id),
            self._db.User.get_cultivation_data(robber_user.id),
        )

        # 检查境界
        major_stage_delta = robber_cult.major_stage - victim_cult.major_stage
        tpl_var = dict(
            robber=robber_user.full_name,
            robber_stage=self._get_cult_stage_name(robber_cult.stage),
            victim=victim_user.full_name,
            victim_stage=self._get_cult_stage_name(victim_cult.stage),
        )
        if major_stage_delta < -1:
            return await self.reply(message, self._config.rob.messages.too_weak.format(**tpl_var))
        elif major_stage_delta > 1:
            return await self.reply(message, self._config.rob.messages.too_strong.format(**tpl_var))

        if self.chance_hit(self._config.rob.escape_chance):
            # 逃跑成功
            dice_msg, dice_face = await self.dice_roll(message.chat_id)
            self.delete(dice_msg, 5)

            escape_msg = self._rnd.choice(self._config.rob.messages.escapes).format(**tpl_var)
            return await self.reply(message, escape_msg, del_source_timeout=0, del_reply_timeout=8)

        # 摇点
        ((robber_dice_message, robber_roll), (victim_dice_message, victim_roll)) = await asyncio.gather(
            self.dice_roll(message.chat_id),
            self.dice_roll(message.chat_id),
        )
        self.delete(robber_dice_message, 8)
        self.delete(victim_dice_message, 8)

        # 计算赢家
        robber_bonus = copysign(self._config.rob.stage_bonus, robber_cult.stage - victim_cult.stage)
        robber_pt_delta = robber_roll - victim_roll + robber_bonus

        if robber_pt_delta == 0:
            return await self.reply(message, self._config.rob.messages.tie.format(**tpl_var))

        # 计算输家、赢家
        winner, loser = (robber_user, victim_user) if robber_pt_delta > 0 else (victim_user, robber_user)
        tpl_var.update(winner=winner.full_name, loser=loser.full_name)

        # 让输家进行选择
        btn_pay = InlineKeyboardButton("💰 破财消灾", callback_data=f"rob_pay_{winner.id}_{loser.id}")
        btn_fight = InlineKeyboardButton("⚔️ 死战到底", callback_data=f"rob_fight_{winner.id}_{loser.id}")
        loser_action_msg = await context.bot.send_message(
            chat_id=message.chat_id,
            text=self._rnd.choice(self._config.rob.messages.rob_action_descriptions).format(**tpl_var),
            reply_markup=InlineKeyboardMarkup([[btn_pay], [btn_fight]]),
        )
        self.delete(message, 0)
        self.delete(loser_action_msg, 60)

    async def _handle_rob_action(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # 处理打劫输家的选择
        query = update.callback_query

        _, action, winner_id, loser_id = query.data.split("_")
        winner_id, loser_id = int(winner_id), int(loser_id)

        if query.from_user.id != loser_id:
            loser_user = await context.bot.get_chat(loser_id)
            return await query.answer(f"🚫 只有 {loser_user.full_name} 可以操作！", show_alert=True)

        await query.answer()
        match action:
            case "pay":
                await self._handle_rob_action_pay(winner_id, loser_id, update, context)
            case "fight":
                await self._handle_rob_action_fight(winner_id, loser_id, update, context)

        # Cleanup
        self.delete(cast(Message, query.message), 8)

    async def _handle_rob_action_pay(
        self, winner_id: int, loser_id: int, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """打劫输家选择「破财消灾」"""
        query = update.callback_query
        steal_ratio = self._rnd.uniform(*self._config.rob.penalty_ratio.to_tuple())
        (loser, (transfer_status, rob_amount, loser_pts, winner_pts)) = await asyncio.gather(
            context.bot.get_chat(loser_id),
            self._rob_transfer(loser_id, winner_id, steal_ratio),
        )

        tpl_vars = dict(loser=loser.full_name, rob_amount=rob_amount, winner_pts=winner_pts, loser_pts=loser_pts)

        match transfer_status:
            case RobTransferResult.LOSER_NO_MONEY | RobTransferResult.STOLEN_ZERO:
                await query.edit_message_text(
                    self._rnd.choice(self._config.rob.messages.steal_empty).format(**tpl_vars)
                )
            case RobTransferResult.SUCCESS:
                await query.edit_message_text(
                    self._rnd.choice(self._config.rob.messages.steal_complete).format(**tpl_vars)
                )
            case _:
                await query.edit_message_text("🚫 未知错误，请联系管理员 (SQL Exception)")

    async def _handle_rob_action_fight(
        self, winner_id: int, loser_id: int, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """打劫输家选择「死战到底」"""
        query = update.callback_query
        message = cast(Message, query.message)

        # 摇点
        ((winner_dice_message, winner_roll), (loser_dice_message, loser_roll), loser) = await asyncio.gather(
            self.dice_roll(message.chat_id),
            self.dice_roll(message.chat_id),
            context.bot.get_chat(loser_id),
        )
        self.delete(winner_dice_message, 5)
        self.delete(loser_dice_message, 5)

        reset_user_cond = Future()
        if winner_roll > loser_roll:
            reset_user_cond = self._rob_reset_user(loser_id)
            template = self._rnd.choice(self._config.rob.messages.fight_lose)
        else:
            reset_user_cond.set_result(True)
            template = self._rnd.choice(self._config.rob.messages.fight_win)

        sql_ok, _ = await asyncio.gather(
            reset_user_cond,
            query.edit_message_text(template.format(loser=loser.full_name)),
        )

        if not sql_ok:
            await query.edit_message_text("🚫 未知错误，请联系管理员 (SQL Exception)")

    async def _try_rob(self, uid: int) -> tuple[RobResult, int]:
        async with self._db.acquire() as conn:
            async with conn.cursor() as cursor:  # type: aiomysql.Cursor
                await cursor.execute(
                    "CALL shubot_rob_user(%s, %s, %s)",
                    (uid, self._config.rob.cooldown, self._config.rob.daily_limit),
                )
                result_code, new_rob_count = await cursor.fetchone()
                return RobResult(result_code), new_rob_count

    async def _rob_transfer(
        self, loser_id: int, winner_id: int, steal_ratio: float
    ) -> tuple[RobTransferResult, int, int, int]:
        async with self._db.acquire() as conn:
            async with conn.cursor() as cursor:  # type: aiomysql.Cursor
                await cursor.execute(
                    "CALL shubot_rob_transfer(%s, %s, %s)",
                    (loser_id, winner_id, steal_ratio),
                )
                result_code, rob_amount, loser_pts, winner_pts = await cursor.fetchone()
                return RobTransferResult(result_code), rob_amount, loser_pts, winner_pts

    async def _rob_reset_user(self, loser_id: int) -> bool:
        async with self._db.acquire() as conn:
            async with conn.cursor() as cursor:  # type: aiomysql.Cursor
                await cursor.execute("CALL shubot_rob_reset_user(%s)", (loser_id,))
                (result_code,) = await cursor.fetchone()
                return result_code == 1
