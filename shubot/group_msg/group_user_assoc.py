from typing import cast

from async_lru import alru_cache
from telegram import Update, Message
from telegram.ext import ContextTypes

from shubot.ext.group_msg_handler import GroupMsgHandlerMixin


class GroupUserAssocRegisterHandler(GroupMsgHandlerMixin):
    async def handle_group_msg(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        message = cast(Message, update.message)
        user_id = message.from_user.id
        group_id = message.chat.id
        await self._assoc_user_to_group(user_id, group_id)

    @alru_cache
    async def _assoc_user_to_group(self, user_id: int, group_id: int):
        return await self._db.update(
            """
                    INSERT IGNORE INTO user_group (user_id, group_id)
                    VALUES (%s, %s)
            """,
            (user_id, group_id),
        )
