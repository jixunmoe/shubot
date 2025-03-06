import asyncio
import logging
from functools import lru_cache
from textwrap import dedent
from traceback import format_exception

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.ext.filters import ChatType
from telegram.helpers import escape_markdown

from shubot.config import Config
from shubot.database import DatabaseManager
from shubot.ext.command import BotCommandHandlerMixin
from shubot.util import reply, defer_delete

logger = logging.getLogger(__name__)

RANK_NUMBERS = "⒈⒉⒊⒋⒌⒍⒎⒏⒐⒑⒒⒓⒔⒕⒖⒗⒘⒙⒚⒛"


class UserInfoCommand(BotCommandHandlerMixin):
    """查询当前用户状态"""

    _app: Application
    _config: Config
    _db: DatabaseManager

    def __init__(self, app: Application, config: Config, db: DatabaseManager | None = None):
        self._db = db or DatabaseManager.get_instance()
        self._app = app
        self._config = config

        self._app.add_handler(CommandHandler("my", self._handle_my, filters=ChatType.GROUPS))
        self._app.add_handler(
            CommandHandler(["paihang", "leaderboard", "ranking"], self._handle_ranking, filters=ChatType.GROUPS)
        )

    async def _handle_my(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """响应 /my 命令，查询当前用户的状态"""
        user = update.effective_user
        message = update.message

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
            logger.error(f"查询积分失败：{str(e)} - {format_exception(e)}")
            await message.reply_text("❌ 查询积分失败，请稍后再试")

    async def _handle_ranking(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """响应 /paihang 命令，查询积分排行榜"""
        message = update.message
        msgs = self._config.leaderboard.messages
        group_id = message.chat.id
        top_users = await self._get_top_users_by_group(group_id)

        if not top_users:
            return await self.reply(message, rf"🌫️ 本群 \(`{group_id}`\) 尚无修仙者上榜", parse_mode="MarkdownV2")

        tg_names = await asyncio.gather(*(self._get_tg_name(uid) for (uid, _, _) in top_users))
        leaderboard_entries = []
        for rank, name, (_, stage, points) in zip(RANK_NUMBERS, tg_names, top_users):
            entry = msgs.entry.format(
                rank=rank,
                name=escape_markdown(name, version=2),
                stage=escape_markdown(self._config.cultivation[stage], version=2),
                points=points,
            )
            leaderboard_entries.append(entry.strip())
        msgs.separator.join(leaderboard_entries)
        leaderboard = f"{msgs.banner}\n\n{msgs.separator.join(leaderboard_entries)}\n\n{msgs.footer}"
        await self.reply(message, leaderboard, parse_mode="MarkdownV2", del_reply_timeout=60, del_source_timeout=0)

    @lru_cache
    async def _get_tg_name(self, uid: int, fallback: str = "侠名") -> str:
        try:
            user = await self.bot.get_chat(uid)
            return user.full_name
        except Exception as e:
            logger.error(f"获取用户信息 (uid={uid}) 失败：{str(e)}")
            return fallback

    async def _get_top_users_by_group(self, group_id: int):
        return await self._db.find_many(
            f"""
                SELECT
                    u.user_id, IFNULL(uc.stage, 0), IFNULL(u.points, 0) 
                FROM user_group ug
                    JOIN users u ON ug.user_id = u.user_id
                    LEFT JOIN user_cultivation uc ON u.user_id = uc.user_id
                WHERE
                    ug.group_id = %s
                ORDER BY
                    uc.stage DESC, u.points DESC
                LIMIT {int(self._config.leaderboard.top_count)}
            """,
            (group_id,),
        )
