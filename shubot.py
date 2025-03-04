import logging
import os
import random
import hashlib
import asyncio
import re
from datetime import time
from pathlib import Path
from typing import Optional
from typing import Tuple
from datetime import datetime, timezone, timedelta
import aiomysql
from telegram import Update, Message, File, BotCommand, BotCommandScopeAllPrivateChats
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.helpers import escape_markdown
from telegram.ext import (
    Application,
    MessageHandler,
    filters,
    CommandHandler,
    ContextTypes,
    JobQueue,
    CallbackQueryHandler
)

now = datetime.now(timezone(timedelta(hours=8))).date()
BOT_USERNAME = "shuqunBot"

#配置项
CONFIG = {
    "token": "",
    "admin_ids": [],
    "download_path": "/root/shuku",
    "book_repo": {
        "url": "https://shuku.sf.uk",
        "username": "hesu",
        "password": "aa1233",
        "notice": "请不要上传无关内容,不要批量/打包下载"
    },
    "db": {
        "host": "localhost",
        "user": "root",
        "password": "",
        "db": "novel_bot_db",
        "port": 3306
    },
    "allowed_extensions": {".txt", ".epub"},
    "points_per_book": 10
}

SLAVE_RULES = {
    "init_phrase": "见过主人，喵~",
    "daily_phrase": "喵",
    "max_retry": 3
}

ROB_CONFIG = {
    "daily_limit": 5,
    "escape_prob": 0.2,
    "dice_range": (1, 6),
    "stage_bonus": 3,
    "penalty_ratio": (0.1, 0.3),
    "cooldown": 60
}

CONFIG["gang"] = {
    "base_donation": 100,
    "reset_hour": 21,
    "reset_minute": 33
}

RANDOM_EVENTS = [
    {
        "name": "灵石丢失",
        "probability": 0.005,
        "condition": lambda u: u['points'] > 50,
        "action": "handle_lost_points"
    },
    {
        "name": "小境界突破",
        "probability": 0.002,
        "condition": lambda u: u['stage'] % 3 != 2,
        "action": "handle_stage_up"
    },
    {
        "name": "境界跌落",
        "probability": 0.003,
        "condition": lambda u: u['stage'] > 3,
        "action": "handle_stage_down"
    },
    {
        "name": "上古遗迹",
        "probability": 0.002,
        "action": "handle_discovery"
    }
]

CULTIVATION_STAGES = [
    "凡夫俗子",
    "后天前期", "后天中期", "后天后期",
    "先天前期", "先天中期", "先天后期",
    "练气前期", "练气中期", "练气后期",
    "筑基前期", "筑基中期", "筑基后期",
    "金丹前期", "金丹中期", "金丹后期",
    "元婴前期", "元婴中期", "元婴后期",
    "化神前期", "化神中期", "化神后期",
    "炼虚前期", "炼虚中期", "炼虚后期",
    "合体前期", "合体中期", "合体后期",
    "大乘前期", "大乘中期", "大乘后期",
    "渡劫前期", "渡劫中期", "渡劫后期" 
]

BREAKTHROUGH_PROBABILITY = {
    3: 1.0,
    6: 0.9,
    9: 0.8,
    12: 0.7,
    15: 0.6,
    18: 0.5,
    21: 0.4,
    24: 0.3,
    27: 0.2,
    30: 0.1
}
REGION_NAMES = {
    "hk": "香港",
    "jp": "日本",
    "sg": "新加坡",
    "us": "美国"
}
GUA_CONFIG = {
    "options": {
        3: 30,
        10: 100,
        50: 500
    },
    "daily_limit": 5,
    "number_range": (1, 20),
    "select_count": 5,
    "win_probability": 0.1
}

HANZI_PATTERN = re.compile(r'[\u4e00-\u9fa5]')

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)
Path(CONFIG["download_path"]).mkdir(parents=True, exist_ok=True)

class DatabaseManager:
    def __init__(self):
        self.pool = None

    async def get_pool(self):
        if not self.pool:
            self.pool = await aiomysql.create_pool(
                host=CONFIG['db']['host'],
                port=CONFIG['db']['port'],
                user=CONFIG['db']['user'],
                password=CONFIG['db']['password'],
                db=CONFIG['db']['db'],
                autocommit=False
            )
        return self.pool

    async def is_group_authorized(self, group_id: int) -> bool:
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    "SELECT 1 FROM authorized_groups WHERE group_id = %s",
                    (group_id,)
                )
                return bool(await cursor.fetchone())

    async def add_authorized_group(self, group_id: int, group_name: str):
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """INSERT INTO authorized_groups (group_id, group_name)
                        VALUES (%s, %s)
                        ON DUPLICATE KEY UPDATE group_name = VALUES(group_name)""",
                    (group_id, group_name)
                )
            await conn.commit()

    async def get_user_state(self, user_id: int) -> dict:
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """INSERT IGNORE INTO users (user_id, points) 
                       VALUES (%s, 0)""",
                    (user_id,)
                )
                await cursor.execute(
                    """INSERT IGNORE INTO user_cultivation (user_id) 
                       VALUES (%s)""",
                    (user_id,)
                )
                
                await cursor.execute(
                    "SELECT points FROM users WHERE user_id = %s",
                    (user_id,)
                )
                points_row = await cursor.fetchone()
                
                
                await cursor.execute(
                    "SELECT stage, pills, next_cost FROM user_cultivation WHERE user_id = %s",
                    (user_id,)
                )
                cult_row = await cursor.fetchone()
                
                await conn.commit()
                
                return {
                    "points": points_row[0] if points_row else 0,
                    "stage": cult_row[0] if cult_row else 0,
                    "pills": cult_row[1] if cult_row else 0,
                    "next_cost": cult_row[2] if cult_row else 10
                }

    async def remove_authorized_group(self, group_id: int):
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    "DELETE FROM authorized_groups WHERE group_id = %s",
                    (group_id,)
                )
            await conn.commit()

    async def get_all_groups(self):
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("SELECT group_id FROM authorized_groups")
                return [row[0] for row in await cursor.fetchall()]

    async def record_gua_usage(self, user_id: int) -> bool:
        pool = await self.get_pool()
        today = datetime.utcnow().date()
        async with pool.acquire() as conn:
            try:
                async with conn.cursor() as cursor:
                    await cursor.execute("""
                        SELECT times_used FROM gua_records
                        WHERE user_id = %s AND date = %s
                        FOR UPDATE
                    """, (user_id, today))
                    result = await cursor.fetchone()
                    
                    current = result[0] if result else 0
                    if current >= GUA_CONFIG["daily_limit"]:
                        return False
                    
                    await cursor.execute("""
                        INSERT INTO gua_records (user_id, date, times_used)
                        VALUES (%s, %s, 1)
                        ON DUPLICATE KEY UPDATE
                        times_used = times_used + 1
                    """, (user_id, today))
                    
                    await conn.commit()
                    return True
                    
            except Exception as e:
                await conn.rollback()
                logger.error(f"记录刮刮乐使用失败：{str(e)}")
                return False

    async def daily_checkin(self, user_id: int, username: str) -> Tuple[int, bool]:
        #签到
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("SELECT UTC_TIMESTAMP()")
                current_utc = (await cursor.fetchone())[0]
                current_date = current_utc.date()
                await cursor.execute(
                    """SELECT CONVERT_TZ(last_checkin, 
                        @@session.time_zone, '+00:00') 
                       FROM users WHERE user_id = %s""",
                    (user_id,)
                )
                result = await cursor.fetchone()
    
                #判断是否已签到
                if result and result[0]:
                    last_checkin_utc = result[0].replace(tzinfo=timezone.utc)
                    if last_checkin_utc.date() == current_date:
                        return 0, False
    
                #生成随机积分
                points = random.randint(1, 10)
                
                await cursor.execute(
                    """INSERT INTO users 
                        (user_id, username, points, last_checkin)
                       VALUES (%s, %s, %s, UTC_TIMESTAMP())
                       ON DUPLICATE KEY UPDATE
                       points = points + VALUES(points),
                       username = VALUES(username),
                       last_checkin = UTC_TIMESTAMP()""",
                    (user_id, username, points)
                )
                await conn.commit()
                return points, True


    async def deduct_points(self, user_id: int, amount: int) -> bool:
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    "SELECT points FROM users WHERE user_id = %s FOR UPDATE",
                    (user_id,)
                )
                result = await cursor.fetchone()
                
                if not result or result[0] < amount:
                    return False
                
                await cursor.execute(
                    "UPDATE users SET points = points - %s WHERE user_id = %s",
                    (amount, user_id)
                )
                await conn.commit()
                return True

    async def get_cultivation_data(self, user_id: int) -> dict:
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """INSERT INTO user_cultivation (user_id, stage, pills, next_cost)
                       VALUES (%s, 0, 0, 10)
                       ON DUPLICATE KEY UPDATE
                       user_id = VALUES(user_id)""",
                    (user_id,)
                )
                await cursor.execute(
                    "SELECT stage, pills, next_cost FROM user_cultivation WHERE user_id = %s",
                    (user_id,)
                )
                result = await cursor.fetchone()
                await conn.commit()
                return dict(zip(['stage','pills','next_cost'], result)) if result else None

    async def update_cultivation_stage(self, user_id: int, new_stage: int, new_cost: int):
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """UPDATE user_cultivation 
                       SET stage = %s, next_cost = %s 
                       WHERE user_id = %s""",
                    (new_stage, new_cost, user_id)
                )
                await conn.commit()

    async def add_breakthrough_pill(self, user_id: int, amount: int = 1):
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """UPDATE user_cultivation 
                       SET pills = pills + %s 
                       WHERE user_id = %s""",
                    (amount, user_id)
                )
                await conn.commit()
    async def get_user_points(self, user_id: int) -> int:
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    "SELECT points FROM users WHERE user_id = %s",
                    (user_id,)
                )
                result = await cursor.fetchone()
                return result[0] if result else 0

    async def modify_points(self, user_id: int, delta: int) -> int:
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """INSERT INTO users (user_id, points)
                       VALUES (%s, %s)
                       ON DUPLICATE KEY UPDATE
                       username = VALUES(username)""",
                    (user_id, max(delta, 0))
                )
                
                await cursor.execute(
                    "UPDATE users SET points = GREATEST(points + %s, 0) WHERE user_id = %s",
                    (delta, user_id)
                )
                
                await cursor.execute(
                    "SELECT points FROM users WHERE user_id = %s",
                    (user_id,)
                )
                result = await cursor.fetchone()
                await conn.commit()
                return result[0] if result else 0

    async def check_md5_exists(self, md5: str) -> bool:
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("SELECT 1 FROM files WHERE md5 = %s", (md5,))
                return bool(await cursor.fetchone())

    async def update_user_points(self, user_id: int, username: str):
        #更新积分
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """INSERT INTO users (user_id, username, points)
                       VALUES (%s, %s, %s)
                       ON DUPLICATE KEY UPDATE
                       points = points + VALUES(points),
                       username = VALUES(username)""",
                    (user_id, username, CONFIG["points_per_book"])
                )
            await conn.commit()

    async def record_new_file(self, user_id: int, md5: str):
        #记录新文件
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    "INSERT INTO files (md5, user_id) VALUES (%s, %s)",
                    (md5, user_id)
                )
            await conn.commit()

    async def record_rob(self, user_id: int) -> bool:
        #记录打劫次数
        pool = await self.get_pool()
        now = datetime.utcnow()
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("""
                    CREATE TABLE IF NOT EXISTS rob_records (
                        user_id BIGINT PRIMARY KEY,
                        last_rob TIMESTAMP,
                        count INT DEFAULT 0,
                        FOREIGN KEY (user_id) REFERENCES users(user_id)
                    )
                """)
                
                await cursor.execute(
                    "SELECT last_rob FROM rob_records WHERE user_id = %s",
                    (user_id,)
                )
                result = await cursor.fetchone()
                if result and (now - result[0]).seconds < ROB_CONFIG["cooldown"]:
                    return False
                
                await cursor.execute("""
                    INSERT INTO rob_records (user_id, last_rob, count)
                    VALUES (%s, %s, 1)
                    ON DUPLICATE KEY UPDATE
                    last_rob = VALUES(last_rob),
                    count = IF(DATE(last_rob) != CURDATE(), 1, count + 1)
                """, (user_id, now))
                
                await conn.commit()
                return True

    async def get_rob_count(self, user_id: int) -> int:
        #获取当日打劫次数
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    "SELECT count FROM rob_records WHERE user_id = %s",
                    (user_id,)
                )
                result = await cursor.fetchone()
                return result[0] if result else 0

    async def silent_add_points(self, user_id: int, username: str):
        #水群分
        try:
            pool = await self.get_pool()
            async with pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(
                        """INSERT INTO users (user_id, username, points)
                           VALUES (%s, %s, 1)
                           ON DUPLICATE KEY UPDATE
                           points = points + 1,
                           username = VALUES(username)""",
                        (user_id, username)
                    )
                    await conn.commit()
                    return True
        except Exception as e:
            logger.error(f"数据库操作失败：{str(e)}")
            return False

db_manager = DatabaseManager()

async def calculate_md5(file_path: Path) -> str:
    #计算md5
    hash_md5 = hashlib.md5()
    with file_path.open("rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

async def admin_add_group(update: Update, context):
    #群组授权
    user = update.effective_user
    if user.id not in CONFIG["admin_ids"]:
        await update.message.reply_text("⚠️ 你没有权限执行此操作")
        return

    if not update.message.chat.type == "private":
        await update.message.reply_text("⚠️ 请在群聊中使用该命令")
        return

    command = update.message.text.strip().split()
    if len(command) < 2:
        await update.message.reply_text("用法：/addgroup <群组ID>")
        return

    group_id = int(command[1])
    group = await context.bot.get_chat(group_id)
    await db_manager.add_authorized_group(group_id, group.title)
    await update.message.reply_text(f"✅ 已授权群组：{group.title}（ID: {group_id}）")

async def group_exchange(update: Update, context: ContextTypes.DEFAULT_TYPE):
    #兑换(群组里)
    message = update.message
    user = message.from_user
    
    try:
        points = await db_manager.get_user_points(user.id)
        
        if points < 300:
            reply = await message.reply_text(
                "📉 积分不足！\n"
                "💡 分享优质小说可获得积分\n"
                "⚡ 当前积分：{}/300".format(points)
            )
            
            context.job_queue.run_once(
                callback=lambda ctx: ctx.bot.delete_message(
                    chat_id=message.chat_id,
                    message_id=reply.message_id
                ),
                when=10
            )
        else:
            reply = await message.reply_text(
                "🔑 兑换功能已解锁！\n"
                "💬 请与机器人私聊完成兑换操作",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("前往私聊", url=f"t.me/{BOT_USERNAME}")]
                ])
            )
            context.job_queue.run_once(
                callback=lambda ctx: ctx.bot.delete_message(
                    chat_id=message.chat_id,
                    message_id=reply.message_id
                ),
                when=10
            )
            
    except Exception as e:
        logger.error(f"群组兑换处理失败: {str(e)}")

async def handle_lost_points(user_id, cult_data):
    lost = random.randint(10, min(200, cult_data['points']//2))
    new_points = await db_manager.modify_points(user_id, -lost)
    return {
        "msg": random.choice([
            f"💸 遭遇虚空裂缝！丢失{lost}灵石（剩余：{new_points}）",
            f"🦊 被幻化妖狐所骗，损失{lost}灵石",
            f"🌪️ 储物袋破洞！掉出{lost}灵石"
        ]),
        "duration": 10
    }

async def handle_stage_up(user_id, cult_data):
    new_stage = cult_data['stage'] + 1
    await db_manager.update_cultivation_stage(user_id, new_stage, cult_data['next_cost'])
    return {
        "msg": f"🌟 顿悟天道法则！直接突破至《{CULTIVATION_STAGES[new_stage]}》",
        "duration": 15
    }

async def handle_stage_down(user_id, cult_data):
    lost_stage = random.randint(1, min(3, cult_data['stage']-3))
    new_stage = cult_data['stage'] - lost_stage
    await db_manager.update_cultivation_stage(user_id, new_stage, max(10, cult_data['next_cost']//2))
    return {
        "msg": random.choice([
            f"💥 心魔反噬！境界跌落{lost_stage}重天至《{CULTIVATION_STAGES[new_stage]}》",
            f"☠️ 误练邪功，倒退{lost_stage}个小境界",
            f"🌑 道基受损！修为跌落至《{CULTIVATION_STAGES[new_stage]}》"
        ]),
        "duration": 15
    }

async def handle_discovery(user_id, cult_data):
    gain = random.randint(50, 200)
    pills = random.randint(1, 2)
    await db_manager.modify_points(user_id, gain)

    await db_manager.add_breakthrough_pill(user_id, pills)
    return {
        "msg": random.choice([
            f"🏛️ 发现上古洞府！获得{gain}灵石和{pills}枚破境丹",
            f"🗺️ 破解秘境禁制，寻得天材地宝（+{gain}灵石，+{pills}丹）",
            f"🔱 获得古修士传承！修为大涨（灵石+{gain}，丹药+{pills}）"
        ]),
        "duration": 15
    }


async def gua_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    #刮刮乐
    user = update.effective_user
    message = update.message
    
    keyboard = [
        [InlineKeyboardButton(f"{cost}积分（奖{reward}）", callback_data=f"gua_{cost}")]
        for cost, reward in GUA_CONFIG["options"].items()
    ]
    markup = InlineKeyboardMarkup(keyboard)
    
    sent_msg = await message.reply_text(
        "🎰 刮刮乐游戏\n"
        f"每日次数：{GUA_CONFIG['daily_limit']}次\n"
        "请选择面值：",
        reply_markup=markup
    )
    
    context.job_queue.run_once(
        callback=auto_delete_messages,
        when=30,
        data={
            "chat_id": message.chat_id,
            "user_msg_id": message.message_id,
            "bot_msg_id": sent_msg.message_id
        },
        name=f"delete_gua_{message.message_id}"
    )

async def private_exchange(update: Update, context: ContextTypes.DEFAULT_TYPE):
    #兑换节点
    user = update.effective_user
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🇭🇰 香港节点", callback_data="hk"),
            InlineKeyboardButton("🇯🇵 日本节点", callback_data="jp")
        ],
        [
            InlineKeyboardButton("🇸🇬 新加坡节点", callback_data="sg"),
            InlineKeyboardButton("🇺🇸 美国节点", callback_data="us")
        ]
    ])
    
    await update.message.reply_text(
        "🎉 欢迎使用兑换系统\n"
        "📚 感谢您持续分享优质小说\n"
        "🔐 请选择节点类型：",
        reply_markup=keyboard
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    #兑换回调
    query = update.callback_query
    await query.answer()

    if query.data.startswith("gua_"):
        await handle_gua_callback(update, context)
        return 

    user = query.from_user
    node_type = query.data
    
    try:
        #扣除积分
        required_points = 300
        success = await db_manager.deduct_points(user.id, required_points)
        if not success:
            await query.edit_message_text("❌ 积分不足，兑换失败")
            return
        
        file_path = Path(__file__).parent / f"{node_type}.txt"
        if not file_path.exists():
            await query.edit_message_text("⚠️ 节点列表暂未更新，请联系管理员")
            return
            
        with open(file_path, "r") as f:
            nodes = [line.strip() for line in f if line.strip()]
        
   
        if not nodes:
            await query.edit_message_text("⚠️ 节点暂无，请联系管理员")
            return
            
        selected = random.choice(nodes)
        
        await context.bot.send_message(
            chat_id=user.id,
            text=f"🔗 您的{REGION_NAMES[node_type]}节点：\n\n`{selected}`\n\n⏳ 有效期：用到死",
            parse_mode="MarkdownV2"
        )
        await query.edit_message_text("✅ 兑换成功！请查收私信")
        
    except Exception as e:
        logger.error(f"兑换失败: {str(e)}")
        await query.edit_message_text("‼️ 兑换失败，请联系管理员")

async def select_gang_leader(group_id: int) -> Optional[dict]:
    #选出帮主
    pool = await db_manager.get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("""
                SELECT u.user_id, uc.stage, u.points 
                FROM user_group ug
                JOIN users u ON ug.user_id = u.user_id
                JOIN user_cultivation uc ON u.user_id = uc.user_id
                WHERE ug.group_id = %s
                ORDER BY uc.stage DESC, u.points DESC
                LIMIT 1
            """, (group_id,))
            leader = await cursor.fetchone()
            return leader

async def update_gang_leader(context: ContextTypes.DEFAULT_TYPE):
    #选出帮主
    logger.info("开始执行帮主更新任务")
    
    try:
        groups = await db_manager.get_all_groups()
        if not groups:
            logger.warning("当前没有已授权的群组")
            return

        for group_id in groups:
            try:
                try:
                    chat = await context.bot.get_chat(group_id)
                    if chat.type not in ["group", "supergroup"]:
                        logger.debug(f"跳过非群组类型：{group_id}")
                        continue
                    
                    bot_member = await context.bot.get_chat_member(group_id, context.bot.id)
                    if bot_member.status not in ["administrator", "creator"]:
                        logger.warning(f"机器人在群组 {group_id} 无管理员权限")
                        continue
                except TelegramError as e:
                    logger.error(f"群组 {group_id} 状态检查失败: {str(e)}")
                    continue

                async with (await db_manager.get_pool()).acquire() as conn:
                    async with conn.cursor(aiomysql.DictCursor) as cursor:
                        await cursor.execute("""
                            SELECT u.user_id, uc.stage, u.points
                            FROM user_group ug
                            JOIN users u ON ug.user_id = u.user_id
                            JOIN user_cultivation uc ON u.user_id = uc.user_id
                            WHERE ug.group_id = %s
                            ORDER BY uc.stage DESC, u.points DESC
                            LIMIT 1
                        """, (group_id,))
                        leader_data = await cursor.fetchone()

                if not leader_data:
                    logger.info(f"群组 {group_id} 无有效修士")
                    continue

                current_leader_id = leader_data["user_id"]
                current_stage = leader_data["stage"]
                current_points = leader_data["points"]

                today = datetime.utcnow().date()
                async with (await db_manager.get_pool()).acquire() as conn:
                    async with conn.cursor() as cursor:
                        # 检查是否连任
                        await cursor.execute("""
                            SELECT consecutive_days 
                            FROM gang_records 
                            WHERE user_id = %s 
                            ORDER BY start_date DESC 
                            LIMIT 1
                        """, (current_leader_id,))
                        record = await cursor.fetchone()
                        
                        days = 1
                        if record:
                            #连任
                            await cursor.execute("""
                                SELECT 1 FROM gang_records
                                WHERE user_id = %s 
                                AND start_date = %s
                            """, (current_leader_id, today - timedelta(days=1)))
                            if await cursor.fetchone():
                                days = record[0] + 1

                        await cursor.execute("""
                            INSERT INTO gang_records 
                            (user_id, start_date, consecutive_days, total_donated)
                            VALUES (%s, %s, %s, %s)
                            ON DUPLICATE KEY UPDATE
                            consecutive_days = VALUES(consecutive_days),
                            total_donated = total_donated + VALUES(total_donated)
                        """, (
                            current_leader_id, 
                            today,
                            days,
                            days * CONFIG["gang"]["base_donation"]
                        ))
                        await conn.commit()

                try:
                    user = await context.bot.get_chat(current_leader_id)
                    honorific = random.choice([
                        "天选之子", "不世出的绝世高手", 
                        "万古无一的天骄", "镇压时代的至强者"
                    ])
                    
                    donation = days * CONFIG["gang"]["base_donation"]
                    
                    safe_stage = escape_markdown(
                        CULTIVATION_STAGES[current_stage], 
                        version=2
                    )
                    
                    msg_text = (
                        f"🎇【天道敕令·帮主更迭】\n"
                        f"✨ {honorific} {escape_markdown(user.full_name,2)} \n"
                        f"🏯 以《{safe_stage}》无上修为，执掌合书帮！\n"
                        f"💰 享全群供奉 {donation}灵石（连任天数：{days}日）\n"
                        f"⚡ 诸弟子当以帮主马首是瞻！"
                    )
                    
                    await context.bot.send_message(
                        chat_id=group_id,
                        text=msg_text,
                        parse_mode="MarkdownV2",
                        disable_notification=True
                    )
                    logger.info(f"群组 {group_id} 帮主更新成功")
                    
                except Exception as e:
                    logger.error(f"群组 {group_id} 消息发送失败: {str(e)}")

            except Exception as e:
                logger.error(f"处理群组 {group_id} 时发生未知错误: {str(e)}")
                continue
                
    except Exception as e:
        logger.critical(f"帮主更新任务整体失败: {str(e)}")
    finally:
        logger.info("帮主更新任务执行结束")

def set_gang_schedule(app: Application):
    #定时群主任务
    tz = timezone(timedelta(hours=8))
    app.job_queue.run_daily(
        callback=update_gang_leader,
        time=time(
            hour=CONFIG["gang"]["reset_hour"],
            minute=CONFIG["gang"]["reset_minute"],
            tzinfo=tz
        ),
        name="gang_leader_update"
    )

async def paihang_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    #修仙排行榜
    group_id = update.message.chat.id
    pool = await db_manager.get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("""
                SELECT u.user_id, uc.stage, u.points 
                FROM user_group ug
                JOIN users u ON ug.user_id = u.user_id
                JOIN user_cultivation uc ON u.user_id = uc.user_id
                WHERE ug.group_id = %s
                ORDER BY uc.stage DESC, u.points DESC
                LIMIT 10
            """, (group_id,))
            top10 = await cursor.fetchall()

    if not top10:
        await update.message.reply_text("🌫️ 本群尚无修仙者上榜")
        return

    text = "🏯【合书帮·天骄榜】🏯\n"
    for idx, (user_id, stage, points) in enumerate(top10, 1):
        user = await context.bot.get_chat(user_id)
        
        safe_name = escape_markdown(escape_markdown(user.full_name, version=2), version=2)
        safe_stage = escape_markdown(CULTIVATION_STAGES[stage], version=2)
        text += (
            f"{idx}\\. {safe_name}\n"
            f"   境界：《{safe_stage}》\n"
            f"   灵石：{points}枚\n"
            "▰▰▰▰▰▰▰▰▰\n"
        )

    msg = await update.message.reply_text(
        text + "\n⚡ 此榜单一分钟后消散", 
        parse_mode="MarkdownV2",
        disable_web_page_preview=True
    )
    
    context.job_queue.run_once(
        lambda ctx: ctx.bot.delete_message(chat_id=msg.chat_id, message_id=msg.message_id),
        60
    )

def safe_markdown(text: str) -> str:
    return escape_markdown(
        escape_markdown(text, version=2), 
        version=2
    ).replace(".", "\\.")

async def auto_delete_messages(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    try:
        
        chat_id = int(job.data["chat_id"])
        user_msg_id = int(job.data["user_msg_id"])
        bot_msg_id = int(job.data["bot_msg_id"])
        
        logger.info(f"正在删除消息：群组ID={chat_id} 用户消息ID={user_msg_id} 机器人消息ID={bot_msg_id}")
        
        
        await context.bot.delete_message(
            chat_id=chat_id,
            message_id=user_msg_id
        )

        await context.bot.delete_message(
            chat_id=chat_id,
            message_id=bot_msg_id
        )
        
    except Exception as e:
        logger.error(f"消息删除失败：{str(e)}", exc_info=True)


async def handle_gua_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    #刮刮乐回调
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    cost = int(query.data.split("_")[1])
    reward = GUA_CONFIG["options"][cost]
    
    try:
        #检查次数
        remaining = await check_gua_remaining(user.id)
        if remaining <= 0:
            await query.edit_message_text("❌ 今日次数已用尽，请明天再来")
            return
            
        if not await db_manager.deduct_points(user.id, cost):
            await query.edit_message_text(f"❌ 积分不足，需要{cost}积分")
            return
            
        success = await db_manager.record_gua_usage(user.id)
        if not success:
            await db_manager.modify_points(user.id, cost)
            await query.edit_message_text("❌ 操作失败，请重试")
            return
            
        user_nums = random.sample(
            range(GUA_CONFIG["number_range"][0], GUA_CONFIG["number_range"][1]+1),
            GUA_CONFIG["select_count"]
        )
        
        #暗调
        is_win = random.random() < GUA_CONFIG["win_probability"]
        
        all_numbers = set(range(GUA_CONFIG["number_range"][0], GUA_CONFIG["number_range"][1]+1))
        if is_win:
            win_num = random.choice(user_nums)
        else:
            non_user_numbers = list(all_numbers - set(user_nums))
            win_num = random.choice(non_user_numbers)
        
        if is_win:
            await db_manager.modify_points(user.id, reward)
            
        result_text = (
            f"🎯 中奖号码：{win_num}\n"
            f"📝 你的号码：{', '.join(map(str, sorted(user_nums)))}\n"
            f"🏆 结果：{'🎉 中奖！+' + str(reward) + '积分' if is_win else '❌ 未中奖'}\n"
            f"📅 剩余次数：{remaining - 1}/{GUA_CONFIG['daily_limit']}"
        )
        
        await query.edit_message_text(result_text)
        
    except Exception as e:
        logger.error(f"刮刮乐处理失败：{str(e)}")
        await query.edit_message_text("❌ 发生错误，请稍后再试")

async def check_gua_remaining(user_id: int) -> int:
    #挂挂乐次数检查
    pool = await db_manager.get_pool()
    today = datetime.utcnow().date()
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("""
                SELECT times_used FROM gua_records
                WHERE user_id = %s AND date = %s
            """, (user_id, today))
            result = await cursor.fetchone()
            used_times = result[0] if result else 0
            remaining = GUA_CONFIG["daily_limit"] - used_times
            return max(remaining, 0)

async def checkin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    #签到
    user = update.effective_user
    message = update.message
    
    if message.chat.type not in ["group", "supergroup"]:
        await message.reply_text("🌱 请在群组内签到哦~")
        return
    
    try:
        earned, is_new = await db_manager.daily_checkin(user.id, user.full_name)
        
        if not is_new:
            reply_text = (
                "⏳ 今日已签到\n"
                "🕒 下次签到时间：次日 00:00 (UTC)"
            )
            reply_msg = await message.reply_text(reply_text)
        else:
            stars = "⭐" * min(earned, 5) + "✨" * max(earned-5, 0)
            reply_text = (
                f"{stars}\n"
                f"🎉 签到成功！\n"
                f"📅 今日获得 {earned} 积分\n"
                f"⏳ 本条消息将在10秒后消失"
            )
            reply_msg = await message.reply_text(reply_text)
        
        context.job_queue.run_once(
            callback=auto_delete_messages,
            when=10,
            data={
                "chat_id": update.message.chat_id,
                "user_msg_id": update.message.message_id,
                "bot_msg_id": reply_msg.message_id
            },
            name=f"delete_checkin_{update.message.message_id}"
        )
        
    except Exception as e:
        logger.error(f"签到失败：{str(e)}", exc_info=True)
        await message.reply_text("❌ 签到失败，请稍后再试")

async def book_repository(update: Update, context: ContextTypes.DEFAULT_TYPE):
    #书库自动回复
    message = update.message
    
    if message.chat.type not in ["group", "supergroup"]:
        return
    
    try:
        # 发送格式化的可复制消息
        repo_info = (
            f"📚 书库信息（20秒后自动删除）\n"
            f"├ 地址: `{CONFIG['book_repo']['url']}`\n"
            f"├ 账号: `{CONFIG['book_repo']['username']}`\n"
            f"├ 密码: `{CONFIG['book_repo']['password']}`\n"
            f"└ 注意: {CONFIG['book_repo']['notice']}"
        )
        
        sent_msg = await message.reply_text(
            repo_info,
            parse_mode="MarkdownV2"
        )
        
        context.job_queue.run_once(
            callback=auto_delete_messages,
            when=20,
            data={
                "chat_id": message.chat_id,
                "user_msg_id": message.message_id,
                "bot_msg_id": sent_msg.message_id
            },
            name=f"delete_bookinfo_{message.message_id}"
        )
        
    except Exception as e:
        logger.error(f"书库信息发送失败: {str(e)}")


async def admin_remove_group(update: Update, context):
    #群组扯权
    user = update.effective_user
    if user.id not in CONFIG["admin_ids"]:
        await update.message.reply_text("⚠️ 你没有权限执行此操作")
        return

    command = update.message.text.strip().split()
    if len(command) < 2:
        await update.message.reply_text("用法：/removegroup <群组ID>")
        return

    group_id = int(command[1])
    await db_manager.remove_authorized_group(group_id)
    await update.message.reply_text(f"✅ 已移除群组授权：{group_id}")

async def my_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    #查询积分
    user = update.effective_user
    message = update.message
    
    try:
        points = await db_manager.get_user_points(user.id)
        cult_data = await db_manager.get_cultivation_data(user.id)
        logger.info(f"修仙数据查询结果：{cult_data}")
        stage_name = CULTIVATION_STAGES[cult_data["stage"]]
        
        sent_msg = await message.reply_text(
            f"📊 您的当前积分\n"
            f"├ 用户ID：{user.id}\n"
            f"├ 用户名：{user.full_name}\n"
            f"├ 当前境界：{stage_name}\n"
            f"├ 突破丹：{cult_data['pills']}枚\n"
            f"├ 下次突破需：{cult_data['next_cost']}积分\n"
            f"└ 总积分(灵石)：{points} 分"
        )
        
        context.job_queue.run_once(
            callback=auto_delete_messages,
            when=10,
            data={
                "chat_id": update.message.chat_id,
                "user_msg_id": update.message.message_id,
                "bot_msg_id": sent_msg.message_id
            },
            name=f"delete_my_{update.message.message_id}"
        )
        
    except Exception as e:
        logger.error(f"查询积分失败：{str(e)}")
        await message.reply_text("❌ 查询积分失败，请稍后再试")


async def auto_delete_bot_message(context: ContextTypes.DEFAULT_TYPE):
    #自动删除机器人信息
    job = context.job
    try:
        await context.bot.delete_message(
            chat_id=int(job.data["chat_id"]),
            message_id=int(job.data["bot_msg_id"])
        )
        logger.debug(f"已删除机器人消息：{job.data['bot_msg_id']}")
    except Exception as e:
        logger.warning(f"机器人消息删除失败：{str(e)}")

async def process_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    #文件转存
    message = update.message
    logger.info(f"收到文件: {message.document.file_name}")
    user = message.from_user
    doc = message.document

    #文件类型检查
    file_ext = Path(doc.file_name).suffix.lower() if doc.file_name else None
    if file_ext not in CONFIG["allowed_extensions"]:
        logger.warning(f"拒绝非小说文件: {doc.file_name}")
        return

    try:
        #下载文件
        tg_file: File = await doc.get_file()
        file_path = Path(CONFIG["download_path"]) / doc.file_name
        await tg_file.download_to_drive(file_path)
        logger.info(f"文件已下载到: {file_path}")

        #计算MD5
        md5 = await calculate_md5(file_path)
        logger.info(f"计算得到MD5: {md5}")

        async with (await db_manager.get_pool()).acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """INSERT INTO users (user_id, username, points)
                       VALUES (%s, %s, 0)
                       ON DUPLICATE KEY UPDATE 
                       username = VALUES(username)""",
                    (user.id, user.username or "")
                )

                #检查MD5
                await cursor.execute(
                    "SELECT 1 FROM files WHERE md5 = %s FOR UPDATE",
                    (md5,)
                )
                if await cursor.fetchone():
                    logger.warning(f"检测到重复文件: {md5}")
                    await message.reply_text("⚠️ 重复文件，不计积分")
                    await conn.rollback()
                    try:
                        file_path.unlink()
                    except FileNotFoundError:
                        pass
                    return

                await cursor.execute(
                    "INSERT INTO files (md5, user_id) VALUES (%s, %s)",
                    (md5, user.id)
                )

                await cursor.execute(
                    "UPDATE users SET points = points + %s WHERE user_id = %s",
                    (CONFIG["points_per_book"], user.id)
                )

                await conn.commit()

                await cursor.execute(
                    "SELECT points FROM users WHERE user_id = %s",
                    (user.id,)
                )
                points = (await cursor.fetchone())[0]

                sent_msg = await message.reply_text(
                    f"✅ 已收录！\n"
                    f"+{CONFIG['points_per_book']}积分\n"
                    f"当前总积分：{points}"
                )
                
                context.job_queue.run_once(
                    callback=auto_delete_bot_message,
                    when=10,
                    data={
                        "chat_id": message.chat_id,
                        "bot_msg_id": sent_msg.message_id
                    },
                    name=f"delete_file_confirm_{sent_msg.message_id}"
                )

    except Exception as e:
        logger.error(f"处理文件失败: {str(e)}", exc_info=True)
        if 'file_path' in locals():
            try:
                file_path.unlink()
            except:
                pass
        await message.reply_text("❌ 处理文件时发生错误，请联系管理员")
        raise


async def modify_points_command(update: Update, context, is_add: bool):
    #积分增删
    user = update.effective_user
    message = update.message
    
    if user.id not in CONFIG["admin_ids"]:
        await message.reply_text("⚠️ 权限不足")
        return
    
    if not message.reply_to_message or message.chat.type == "private":
        await message.reply_text("⚠️ 请通过回复群成员消息使用此命令")
        return
    
    try:
        amount = int(context.args[0])
        if amount <= 0:
            raise ValueError
    except (IndexError, ValueError):
        verb = "增加" if is_add else "扣除"
        await message.reply_text(f"⚠️ 用法：/{'add' if is_add else 'del'} <正整数>\n示例：/{'add' if is_add else 'del'} 50")
        return
    
    target_user = message.reply_to_message.from_user
    if target_user.is_bot:
        await message.reply_text("⚠️ 不能操作机器人")
        return
    
    try:
        delta = amount if is_add else -amount
        new_points = await db_manager.modify_points(target_user.id, delta)
        
        action = "增加" if is_add else "扣除"
        await message.reply_text(
            f"✅ 操作成功\n"
            f"目标用户：{target_user.full_name}\n"
            f"操作类型：{action} {amount} 积分\n"
            f"当前积分：{new_points}"
        )
        
    except Exception as e:
        logger.error(f"积分修改失败：{str(e)}")
        await message.reply_text("❌ 操作失败，请检查日志")

async def add_points(update: Update, context):
    #加分
    await modify_points_command(update, context, is_add=True)

async def del_points(update: Update, context):
    #扣分
    await modify_points_command(update, context, is_add=False)

async def welcome_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    #欢迎新群友
    message = update.message
    if not message or not message.new_chat_members:
        return

    try:
        await message.delete()
    except Exception as e:
        logger.warning(f"删除系统提示失败: {str(e)}")

    for new_member in message.new_chat_members:
        if new_member.is_bot:
            continue
        
        safe_name = escape_markdown(new_member.full_name, version=2)
        safe_text = (
            f"🎉 欢迎 [{safe_name}](tg://user?id={new_member.id}) 加入本群！\n"
            "📚 群规请查看\>置顶消息第一条\n"
            "💬 畅聊时请注意遵守群规哦\~"
        )
        
        try:
            sent_msg = await context.bot.send_message(
                chat_id=message.chat.id,
                text=safe_text,
                parse_mode="MarkdownV2",
                disable_web_page_preview=True
            )
            
            context.job_queue.run_once(
                callback=delete_welcome_message,
                when=20,
                data={
                    "chat_id": message.chat.id,
                    "message_id": sent_msg.message_id
                },
                name=f"delete_welcome_{sent_msg.message_id}"
            )
            
        except Exception as e:
            logger.error(f"发送欢迎消息失败: {str(e)}")
            
            await context.bot.send_message(
                chat_id=message.chat.id,
                text=f"🎉 欢迎新成员 {new_member.full_name} 加入！\n请查看置顶群规",
                disable_web_page_preview=True
            )

async def delete_welcome_message(context: ContextTypes.DEFAULT_TYPE):
    #删除欢迎消息
    job = context.job
    try:
        await context.bot.delete_message(
            chat_id=job.data["chat_id"],
            message_id=job.data["message_id"]
        )
    except Exception as e:
        logger.warning(f"删除欢迎消息失败: {str(e)}")

async def breakthrough(update: Update, context: ContextTypes.DEFAULT_TYPE):
    #境界突破
    user = update.effective_user
    message = update.message
    
    try:
        cult_data = await db_manager.get_cultivation_data(user.id)
        if not cult_data:
            await message.reply_text("❌ 修仙数据初始化失败，请联系管理员")
            return
        current_stage = cult_data["stage"]
        logger.info(f"用户 {user.id} 突破前境界：{current_stage}")
        current_stage_name = CULTIVATION_STAGES[current_stage]
        
        #境界上限检查
        if current_stage >= len(CULTIVATION_STAGES)-1:
            reply = await message.reply_text("🚫 天道桎梏，此方世界已无法容纳更高境界！")
            context.job_queue.run_once(lambda ctx: ctx.bot.delete_message(
                chat_id=message.chat_id, message_id=reply.message_id), 20)
            return

        #判断是否为大境界突破
        is_major = current_stage in BREAKTHROUGH_PROBABILITY
        required_points = cult_data["next_cost"]
        user_points = await db_manager.get_user_points(user.id)

        #积分不足提示
        if user_points < required_points:
            reply = await message.reply_text(
                f"💸 突破《{current_stage_name}》需{required_points}灵石\n"
                f"当前灵石：{user_points}（不足{required_points - user_points}）"
            )
            context.job_queue.run_once(lambda ctx: ctx.bot.delete_message(
                chat_id=message.chat_id, message_id=reply.message_id), 20)
            return

        #突破丹检查
        if is_major and cult_data["pills"] < 1:
            reply = await message.reply_text(
                f"⚠ 突破大境界需焚香沐浴，以【破境丹】护法！\n"
                f"当前破境丹：{cult_data['pills']}枚"
            )
            context.job_queue.run_once(lambda ctx: ctx.bot.delete_message(
                chat_id=message.chat_id, message_id=reply.message_id), 20)
            return

        #突破概率
        success = True
        if is_major:
            success = random.random() < BREAKTHROUGH_PROBABILITY[current_stage]

        async with (await db_manager.get_pool()).acquire() as conn:
            async with conn.cursor() as cursor:
                #扣除积分
                await cursor.execute(
                    "UPDATE users SET points = points - %s WHERE user_id = %s",
                    (required_points, user.id)
                )

                if success:
                    new_stage = current_stage + 1
                    new_cost = int(required_points * (2 if is_major else 1.5))
                    
                    #更新境界
                    await cursor.execute(
                        """UPDATE user_cultivation 
                           SET stage = %s, next_cost = %s 
                           WHERE user_id = %s""",
                        (new_stage, new_cost, user.id)
                    )
                    
                    #扣除突破丹
                    if is_major:
                        await cursor.execute(
                            "UPDATE user_cultivation SET pills = pills - 1 WHERE user_id = %s",
                            (user.id,)
                        )

                    next_stage_name = CULTIVATION_STAGES[new_stage]
                    success_text = random.choice([
                        f"🌪️ 紫气东来三万里！{user.full_name}成功突破至《{next_stage_name}》！",
                        f"⚡ 雷云翻涌间，{user.full_name}的修为已臻《{next_stage_name}》！",
                        f"🌅 朝阳初升，{user.full_name} 沐浴晨晖踏入《{next_stage_name}》之境！",
                        f"🌌 星河倒悬，{user.full_name} 引动周天星力晋升《{next_stage_name}》！",
                        f"🗻 山岳共鸣！{user.full_name} 感悟地脉玄机突破至《{next_stage_name}》！",
                        f"🌀 灵气风暴中心，{user.full_name} 逆天改命成就《{next_stage_name}》！",
                        f"🌋 熔岩为浴，{user.full_name} 以地火淬体迈入《{next_stage_name}》阶段！",
                        f"❄️ 冰封千里的极寒中，{user.full_name} 明悟《{next_stage_name}》真谛！",
                        f"🌊 潮声如雷，{user.full_name} 借惊涛之势冲破《{next_stage_name}》桎梏！",
                        f"🎇 天花乱坠，{user.full_name} 顿悟天道法则臻至《{next_stage_name}》！",
                        f"🌩️ 九重雷劫下，{user.full_name} 涅槃重生踏入《{next_stage_name}》！",
                        f"🕳️ 虚空破碎，{user.full_name} 穿梭阴阳领悟《{next_stage_name}》玄奥！",
                        f"🌠 流星贯体，{user.full_name} 融合星核之力突破《{next_stage_name}》！",
                        f"🔥 焚尽心魔，{user.full_name} 于业火中证得《{next_stage_name}》大道！",
                        f"🌫️ 迷雾散尽，{user.full_name} 勘破轮回成就《{next_stage_name}》金身！"
                    ])
                    logger.info(f"用户 {user.id} 突破成功！原境界：{current_stage}，新境界：{new_stage}")
                    reply_text = (
                        f"{success_text}\n▬▬▬▬▬▬▬▬▬▬\n"
                        f"💰 消耗灵石：{required_points}\n"
                        f"⚡ 下境需求：{new_cost}灵石"
                    )
                else:
                    penalty = int(required_points * 0.3)
                    await cursor.execute(
                        "UPDATE users SET points = points - %s WHERE user_id = %s",
                        (penalty, user.id)
                    )
                    
                    failure_reason = random.choice([
                        "心魔侵扰导致真元逆流",
                        "天劫突然降临打断突破"
                    ])
                    reply_text = (
                        f"💥 {failure_reason}，《{CULTIVATION_STAGES[current_stage+1]}》突破失败！\n"
                        f"▬▬▬▬▬▬▬▬▬▬\n"
                        f"💔 走火入魔损失：{penalty}灵石\n"
                        f"💊 破境丹已消耗：{1 if is_major else 0}枚"
                    )

                await conn.commit()

        sent_msg = await message.reply_text(reply_text)

        context.job_queue.run_once(
            lambda ctx: ctx.bot.delete_message(
                chat_id=message.chat_id,
                message_id=sent_msg.message_id
            ), 20
        )
        await message.delete()

    except Exception as e:
        logger.error(f"突破处理失败：{str(e)}", exc_info=True)
        reply = await message.reply_text("🈲 突破途中遭遇域外天魔，请速速调息！")
        context.job_queue.run_once(lambda ctx: ctx.bot.delete_message(
            chat_id=message.chat_id, message_id=reply.message_id), 20)

async def handle_rob(update: Update, context: ContextTypes.DEFAULT_TYPE):
    #打劫
    message = update.message
    user_a = message.from_user
    reply_to = message.reply_to_message

    if not reply_to or reply_to.from_user.is_bot:
        reply = await message.reply_text("🦹 请对目标修士的消息回复使用此命令")
        await delete_messages(context, [message, reply])
        return

    user_b = reply_to.from_user
    if user_a.id == user_b.id:
        reply = await message.reply_text("🤡 道友为何要自劫？")
        await delete_messages(context, [message, reply])
        return

    #检查次数限制
    if await db_manager.get_rob_count(user_a.id) >= ROB_CONFIG["daily_limit"]:
        reply = await message.reply_text("🛑 今日打劫次数已用尽，明日请早")
        await delete_messages(context, [message, reply])
        return

    #获取境界
    cult_a = await db_manager.get_cultivation_data(user_a.id)
    cult_b = await db_manager.get_cultivation_data(user_b.id)
    stage_a = cult_a["stage"]
    stage_b = cult_b["stage"]

    major_stage_a = stage_a // 3
    major_stage_b = stage_b // 3

    stage_name_a = CULTIVATION_STAGES[stage_a]
    stage_name_b = CULTIVATION_STAGES[stage_b]

    #境界差距判断
    if major_stage_b > major_stage_a + 1:
        reply = await message.reply_text(
            f"💢 {user_a.full_name}（{stage_name_a}）妄图挑战{stage_name_b}大能\n"
            "⚡ 虚空中传来一声冷哼：区区小辈，不知天高地厚！"
        )
        await delete_messages(context, [message, reply], [0, 5])
        return

    if major_stage_b < major_stage_a - 1:
        reply = await message.reply_text(
            f"👎 {user_a.full_name}（{stage_name_a}）竟想欺凌{stage_name_b}修士\n"
            "💢 围观修士纷纷摇头：你要点B脸行不？"
        )
        await delete_messages(context, [message, reply], [0, 5])
        return

    #记录打劫次数
    if not await db_manager.record_rob(user_a.id):
        reply = await message.reply_text("🚧 道友出手太快，需调息片刻")
        await delete_messages(context, [message, reply])
        return

    #打劫流程
    try:
        #逃脱概率
        if random.random() < ROB_CONFIG["escape_prob"]:
            msg = await send_dice_with_animation(context, message.chat_id)
            reply_text = random.choice([
                f"🏃♂️ {user_b.full_name} 施展神行百变，瞬间消失无踪！",
                f"🕶️ {user_b.full_name} 留下替身木偶戏耍了 {user_a.full_name}",
                f"🌫️ 一阵迷雾过后，{user_b.full_name} 早已不见踪影"
            ])
            reply = await context.bot.send_message(
                chat_id=message.chat_id,
                text=reply_text,
                reply_to_message_id=message.message_id
            )
            await delete_messages(context, [message, msg, reply], delays=[0, 5, 8])
            return

        #修为比拼
        stage_a = (await db_manager.get_cultivation_data(user_a.id))["stage"]
        stage_b = (await db_manager.get_cultivation_data(user_b.id))["stage"]
        dice_a = await send_dice_with_animation(context, message.chat_id)
        dice_b = await send_dice_with_animation(context, message.chat_id)

        #计算点数
        point_a = dice_a.dice.value + (ROB_CONFIG["stage_bonus"] if stage_a > stage_b else 0)
        point_b = dice_b.dice.value + (ROB_CONFIG["stage_bonus"] if stage_b > stage_a else 0)
        winner = user_a if point_a > point_b else user_b if point_b > point_a else None

        #平局
        if not winner:
            reply = await context.bot.send_message(
                chat_id=message.chat_id,
                text=f"⚔️ 双方势均力敌！{user_a.full_name} 与 {user_b.full_name} 各自退去",
            )
            await delete_messages(context, [message, dice_a, dice_b, reply], delays=[0, 8, 8, 15])
            return

        loser = user_b if winner == user_a else user_a
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("💰 破财消灾", callback_data=f"rob_pay_{winner.id}_{loser.id}_{loser.id}")],
            [InlineKeyboardButton("⚔️ 死战到底", callback_data=f"rob_fight_{winner.id}_{loser.id}_{loser.id}")]
        ])

        reply_text = random.choice([
            f"🎲 {winner.full_name} 力压菜鸡！{loser.full_name} 要如何应对？",
            f"🏆 胜负已分！{loser.full_name} 面临 {winner.full_name} 的威胁",
            f"💥 {loser.full_name} 被彻底压制！请选择求饶方式："
        ])
        
        reply = await context.bot.send_message(
            chat_id=message.chat_id,
            text=reply_text,
            reply_markup=keyboard
        )
        await delete_messages(context, [message, dice_a, dice_b], delays=[0, 8, 8])
        context.job_queue.run_once(
            lambda ctx: ctx.bot.delete_message(chat_id=reply.chat_id, message_id=reply.message_id),
            60
        )

    except Exception as e:
        logger.error(f"打劫处理失败: {str(e)}")
        await delete_messages(context, [message])

def get_major_stage(stage_index: int) -> int:
    #境界划分
    return stage_index // 3

def get_stage_range(stage_index: int) -> Tuple[int, int]:
    """获取可挑战的境界范围"""
    major = get_major_stage(stage_index)
    return (major-1)*3, (major+2)*3

async def handle_rob_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    #打劫
    query = update.callback_query
    await query.answer()
    
    try:
        _, action, winner_id, loser_id, allowed_user_id = query.data.split("_")
        winner_id = int(winner_id)
        loser_id = int(loser_id)
        allowed_user_id = int(allowed_user_id)

        
        if query.from_user.id != allowed_user_id:
            loser_user = await context.bot.get_chat(loser_id)
            await query.answer(
                f"🚫 只有 {escape_markdown(loser_user.full_name,2)} 可以操作！", 
                show_alert=True
            )
            return

        winner = await context.bot.get_chat(winner_id)
        loser = await context.bot.get_chat(loser_id)

        #破财消灾
        if action == "pay":
            stolen = int((await db_manager.get_user_points(loser_id)) * random.uniform(*ROB_CONFIG["penalty_ratio"]))
            
            actual_stolen = await db_manager.modify_points(loser_id, -stolen)
            if actual_stolen > 0:
                await db_manager.modify_points(winner_id, actual_stolen)
                reply_text = random.choice([
                    f"💰 {escape_markdown(loser.full_name,2)} 的储物袋破了个洞，掉出{actual_stolen}灵石！",
                    f"⚔️ 寒光一闪，{escape_markdown(loser.full_name,2)} 被迫交出 {actual_stolen}灵石"
                ])
            else:
                reply_text = f"💸 {escape_markdown(loser.full_name,2)} 的储物袋空空如也！"

            await query.edit_message_text(reply_text)
            await delete_messages(context, [query.message], delays=[8])

        #死战到底
        elif action == "fight":
            dice_winner = await send_dice_with_animation(context, query.message.chat_id)
            dice_loser = await send_dice_with_animation(context, query.message.chat_id)
            
            if dice_winner.dice.value > dice_loser.dice.value:
                #废除修为
                await db_manager.update_cultivation_stage(loser_id, 0, 10)
                await db_manager.modify_points(loser_id, -9999)
                reply_text = random.choice([
                    f"💀 道基尽毁！{escape_markdown(loser.full_name,2)} 修为尽失",
                    f"🪦 生死道消，{escape_markdown(loser.full_name,2)} 转世重修"
                ])
            else:
                reply_text = random.choice([
                    f"🍃 绝处逢生！{escape_markdown(loser.full_name,2)} 逃出生天",
                    f"🌈 虹光乍现，{escape_markdown(loser.full_name,2)} 消失于虚空"
                ])
            
            await query.edit_message_text(reply_text)
            await delete_messages(context, [dice_winner, dice_loser, query.message], delays=[5, 5, 8])

    except Exception as e:
        logger.error(f"打劫回调失败: {str(e)}")
        await query.edit_message_text("🈲 天道紊乱，此次打劫作废")


async def send_dice_with_animation(context, chat_id):
    #骰子
    msg = await context.bot.send_dice(chat_id, emoji="🎲")
    await asyncio.sleep(3.5)
    return msg

async def delete_messages(context, messages, delays=None):
    for i, msg in enumerate(messages):
        delay = delays[i] if delays else 8
        context.job_queue.run_once(
            lambda ctx, m=msg: ctx.bot.delete_message(
                chat_id=m.chat_id, 
                message_id=m.message_id
            ),
            delay
        )

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return
    
    if message.chat.type == "private":
        return

    group_id = message.chat.id
    if not await db_manager.is_group_authorized(group_id):
        return
    
    user = message.from_user
    group_id = message.chat.id
    pool = await db_manager.get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("""
                INSERT IGNORE INTO user_group (user_id, group_id)
                VALUES (%s, %s)
            """, (user.id, group_id))
            await conn.commit()

    if message.document:
        await process_document(update, context)
        return

    #一句话一分
    user = message.from_user
    text = message.text or message.caption or ""

    hanzi_count = len(HANZI_PATTERN.findall(text))
    if hanzi_count >= 3:
        try:
            await db_manager.silent_add_points(
                user_id=user.id,
                username=user.full_name
            )
            #突破丹掉落概率
            if random.random() < 0.05:
                try:
                    await db_manager.add_breakthrough_pill(user.id)
                    flavor_text = random.choice([
                        f"✨ 天地灵气汇聚，{user.full_name} 偶得一枚晶莹剔透的突破丹！",
                        f"🌌 福至心灵，{user.full_name} 于顿悟中炼成突破丹！",
                        f"🍃 灵雾弥漫间，{user.full_name} 拾得上古修士遗留的突破丹！",
                        f"🔥 丹炉轰鸣！{user.full_name} 以三昧真火淬炼出突破丹！",
                        f"🌊 北海秘境开启，{user.full_name} 夺得龙宫至宝——突破丹！",
                        f"⚡ 渡劫余波中，{user.full_name} 截取天雷精华凝成突破丹！",
                        f"🌙 月华倾泻，{user.full_name} 接引太阴之气结成突破丹！",
                        f"🐉 神龙摆尾！{user.full_name} 获赠龙族秘传的突破丹！",
                        f"🌋 地脉喷涌，{user.full_name} 采集地心炎髓炼成突破丹！",
                        f"❄️ 北极玄冰窟中，{user.full_name} 寻得突破丹！",
                        f"🌠 流星坠地，{user.full_name} 发现星核所化的突破丹！",
                        f"🍶 畅饮仙酿后，{user.full_name} 体内竟孕育出突破丹！",
                        f"📜 破解古卷残篇，{user.full_name} 复原失传已久的突破丹！",
                        f"🦚 凤凰涅槃时，{user.full_name} 采集真火余烬炼成突破丹！",
                        f"💫 时空裂隙乍现，{user.full_name} 夺取混沌之气凝结突破丹！"
                    ])
                    
                    reply = await message.reply_text(
                        f"{flavor_text}\n（此消息10秒后消失）",
                        reply_to_message_id=message.message_id
                    )
                    
                    context.job_queue.run_once(
                        lambda ctx: ctx.bot.delete_message(
                            chat_id=message.chat_id,
                            message_id=reply.message_id
                        ), 10
                    )
                except Exception as e:
                    logger.error(f"突破丹发放失败: {str(e)}")
            #奇遇
            try:
                user_state = await db_manager.get_user_state(user.id)
                
                for event in RANDOM_EVENTS:
                    if random.random() > event["probability"]:
                        continue
                        
                    if "condition" in event and not event["condition"](user_state):
                        continue
        
                    handler = globals().get(event["action"])
                    if not handler:
                        continue
        
                    result = await handler(user.id, user_state)
                    reply_msg = await message.reply_text(result["msg"])
                    
                    context.job_queue.run_once(
                        lambda ctx: ctx.bot.delete_message(
                            chat_id=message.chat_id,
                            message_id=reply_msg.message_id
                        ),
                        result["duration"]
                    )
                    
                    break
            
            except Exception as e:
                logger.error(f"奇遇处理失败：{str(e)}")
            logger.info(f"用户 {user.full_name}({user.id}) 获得静默积分")
        except Exception as e:
            logger.error(f"静默积分增加失败: {str(e)}", exc_info=True)

async def enslave_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    #帮主任命奴隶
    message = update.message
    user_a = message.from_user
    group_id = message.chat.id
    
    today = datetime.utcnow().date()
    async with (await db_manager.get_pool()).acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("""
                SELECT 1 FROM slave_records 
                WHERE master_id = %s AND created_date = %s
            """, (user_a.id, today))
            if await cursor.fetchone():
                await message.reply_text("🈲 今日已选定奴隶，请明日再来")
                await message.delete()
                return

    if not message.reply_to_message or message.chat.type == "private":
        await message.reply_text("⚡ 请通过回复目标修士的消息使用此令")
        await message.delete()
        return
        
    gang_leader = await select_gang_leader(group_id)
    if gang_leader["user_id"] != user_a.id:
        await message.reply_text("❌ 此乃帮主秘法，尔等岂可妄用！")
        await message.delete()
        return

    user_b = message.reply_to_message.from_user
    if user_b.is_bot or user_b.id == user_a.id:
        await message.reply_text("🌀 帮主大人，这是孝敬给您的奴隶，比较野")
        await message.delete()
        return

    # 写入数据库
    async with (await db_manager.get_pool()).acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("""
                INSERT INTO slave_records 
                (master_id, slave_id, group_id, created_date)
                VALUES (%s, %s, %s, %s)
            """, (user_a.id, user_b.id, group_id, today))
            await conn.commit()

    #契约
    text = (
        f"🌌【主奴契约·天道认证】\n"
        f"✨ {escape_markdown(escape_markdown(user_a.full_name, version=2), version=2)} 帮主手掐法诀，祭出奴隶印记！\n"
        f"🔥 只见一道金光没入 {escape_markdown(escape_markdown(user_b.full_name, version=2), version=2)} 眉心\n"
        f"🐾 霎时间， {escape_markdown(escape_markdown(user_b.full_name, version=2), version=2)} 眼神一下空洞起来\n"
        f"🐾 其头顶竟冒出两个猫耳朵，屁股也\\.\\.\\.好像长出了一条尾巴正摇曳\n"
        f"💢 帮主冷喝一声：『孽畜，还不速速立下跪下！』\n"
        f"💢  {escape_markdown(escape_markdown(user_b.full_name, version=2), version=2)} 一哆嗦，马上跪下来！\n"
        f"📜 请道友 {escape_markdown(escape_markdown(user_b.full_name, version=2), version=2)} 诵念：\n"
        f"『{escape_markdown(escape_markdown(SLAVE_RULES['init_phrase'], version=2), version=2)}』（必须一字不差的打完）"
    )
    
    sent_msg = await message.reply_text(text, parse_mode="MarkdownV2")
    await message.delete()
    
    # 删除契约消息
    context.job_queue.run_once(
        lambda ctx: ctx.bot.delete_message(
            chat_id=sent_msg.chat_id, 
            message_id=sent_msg.message_id
        ), 
        30
    )

async def enforce_slavery(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user = message.from_user
    if message.chat.type == "private" or user.is_bot:
        return

    async with (await db_manager.get_pool()).acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("""
                SELECT master_id, created_date, confirmed 
                FROM slave_records 
                WHERE slave_id = %s AND group_id = %s
                ORDER BY created_date DESC 
                LIMIT 1
            """, (user.id, message.chat.id))
            record = await cursor.fetchone()





    if not record or record["created_date"] != datetime.utcnow().date():
        return


    master_id, _, confirmed = record
    if not confirmed:
        if message.text != SLAVE_RULES["init_phrase"]:
            await message.delete()
            warning = await message.reply_text(
                f"⚡ @{user.username or user.id} 灵台混沌未立誓！速诵『{SLAVE_RULES['init_phrase']}』",
                parse_mode="MarkdownV2"
            )
            context.job_queue.run_once(
                lambda ctx: ctx.bot.delete_message(
                    chat_id=warning.chat_id,
                    message_id=warning.message_id
                ), 
                10
            )
    else:
        if message.text and SLAVE_RULES["daily_phrase"] not in message.text:
            await message.delete()
            reminder = await message.reply_text(
                f"🐾 @{user.username or user.id} 忘了带尾音哦～要加『喵』～",
                parse_mode="MarkdownV2"
            )
            context.job_queue.run_once(
                lambda ctx: ctx.bot.delete_message(
                    chat_id=reminder.chat_id,
                    message_id=reminder.message_id
                ), 
                10
            )

async def confirm_slavery(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if message.text != SLAVE_RULES["init_phrase"]:
        return

    async with (await db_manager.get_pool()).acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("""
                UPDATE slave_records SET confirmed = TRUE 
                WHERE slave_id = %s AND created_date = %s
            """, (message.from_user.id, datetime.utcnow().date()))
            await conn.commit()

    text = (
        f"🎇【心魔大誓·天道认证】\n"
        f"⚡ 九霄雷动，{escape_markdown(message.from_user.full_name,2)} 的魂灯已入帮主命牌！\n"
        f"🐾 自此刻起至子时三刻，言行当以主人为本\n"
        f"📜 违者将受万蚁噬心之苦！"
    )
    sent_msg = await message.reply_text(text, parse_mode="MarkdownV2")
    
    for _ in range(3):
        await asyncio.sleep(1)
        await message.chat.send_message(
            text=random.choice([
                f"🌌 虚空震颤，恭贺 {escape_markdown(message.from_user.full_name,2)} 成为帮主奴隶！",
                f"🎉 千妖俯首，万灵齐贺新奴入籍！",
                f"🍃 清风为凭，明月为证，此契天地共鉴！"
            ]),
            parse_mode="MarkdownV2"
        )

async def set_commands(app: Application):
    await app.bot.set_my_commands(
        commands=[
            BotCommand("addgroup", "管理员添加授权群组（需要群组ID）"),
            BotCommand("removegroup", "管理员移除授权群组（需要群组ID）"),
            BotCommand("my", "查看我的积分"),
            BotCommand("checkin", "每日签到获取积分"),
            BotCommand("add", "管理员增加积分（回复消息使用）"),
            BotCommand("del", "管理员扣除积分（回复消息使用）")
        ],
        scope=BotCommandScopeAllPrivateChats()
    )

async def check_bot_username(app: Application):
    try:
        me = await app.bot.get_me()
        if me.username != BOT_USERNAME:
            logger.error(f"机器人用户名配置错误！当前：{me.username}，应配置为：{BOT_USERNAME}")
            exit(1)
    except Exception as e:
        logger.critical(f"机器人初始化失败: {str(e)}")
        exit(1)

async def register_commands(app: Application):
    await set_commands(app)
    await check_bot_username(app)
    set_gang_schedule(app)

def main():
    app = Application.builder() \
        .token(CONFIG["token"]) \
        .post_init(register_commands) \
        .build()

    app.add_handler(CommandHandler("nuli", enslave_member, filters=filters.ChatType.GROUPS))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_slavery), group=1)
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, enforce_slavery), group=2)

    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r'^书库$'), book_repository))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, message_handler))
    app.add_handler(MessageHandler(
        filters.StatusUpdate.NEW_CHAT_MEMBERS,
        welcome_new_members
    ))
    app.add_handler(CommandHandler("duihuan", group_exchange, filters.ChatType.GROUPS))
    app.add_handler(CommandHandler("duihuan", private_exchange, filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("gua", gua_command, filters=filters.ChatType.GROUPS))
    app.add_handler(CallbackQueryHandler(handle_rob_callback, pattern=r"^rob_"))
    app.add_handler(CallbackQueryHandler(button_callback))
    

    app.add_handler(CommandHandler("breakthrough", breakthrough, filters=filters.ChatType.GROUPS))
    app.add_handler(CommandHandler("checkin", checkin_command, filters=filters.ChatType.GROUPS))
    app.add_handler(CommandHandler("my", my_command, filters=filters.ChatType.GROUPS))
    app.add_handler(CommandHandler("add", add_points))
    app.add_handler(CommandHandler("del", del_points))
    app.add_handler(CommandHandler("addgroup", admin_add_group))
    app.add_handler(CommandHandler("removegroup", admin_remove_group))
    app.add_handler(CommandHandler("dajie", handle_rob, filters=filters.ChatType.GROUPS))
    app.add_handler(CommandHandler("paihang", paihang_command, filters=filters.ChatType.GROUPS))

    print("starting")
    app.run_polling()

if __name__ == "__main__":
    main()
