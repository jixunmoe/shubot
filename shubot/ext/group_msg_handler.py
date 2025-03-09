import enum
from abc import ABC, abstractmethod

from telegram import Update
from telegram.ext import ContextTypes

from shubot.ext.bot_helper import BotHelperMixin


class GroupMessageHandleResult(enum.IntEnum):
    CONTINUE = 0
    STOP = 1


class GroupMsgHandlerMixin(BotHelperMixin, ABC):
    async def init_db(self):
        """初始化数据库，子类可选实现此方法"""
        pass

    @abstractmethod
    async def handle_group_msg(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> GroupMessageHandleResult | None:
        """处理群组消息"""
        pass
