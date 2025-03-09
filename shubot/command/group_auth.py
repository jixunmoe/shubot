from functools import partial

from telegram import Update, User
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.ext.filters import ChatType
from telegram.helpers import escape_markdown

from shubot.config import Config
from shubot.database import DatabaseManager
from shubot.ext.bot_helper import BotHelperMixin

CHECKIN_STAR_PATTERN = "⭐" * 5 + "✨" * 5


class GroupAuthCommand(BotHelperMixin):
    """群组授权指令，仅限管理员使用"""

    def __init__(self, app: Application, config: Config, db: DatabaseManager | None = None):
        super().__init__(app, config, db)

        self._app.add_handler(
            CommandHandler("addgroup", partial(self._handle_group_auth, auth=True), filters=ChatType.GROUPS)
        )
        self._app.add_handler(
            CommandHandler("removegroup", partial(self._handle_group_auth, auth=False), filters=ChatType.GROUPS)
        )

    async def _handle_group_auth(self, update: Update, context: ContextTypes.DEFAULT_TYPE, auth: bool):
        """处理群组授权指令"""
        user = update.effective_user
        message = update.message

        if not self.is_admin(user):
            return await self.reply(message, "⚠️ 你没有权限执行此操作")

        if not context.args or len(context.args) != 1:
            return await self.reply(
                message,
                reply=(
                    "用法：`/addgroup <群组ID>`（或 `/removegroup <群组ID>`。\n"
                    f"当前群组 ID `{escape_markdown(str(message.chat_id), version=2)}`"
                ),
                parse_mode="MarkdownV2",
            )

        group_id = int(context.args[0])
        group = await self.bot.get_chat(group_id)
        if not group:
            return await self.reply(message, f"⚠️ 未找到群组 `{escape_markdown(str(group_id))}`")

        group_name = group.title or f"无名群组 #{group_id}"
        changed = await self._db.GroupAuth.set_group_auth(group_id, group_name, auth)
        if not changed:
            return await self.reply(message, "⚠️ 数据库影响行数为 0。请检查群组 ID 是否正确。")

        result = "已添加授权" if auth else "已移除授权"
        msg = (
            rf"✅ 群组 `{escape_markdown(group_name, version=2)}` \(`{escape_markdown(str(group_id), version=2)}`\)"
            f" {result}"
        )
        await self.reply(message, msg, parse_mode="MarkdownV2")
