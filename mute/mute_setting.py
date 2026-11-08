# Source: HibiKier / zhenxun-org/zhenxun_bot_plugins (AGPL-3.0).
# Modified on 2026-11-08; see CHANGELOG.md.

from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Alconna, Args, Arparma, Match, Option, on_alconna
from nonebot_plugin_session import EventSession

from zhenxun.configs.config import BotConfig
from zhenxun.configs.utils import PluginExtraData, RegisterConfig
from zhenxun.services.log import logger
from zhenxun.utils.enum import PluginType
from zhenxun.utils.message import MessageUtils
from zhenxun.utils.rules import admin_check, ensure_group

from ._data_source import base_config, mute_manage
from .penalty import MAX_MUTE_DURATION_MINUTES, get_mute_duration

__plugin_meta__ = PluginMetadata(
    name="刷屏禁言",
    description="刷屏禁言相关操作",
    usage=f"""
    刷屏禁言相关操作，需要 {BotConfig.self_nickname} 有群管理员权限
    指令：
        刷屏设置: 查看当前设置
        -c [count]: 检测最大次数
        -t [time]: 规定时间内
        -d [duration]: 第一级基础禁言时长
        示例:
            刷屏设置 -c 10: 设置最大次数为10
            刷屏设置 -t 100 -d 20: 设置规定时间和禁言时长
            刷屏设置 -d 10: 设置禁言时长为10
        * 即 X 秒内发送同样消息 N 次，本周前四次按 M/3M/6M/36M 分钟递进禁言，
          第五次起每次翻倍，最高 30 天 *
    """.strip(),
    extra=PluginExtraData(
        author="HibiKier",
        version="0.2.0",
        menu_type="其他",
        plugin_type=PluginType.ADMIN,
        admin_level=base_config.get("MUTE_LEVEL", 5),
        configs=[
            RegisterConfig(
                key="MUTE_LEVEL",
                value=5,
                help="更改禁言设置的管理权限",
                default_value=5,
                type=int,
            ),
            RegisterConfig(
                key="MUTE_DEFAULT_COUNT",
                value=10,
                help="刷屏禁言默认检测次数",
                default_value=10,
                type=int,
            ),
            RegisterConfig(
                key="MUTE_DEFAULT_TIME",
                value=7,
                help="刷屏检测默认规定时间",
                default_value=7,
                type=int,
            ),
            RegisterConfig(
                key="MUTE_DEFAULT_DURATION",
                value=10,
                help="刷屏检测默认第一级基础禁言时长（分钟）",
                default_value=10,
                type=int,
            ),
        ],
    ).dict(),
)


_setting_matcher = on_alconna(
    Alconna(
        "刷屏设置",
        Option("-t|--time", Args["time", int], help_text="检测时长"),
        Option("-c|--count", Args["count", int], help_text="检测次数"),
        Option("-d|--duration", Args["duration", int], help_text="禁言时长"),
    ),
    rule=admin_check(1) & ensure_group,
    block=True,
    priority=5,
)


@_setting_matcher.handle()
async def _(
    session: EventSession,
    arparma: Arparma,
    time: Match[int],
    count: Match[int],
    duration: Match[int],
):
    group_id = session.id2
    if not session.id1 or not group_id:
        return
    _time = time.result if time.available else None
    _count = count.result if count.available else None
    _duration = duration.result if duration.available else None
    group_data = mute_manage.get_group_data(group_id)
    if _time is None and _count is None and _duration is None:
        duration_levels = [
            get_mute_duration(group_data.duration, level) for level in range(1, 5)
        ]
        await MessageUtils.build_message(
            f"最大次数：{group_data.count} 次\n"
            f"规定时间：{group_data.time} 秒\n"
            f"基础禁言时长：{group_data.duration:.2f} 分钟\n"
            f"本周前四次禁言时长：{' / '.join(map(str, duration_levels))} 分钟\n"
            "本周第五次起：每次在上一档基础上翻倍，"
            f"最高 {MAX_MUTE_DURATION_MINUTES // 24 // 60} 天\n"
            "【在规定时间内发送相同消息超过最大次数则禁言\n"
            "处罚次数每周五 00:00 清零，已生效的禁言不会提前解除\n"
            "基础禁言时长为0时关闭此功能】"
        ).finish(reply_to=True)
    if _time is not None and _time <= 0:
        await MessageUtils.build_message("检测时长必须大于 0 秒").finish(reply_to=True)
    if _count is not None and _count <= 0:
        await MessageUtils.build_message("检测次数必须大于 0 次").finish(reply_to=True)
    if _duration is not None and _duration < 0:
        await MessageUtils.build_message("禁言时长不能小于 0 分钟").finish(
            reply_to=True
        )
    if _time is not None:
        group_data.time = _time
    if _count is not None:
        group_data.count = _count
    if _duration is not None:
        group_data.duration = _duration
    await MessageUtils.build_message("设置成功!").send(reply_to=True)
    logger.info(
        f"设置禁言配置 time: {_time}, count: {_count}, duration: {_duration}",
        arparma.header_result,
        session=session,
    )
    mute_manage.save_data()
