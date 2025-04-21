from typing import cast

from telegram import Update, Message
from telegram.ext import ContextTypes

from shubot.ext.group_msg_handler import GroupMsgHandlerMixin


class RandomUserEventHandler(GroupMsgHandlerMixin):
    """在群组聊天时，随机产生机遇。"""

    async def handle_group_msg(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        message = cast(Message, update.message)

        # TODO: Check prerequisites and chances for random events
        pass
