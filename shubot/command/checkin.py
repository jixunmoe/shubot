import random
from datetime import datetime, UTC
from textwrap import dedent

from telegram import Update
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

    def __init__(
        self, app: Application, config: Config, db: DatabaseManager | None = None
    ):
        self._db = db or DatabaseManager.get_instance()
        self._app = app
        self._config = config

        self._app.add_handler(
            CommandHandler("checkin", self._handle_checkin, filters=ChatType.GROUPS)
        )

    async def _handle_checkin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """每日签到"""
        user = update.effective_user
        message = update.message

        if message.chat.type not in ["group", "supergroup"]:
            return await message.reply_text("🌱 请在群组内签到哦~")

        earned = random.randint(1, 10)
        checkin_ok = await self._set_checkin(user.id, earned, datetime.now(UTC).date())
        if checkin_ok:
            reply_text = dedent(
                f"""
                {CHECKIN_STAR_PATTERN[:earned]}
                🎉 签到成功！
                📅 今日获得 {earned} 积分
                ⏳ 本条消息将在10秒后消失
            """
            )
        else:
            reply_text = dedent(
                """
                ⏳ 今日已签到
                🕒 下次签到时间：次日 00:00 (UTC)
            """
            )
        reply_msg = await reply(message, reply_text)
        defer_delete(context.job_queue, reply_msg, 10)

    async def _set_checkin(
        self, user_id: int, points: int, date: datetime.date
    ) -> bool:
        # Create user if not exists
        updated = await self._db.update(
            """
            INSERT IGNORE INTO users (user_id, points, last_checkin)
            VALUES (%s, %s, %s)
        """,
            (user_id, points, date),
        )

        if not updated:
            # User exists, update points
            updated = await self._db.update(
                """
                UPDATE users
                SET points = points + %s AND last_checkin = %s
                WHERE user_id = %s AND last_checkin != %s
            """,
                (points, date, user_id, date),
            )
        return updated > 0
