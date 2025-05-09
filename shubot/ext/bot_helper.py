import asyncio
from datetime import datetime, UTC
from random import SystemRandom
from typing import cast

from telegram import Message, Bot, User
from telegram.ext import Application, CallbackContext

from shubot.config import Config
from shubot.database import DatabaseManager


async def _delete_message(ctx: CallbackContext):
    data = cast(dict, ctx.job.data)
    await ctx.bot.delete_message(**data)


class BotHelperMixin:
    _app: Application
    _config: Config
    _rnd = SystemRandom()

    def __init__(self, app: Application, config: Config, db: DatabaseManager | None = None):
        """初始化基础信息"""
        self._app = app
        self._config = config
        self._db = db or DatabaseManager.get_instance()

    @property
    def bot(self) -> Bot:
        # noinspection PyUnresolvedReferences
        return self._app.bot

    def is_admin(self, user: User | int) -> bool:
        user_id = cast(int, user.id if isinstance(user, User) else user)
        return user_id in self._config.telegram.admin_ids

    def chance_hit(self, chance: float) -> bool:
        """根据概率判断是否命中。chance 为 0 到 1 之间的浮点数"""
        return self._rnd.random() <= chance

    async def dice_roll(self, chat_id: int, dice_timeout: int = 3.5) -> tuple[Message, int]:
        """发送骰子表情并获取结果 (信息对象, 骰子点数)"""
        msg, _ = await asyncio.gather(self.bot.send_dice(chat_id, emoji="🎲"), asyncio.sleep(dice_timeout))
        return msg, msg.dice.value

    async def init_db(self):
        """初始化数据库，子类可选实现此方法"""
        pass

    def delete(self, message: Message, timeout: int = 10):
        self._app.job_queue.run_once(
            _delete_message,
            data={"chat_id": message.chat_id, "message_id": message.message_id},
            when=timeout,
        )

    async def reply(
        self,
        source: Message,
        reply: str,
        reply_markup=None,
        parse_mode=None,
        delete_source=True,
        del_source_timeout: int = 10,
        delete_reply=True,
        del_reply_timeout: int = 10,
    ):
        reply_message = await source.reply_text(reply, reply_markup=reply_markup, parse_mode=parse_mode)
        if delete_source:
            self.delete(source, del_source_timeout)
        if delete_reply:
            self.delete(reply_message, del_reply_timeout)
        return reply_message

    @staticmethod
    def get_today():
        """获取今日日期"""
        return datetime.now(UTC).date()
