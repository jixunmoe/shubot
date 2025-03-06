import asyncio
import logging
from textwrap import dedent

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.ext.filters import ChatType

from shubot.config import Config
from shubot.database import DatabaseManager
from shubot.util import reply, defer_delete

logger = logging.getLogger(__name__)


class MyStatsCommand:
    """查询当前用户状态"""

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
            CommandHandler("my", self._handle_my, filters=ChatType.GROUPS)
        )

    async def _handle_my(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """响应 /my 命令，查询当前用户的状态"""
        user = update.effective_user
        message = update.message

        # await self._db.User.ensure_exists(user)

        try:
            [points, cult] = await asyncio.gather(
                self._db.User.get_points(user.id),
                self._db.User.get_cultivation_data(user.id),
            )
            logger.info(f"修仙数据查询结果：{cult}")
            stage_name = self._config.cultivation[cult.stage]

            sent_msg = await reply(
                message,
                dedent(
                    f"""\
                       📊 您的当前积分
                       ├ 用户ID：{user.id}
                       ├ 用户名：{user.full_name}
                       ├ 当前境界：{stage_name}
                       ├ 突破丹：{cult.pills} 枚
                       ├ 下次突破需：{cult.next_cost} 积分
                       └ 总积分(灵石)：{points} 分
                   """
                ),
            )
            defer_delete(context.job_queue, sent_msg, timeout=10)

        except Exception as e:
            logger.error(f"查询积分失败：{str(e)}")
            await message.reply_text("❌ 查询积分失败，请稍后再试")
