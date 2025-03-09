import enum
import logging
from os import path
from typing import cast

import aiomysql
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
from telegram.ext.filters import ChatType

from shubot.config import Config
from shubot.database import DatabaseManager
from shubot.ext.bot_helper import BotHelperMixin

logger = logging.getLogger(__name__)


class LotteryUpdateStatus(enum.IntEnum):
    """从数据库锁定一次乐透机会"""

    EXCEPTION = 0
    """发生异常"""
    DAILY_LIMIT_EXCEEDED = -1
    """超过每日次数限制"""
    INSUFFICIENT_FUNDS = -2
    """积分不足"""
    SUCCESS = 1
    """成功"""


class LotteryCommand(BotHelperMixin):
    """刮刮乐透"""

    def __init__(self, app: Application, config: Config, db: DatabaseManager | None = None):
        super().__init__(app, config, db)

        self._app.add_handler(CommandHandler(["gua", "lottery"], self._handle_lottery, filters=ChatType.GROUPS))
        self._app.add_handler(CallbackQueryHandler(self._handle_lottery_entry, pattern=r"^lottery_"))

    async def init_db(self):
        init_sql = path.join(path.dirname(__file__), "lottery_init.sql")
        with open(init_sql, "r", encoding="utf-8") as f:
            await self._db.update(f.read())

    async def _handle_lottery(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """响应 /gua 命令，刮刮乐透"""
        message = update.message
        uid = message.from_user.id

        msgs = self._config.lottery.messages

        sent_msg = await self.reply(
            message,
            msgs.game.format(daily_limit=self._config.lottery.daily_limit),
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton(msgs.btn_cost.format(**p.__dict__), callback_data=f"lottery_{p.cost}_{uid}")]
                    for p in self._config.lottery.prizes
                ]
            ),
        )

    async def _handle_lottery_entry(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """响应刮刮乐按钮点击事件"""
        config = self._config.lottery
        msgs = config.messages
        query = update.callback_query
        _, cost, owner = query.data.split("_")
        cost, owner = int(cost), int(owner)

        if owner != query.from_user.id:
            await query.answer(msgs.owner_mismatch, show_alert=True)
            return

        await query.answer()
        self.delete(cast(Message, query.message), 30)
        won = self.chance_hit(config.chance)
        prize = next((p.prize for p in config.prizes if p.cost == cost), 0)

        status, old_balance, new_balance, today_drawn = await self._do_lottery_update(owner, cost, prize if won else 0)
        match status:
            case LotteryUpdateStatus.DAILY_LIMIT_EXCEEDED:
                return await query.edit_message_text(msgs.daily_limit_exceeded)
            case LotteryUpdateStatus.INSUFFICIENT_FUNDS:
                return await query.edit_message_text(msgs.insufficient_funds.format(cost=cost, balance=old_balance))
            case LotteryUpdateStatus.EXCEPTION:
                return await query.edit_message_text("❌ 抽奖时发生异常，请稍后再试 (SQL Exception)")

        numbers = list(range(*config.number_range.to_tuple()))
        self._rnd.shuffle(numbers)

        winner = numbers[0 if won else -1]
        numbers_drawn = sorted(numbers[: config.select_count])
        result = f"🎉 中奖！积分更变 {old_balance} → {new_balance} (+{prize})" if won else "❌ 未中奖"

        finish_message_text = msgs.finish.format(
            winner=winner,
            numbers_drawn=" ".join(map(str, numbers_drawn)),
            result=result,
            prize=prize,
            remaining=config.daily_limit - today_drawn,
            daily_limit=config.daily_limit,
        )
        await query.edit_message_text(finish_message_text)

    async def _do_lottery_update(self, uid: int, cost: int, prize: int) -> tuple[LotteryUpdateStatus, int, int, int]:
        async with self._db.acquire() as conn:
            async with conn.cursor() as cursor:  # type: aiomysql.Cursor
                await cursor.execute(
                    "CALL shubot_lottery(%s, %s, %s, %s)",
                    (uid, self._config.lottery.daily_limit, cost, prize),
                )
                result_code, old_balance, new_balance, daily_count = await cursor.fetchone()
                return LotteryUpdateStatus(result_code), old_balance, new_balance, daily_count
