import asyncio

from telegram import Update, User
from telegram.constants import ParseMode
from telegram.ext import Application, ContextTypes, MessageHandler
from telegram.ext.filters import StatusUpdate
from telegram.helpers import escape_markdown

from shubot.config import Config
from shubot.database import DatabaseManager
from shubot.ext.bot_helper import BotHelperMixin


class WelcomeNewMemberCommand(BotHelperMixin):
    def __init__(self, app: Application, config: Config, db: DatabaseManager | None = None):
        super().__init__(app, config, db)

        app.add_handler(MessageHandler(StatusUpdate.NEW_CHAT_MEMBERS, self._welcome_new_member))

    async def _welcome_new_member(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """新成员加入时的欢迎"""
        message = update.message
        if not message or not message.new_chat_members:
            # 没有新成员
            return

        await asyncio.gather(
            message.delete(),
            *(self._welcome_member(update, context, m) for m in message.new_chat_members if not m.is_bot)
        )

    async def _welcome_member(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user: User):
        msg = await self.bot.send_message(
            chat_id=update.message.chat.id,
            text=self._config.misc_messages.welcome_member.format(
                name=escape_markdown(user.full_name, version=2), id=user.id
            ),
            parse_mode=ParseMode.MARKDOWN_V2,
            disable_web_page_preview=True,
        )
        self.delete(msg, 20)
