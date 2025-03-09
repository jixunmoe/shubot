from typing import cast

from telegram import Update, Message
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from telegram.helpers import escape_markdown

from shubot.ext.group_msg_handler import GroupMsgHandlerMixin, GroupMessageHandleResult


class BookRepoInfoHandler(GroupMsgHandlerMixin):
    async def handle_group_msg(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        message = cast(Message, update.message)
        if message.text.strip() != "书库":
            return None

        # 显示书库信息
        book_repo = self._config.book.book_repo_template.format(
            **self._config.book.book_repo.__dict__, url_normalize=escape_markdown(self._config.book.book_repo.url, 2)
        )
        await self.reply(message, book_repo, parse_mode=ParseMode.MARKDOWN_V2, del_reply_timeout=20)

        return GroupMessageHandleResult.STOP
