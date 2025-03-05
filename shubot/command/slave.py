from dataclasses import dataclass
from datetime import datetime, UTC
from textwrap import dedent
from typing import Optional, cast

from telegram import Update, Chat
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from telegram.ext.filters import ChatType
from telegram.helpers import escape_markdown

from shubot.config import SlaveRulesConfig
from shubot.database import DatabaseManager
from shubot.util import defer_delete, reply


@dataclass
class CelebrateJobData:
    chat: Chat
    text: str


async def _celebrate(ctx: ContextTypes.DEFAULT_TYPE):
    payload = cast(CelebrateJobData, ctx.job.data)
    await payload.chat.send_message(text=payload.text, parse_mode="MarkdownV2")


class SlaveCommand:
    _app: Application
    _config: SlaveRulesConfig
    _db: DatabaseManager

    def __init__(self, app: Application, config: SlaveRulesConfig, db: DatabaseManager | None = None):
        self._db = db or DatabaseManager.get_instance()
        self._app = app
        self._config = config

        self._app.add_handler(CommandHandler("nuli", self._handle_assign_slave, filters=ChatType.GROUPS))
        self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_confirm_slavery), group=1)
        self._app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, self._handle_enforce_slavery), group=2)

    async def _handle_assign_slave(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """帮主任命奴隶"""
        message = update.message
        master_user = message.from_user
        group_id = message.chat.id

        today = datetime.now(UTC).date()
        if await self._find_slave(master_user.id, today):
            return await reply(message, "🈲 今日已选定奴隶，请明日再来")

        if not message.reply_to_message or message.chat.type == "private":
            return await reply(message, "⚡ 请通过回复目标修士的消息使用此令")

        gang_leader = await self._find_gang_leader(group_id)
        if gang_leader["user_id"] != master_user.id:
            return await reply(message, "❌ 此乃帮主秘法，尔等岂可妄用！")

        slave_user = message.reply_to_message.from_user
        if slave_user.is_bot or slave_user.id == master_user.id:
            return await reply(message, "🌀 帮主大人，这是孝敬给您的奴隶，比较野")

        await self._insert_slave_relation(master_user.id, slave_user.id, group_id, today)

        # 契约
        text = dedent(f"""\
            🌌【主奴契约·天道认证】
            ✨ {self._escape(master_user.full_name)} 帮主手掐法诀，祭出奴隶印记！
            🔥 只见一道金光没入 {self._escape(slave_user.full_name)} 眉心
            🐾 霎时间， {self._escape(slave_user.full_name)} 眼神一下空洞起来
            🐾 其头顶竟冒出两个猫耳朵，屁股也…好像长出了一条尾巴正摇曳
            💢 帮主冷喝一声：『孽畜，还不速速立下跪下！』
            💢  {self._escape(slave_user.full_name)} 一哆嗦，马上跪下来！
            📜 请道友 {self._escape(slave_user.full_name)} 诵念：
            『{self._escape(self._config.init_phrase)}』（必须一字不差的打完）
        """)

        sent_msg = await reply(message, text, parse_mode="MarkdownV2")

        # 删除契约消息
        context.job_queue.run_once(
            lambda ctx: ctx.bot.delete_message(
                chat_id=sent_msg.chat_id,
                message_id=sent_msg.message_id
            ),
            30
        )

    async def _handle_confirm_slavery(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        message = update.message
        if message.text != self._config.init_phrase:
            return

        await self._update_confirm_slavery(message.from_user.id, datetime.utcnow().date(), True)

        text = dedent(f"""\
            🎇【心魔大誓·天道认证】
            ⚡ 九霄雷动，{self._escape(message.from_user.full_name)} 的魂灯已入帮主命牌！
            🐾 自此刻起至子时三刻，言行当以主人为本
            📜 违者将受万蚁噬心之苦！
        """)
        await message.reply_text(text, parse_mode="MarkdownV2")

        for i, text in enumerate([
            f"🌌 虚空震颤，恭贺 {escape_markdown(message.from_user.full_name, 2)} 成为帮主奴隶！",
            f"🎉 千妖俯首，万灵齐贺新奴入籍！",
            f"🍃 清风为凭，明月为证，此契天地共鉴！"
        ]):
            context.job_queue.run_once(_celebrate, data=CelebrateJobData(message.chat, text), when=i + 1)

    async def _handle_enforce_slavery(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        message = update.message
        user = message.from_user
        if message.chat.type == "private" or user.is_bot:
            return

        record = await self._find_slave_by_date(user.id, message.chat.id, datetime.utcnow().date())
        if not record:
            return

        master_id, confirmed = record
        if not confirmed and message.text != self._config.init_phrase:
            # 契约未确认，要求诵读咒语
            if message.text != self._config.init_phrase:
                warning_text = f"⚡ @{user.username or user.id} 灵台混沌未立誓！速诵『{self._config.init_phrase}』"
                warning = await reply(message, warning_text, parse_mode="MarkdownV2")
                defer_delete(context.job_queue, warning, 10)
            return

        if confirmed and self._config.daily_phrase not in message.text:
            # 当日契约已成立，检查是否带有要求的内容
            reminder_text = f"🐾 @{user.username or user.id} 忘了带尾音哦～要加『{self._config.daily_phrase}』哦～"
            reminder = await reply(message, reminder_text, parse_mode="MarkdownV2")
            defer_delete(context.job_queue, reminder, 10)

    @staticmethod
    def _escape(text: str):
        return escape_markdown(escape_markdown(text, version=2), version=2)

    async def _find_slave(self, uid: int, date: datetime.date):
        found = await self._db.find_one("""
            SELECT 1 FROM slave_records 
            WHERE master_id = %s AND created_date = %s
        """, (uid, date))
        return bool(found)

    async def _find_gang_leader(self, group_id: int) -> Optional[dict]:
        return await self._db.find_one("""
            SELECT u.user_id, uc.stage, u.points 
            FROM user_group ug
            JOIN users u ON ug.user_id = u.user_id
            JOIN user_cultivation uc ON u.user_id = uc.user_id
            WHERE ug.group_id = %s
            ORDER BY uc.stage DESC, u.points DESC
            LIMIT 1
        """, (group_id,))

    async def _insert_slave_relation(self, master_id: int, slave_id: int, group_id: int, date: datetime.date):
        return await self._db.update("""
            INSERT INTO slave_records 
            (master_id, slave_id, group_id, created_date)
            VALUES (%s, %s, %s, %s)
        """, (master_id, slave_id, group_id, date))

    async def _update_confirm_slavery(self, slave_id: int, date: datetime.date, confirm: bool):
        await self._db.update("""
            UPDATE slave_records SET confirmed = TRUE 
            WHERE slave_id = %s AND created_date = %s
        """, (int(confirm), slave_id, date))

    async def _find_slave_by_date(self, slave_id: int, group_id: int, date: datetime.date):
        return await self._db.find_one("""
            SELECT master_id, confirmed 
            FROM slave_records 
            WHERE slave_id = %s AND group_id = %s and created_date = %s
            ORDER BY created_date DESC 
            LIMIT 1
        """, (slave_id, group_id, date))
