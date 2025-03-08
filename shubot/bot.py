import asyncio
import logging

from telegram import Bot, BotCommandScopeAllPrivateChats, BotCommand
from telegram.ext import Application, JobQueue

from shubot.command.checkin import CheckinCommand
from shubot.command.group_auth import GroupAuthCommand
from shubot.command.lottery import LotteryCommand
from shubot.command.user_info import UserInfoCommand
from shubot.command.rob import RobCommand
from shubot.command.slave import SlaveCommand
from shubot.config import Config
from shubot.database import DatabaseManager
from shubot.ext.command import BotCommandHandlerMixin

logger = logging.getLogger(__name__)


class ShuBot:
    _instance: "ShuBot" = None

    @staticmethod
    def get_instance():
        assert ShuBot._instance, "ShuBot never initialized"
        return ShuBot._instance

    _config: Config
    _app: Application
    _command_handlers: list[BotCommandHandlerMixin] = []

    def __init__(self, config: Config):
        # Setup singleton
        if not ShuBot._instance:
            ShuBot._instance = self

        self._config = config

        builder = Application.builder()
        builder.token(config.telegram.token)
        builder.post_init(self._on_post_init)
        self._app = builder.build()

        self._command_handlers.append(SlaveCommand(self._app, config))
        self._command_handlers.append(CheckinCommand(self._app, config))
        self._command_handlers.append(UserInfoCommand(self._app, config))
        self._command_handlers.append(RobCommand(self._app, config))
        self._command_handlers.append(LotteryCommand(self._app, config))

        self._command_handlers.append(GroupAuthCommand(self._app, config))

    async def _on_post_init(self, app: Application):
        logger.info("init db...")
        await DatabaseManager.get_instance().init_pool(self._config.db)
        logger.info("init command db...")
        await asyncio.gather(*(handler.init_db() for handler in self._command_handlers))

        logger.info("init bot startup...")
        await self._set_commands()
        await self._check_bot_username()
        logger.info("post init done")

    def run(self):
        logger.info("Bot polling")
        self._app.run_polling()

    def get_bot(self) -> Bot:
        # noinspection PyUnresolvedReferences
        return self._app.bot

    def get_job_queue(self) -> JobQueue:
        return self._app.job_queue

    async def _set_commands(self):
        await self.get_bot().set_my_commands(
            commands=[
                BotCommand("addgroup", "管理员添加授权群组（需要群组ID）"),
                BotCommand("removegroup", "管理员移除授权群组（需要群组ID）"),
                BotCommand("my", "查看我的积分"),
                BotCommand("checkin", "每日签到获取积分"),
                BotCommand("add", "管理员增加积分（回复消息使用）"),
                BotCommand("del", "管理员扣除积分（回复消息使用）"),
            ],
            scope=BotCommandScopeAllPrivateChats(),
        )

    async def _check_bot_username(self):
        bot = self.get_bot()
        try:
            me = await bot.get_me()
            if me.username != self._config.telegram.username:
                raise RuntimeError(f"机器人用户名配置错误！当前：{me.username}，应为：{self._config.telegram.username}")
        except Exception as e:
            logger.critical(f"机器人初始化失败: {str(e)}")
            exit(1)
