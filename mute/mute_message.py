# Source: HibiKier / zhenxun-org/zhenxun_bot_plugins (AGPL-3.0).
# Modified on 2026-11-08; see CHANGELOG.md.

import time

from nonebot import on_message, require
from nonebot.adapters import Bot, Event
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import UniMsg
from nonebot_plugin_session import EventSession

from zhenxun.configs.config import BotConfig
from zhenxun.configs.utils import PluginExtraData
from zhenxun.models.ban_console import BanConsole
from zhenxun.services.log import logger
from zhenxun.utils.enum import PluginType
from zhenxun.utils.message import MessageUtils
from zhenxun.utils.platform import PlatformUtils
from zhenxun.utils.utils import FreqLimiter

from ._data_source import mute_manage
from .penalty import MutePenaltyStore, current_penalty_period, get_mute_duration

require("nonebot_plugin_localstore")

__plugin_meta__ = PluginMetadata(
    name="刷屏监听",
    description="",
    usage="",
    extra=PluginExtraData(
        author="HibiKier",
        version="0.2.0",
        menu_type="其他",
        plugin_type=PluginType.DEPENDANT,
    ).dict(),
)

_matcher = on_message(priority=1, block=False)

_flmt = FreqLimiter(30)
_penalty_store: MutePenaltyStore | None = None


def _get_penalty_store() -> MutePenaltyStore:
    global _penalty_store
    if _penalty_store is None:
        from nonebot_plugin_localstore import get_data_file

        _penalty_store = MutePenaltyStore(
            get_data_file("mute", "mute_penalties.sqlite3")
        )
    return _penalty_store


def _build_mute_notice(penalty_count: int) -> str:
    message = f"检测到恶意刷屏，{BotConfig.self_nickname}要把你关进小黑屋！"
    if penalty_count >= 2:
        message += f"这周已经是第{penalty_count}次啦，希望你好好反省！"
    return message


def _normalize_raw_segment(segment) -> str:
    """将原始消息段转换为刷屏检测用的稳定标记。"""
    seg_type = getattr(segment, "type", "")
    data = getattr(segment, "data", {}) or {}

    if seg_type == "text":
        return str(data.get("text", ""))
    if seg_type == "face":
        face_id = data.get("id")
        return f"[face:{face_id}]" if face_id is not None else "[face]"
    if seg_type == "image":
        return "[image]"
    if seg_type == "file":
        return "[file]"
    if seg_type == "forward":
        return "[forward]"
    if seg_type in {"record", "voice", "audio"}:
        return "[voice]"
    if seg_type == "video":
        return "[video]"
    if seg_type in {"json", "xml"}:
        return f"[{seg_type}]"
    if seg_type:
        return f"[segment:{seg_type}]"
    return ""


def _normalize_unimsg_segment(segment) -> str:
    seg_name = segment.__class__.__name__.lower()

    if seg_name == "text":
        return str(getattr(segment, "text", ""))
    if seg_name in {"emoji", "face"}:
        emoji_id = getattr(segment, "id", None)
        return f"[face:{emoji_id}]" if emoji_id is not None else "[face]"
    if seg_name == "image":
        return "[image]"
    if seg_name == "file":
        return "[file]"
    if seg_name == "reference":
        return "[forward]"
    if seg_name in {"voice", "audio"}:
        return "[voice]"
    if seg_name == "video":
        return "[video]"
    if seg_name == "hyper":
        return f"[{getattr(segment, 'format', 'hyper')}]"
    if seg_name == "other":
        origin = getattr(segment, "origin", None)
        return _normalize_raw_segment(origin) if origin else "[segment:other]"
    return f"[segment:{seg_name}]"


def _build_mute_message(event: Event, message: UniMsg) -> str:
    get_message = getattr(event, "get_message", None)
    if callable(get_message):
        try:
            raw_message = get_message()
        except Exception:
            raw_message = None
        if raw_message is not None:
            normalized = "".join(_normalize_raw_segment(seg) for seg in raw_message)
            if normalized:
                return normalized

    normalized = "".join(_normalize_unimsg_segment(seg) for seg in message)
    return normalized or message.extract_plain_text()


@_matcher.handle()
async def _(bot: Bot, event: Event, session: EventSession, message: UniMsg):
    received_time = time.time()
    group_id = session.id2
    if not session.id1 or not group_id:
        return
    if await BanConsole.is_ban(session.id1, group_id):
        return
    _message = _build_mute_message(event, message)
    raw_event_time = getattr(event, "time", None)
    event_time = (
        float(raw_event_time)
        if isinstance(raw_event_time, int | float)
        and not isinstance(raw_event_time, bool)
        else None
    )
    if base_duration := mute_manage.add_message(
        session.id1,
        group_id,
        _message,
        event_time=event_time,
        received_time=received_time,
    ):
        try:
            limiter_key = (session.id1, group_id)
            if _flmt.check(limiter_key):
                _flmt.start_cd(limiter_key)
                penalty_period = current_penalty_period()
                penalty_count = await _get_penalty_store().get_next_count(
                    session.id1,
                    group_id,
                    penalty_period,
                )
                duration = get_mute_duration(base_duration, penalty_count)
                await PlatformUtils.ban_user(bot, session.id1, group_id, duration)
                await _get_penalty_store().record_count(
                    session.id1,
                    group_id,
                    penalty_period,
                    penalty_count,
                )
                await MessageUtils.build_message(
                    _build_mute_notice(penalty_count)
                ).send(at_sender=True)
                mute_manage.reset(session.id1, group_id)
                logger.info(
                    f"检测刷屏 被禁言 {duration} 分钟"
                    f"（本周第 {penalty_count} 次，基础时长 {base_duration} 分钟）",
                    "禁言检查",
                    session=session,
                )
        except Exception as e:
            logger.error("禁言发送错误", "禁言检测", session=session, e=e)
