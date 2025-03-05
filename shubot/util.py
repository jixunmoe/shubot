from typing import cast

from telegram import Message
from telegram.ext import CallbackContext, JobQueue


async def _delete(ctx: CallbackContext):
    data = cast(dict, ctx.job.data)
    await ctx.bot.delete_message(**data)


def defer_delete(queue: JobQueue, message: Message, timeout: int = 30):
    queue.run_once(_delete, data={"chat_id": message.chat_id, "message_id": message.message_id}, when=timeout)


async def reply(src: Message, text: str, parse_mode=None, delete_prev_msg=True, defer_delete_by: int = 10):
    """
    回复消息并返回新消息对象

    :param src: 源消息对象
    :param text: 回复文本
    :param parse_mode: 解析模式
    :param delete_prev_msg: 是否删除源消息
    :param defer_delete_by: 延迟删除时间 (秒)

    :return: 新消息对象
    """
    new_msg = await src.reply_text(text, parse_mode=parse_mode)
    if delete_prev_msg:
        if defer_delete_by:
            from shubot.bot import ShuBot
            defer_delete(ShuBot.get_instance().get_job_queue(), src, timeout=defer_delete_by)
        else:
            await src.delete()
    return new_msg
