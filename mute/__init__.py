# Source: HibiKier / zhenxun-org/zhenxun_bot_plugins (AGPL-3.0).
# Modified on 2026-11-08; see CHANGELOG.md.

from pathlib import Path

import nonebot
from nonebot.plugin import PluginMetadata

from zhenxun.configs.utils import PluginExtraData
from zhenxun.utils.enum import PluginType

__plugin_meta__ = PluginMetadata(
    name="刷屏禁言检测",
    description="",
    usage="",
    extra=PluginExtraData(
        author="HibiKier",
        version="0.2.0",
        plugin_type=PluginType.PARENT,
    ).dict(),
)

nonebot.load_plugins(str(Path(__file__).parent.resolve()))
