from textwrap import dedent

from telegram import Update, User
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.ext.filters import ChatType

from shubot.config import Config
from shubot.database import DatabaseManager
from shubot.ext.command import BotCommandHandlerMixin
from shubot.util import reply, defer_delete

CHECKIN_STAR_PATTERN = "⭐" * 5 + "✨" * 5


class CheckinCommand(BotCommandHandlerMixin):
    _app: Application
    _config: Config
    _db: DatabaseManager

    def __init__(self, app: Application, config: Config, db: DatabaseManager | None = None):
        self._db = db or DatabaseManager.get_instance()
        self._app = app
        self._config = config

        self._app.add_handler(CommandHandler("checkin", self._handle_checkin, filters=ChatType.GROUPS))

    async def _handle_checkin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """每日签到"""
        user = update.effective_user
        message = update.message

        if message.chat.type not in ["group", "supergroup"]:
            return await message.reply_text("🌱 请在群组内签到哦~")

        earned = self._rnd.randint(1, 10)
        checkin_ok = await self._set_checkin(user, earned)
        if checkin_ok:
            reply_text = dedent(
                f"""\
                    {CHECKIN_STAR_PATTERN[:earned]}
                    🎉 签到成功！
                    📅 今日获得 {earned} 积分
                    ⏳ 本条消息将在10秒后消失
                """
            )
        else:
            reply_text = dedent(
                """\
                    ⏳ 今日已签到
                    🕒 下次签到时间：次日 00:00 (UTC)
                """
            )
        reply_msg = await reply(message, reply_text)
        defer_delete(context.job_queue, reply_msg, 10)

    async def _set_checkin(self, user: User, points: int) -> bool:
        await self._db.User.ensure_exists(user)

        updated = await self._db.update(
            """
                UPDATE users
                SET points       = points + %s,
                    last_checkin = UTC_DATE()
                WHERE user_id = %s
                  AND (last_checkin IS NULL OR last_checkin != UTC_DATE());
            """,
            (points, user.id),
        )
        return updated > 0
