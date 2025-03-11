import asyncio
import re
from typing import cast

from telegram import Update, Message
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from telegram.helpers import escape_markdown

from shubot.ext.group_msg_handler import GroupMsgHandlerMixin


class PassiveChatBoostHandler(GroupMsgHandlerMixin):
    """在群组聊天时，静默地为用户增加积分/丹药数量。"""

    _re_hanzi = re.compile(r"[\u4e00-\u9fff]")

    async def handle_group_msg(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        message = cast(Message, update.message)

        if self._should_add_points(message.text or message.caption or ""):
            # 检测是否满足增加积分的条件
            await self._db.User.modify_points(message.from_user.id, 1)

            # 检测是否满足增加丹药数量的条件
            if self.chance_hit(self._config.passive_boost.pill_chance):
                name = escape_markdown(message.from_user.full_name, 2)
                msg = self._rnd.choice(self._config.passive_boost.pill_messages).format(name=name)
                await asyncio.gather(
                    self._db.User.modify_pills(message.from_user.id, 1),
                    self.reply(message, msg, parse_mode=ParseMode.MARKDOWN_V2, delete_source=False),
                )

    def _should_add_points(self, message: str) -> bool:
        actual_count = 0
        required_count = self._config.passive_boost.chinese_count
        if len(message) >= required_count:
            for _ in self._re_hanzi.finditer(message):
                actual_count += 1
                if actual_count >= required_count:
                    return True
        return False
