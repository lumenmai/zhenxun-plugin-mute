"""Exercise plugin code with real NoneBot and isolated host/storage interfaces."""

from enum import Enum
import importlib
import sys
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import nonebot
from nonebot.adapters.onebot.v11 import Adapter
from nonebot.rule import Rule
from pydantic import BaseModel
import pytest


@pytest.fixture(scope="session", autouse=True)
def init_plugin(tmp_path_factory):
    storage = tmp_path_factory.mktemp("mute-storage")
    data_path = storage / "host-data"
    data_path.mkdir()
    nonebot.init(
        driver="~fastapi",
        command_start={""},
        superusers={"10000"},
        localstore_data_dir=storage / "data",
        localstore_cache_dir=storage / "cache",
        localstore_config_dir=storage / "config",
    )
    nonebot.get_driver().register_adapter(Adapter)
    nonebot.load_plugin("nonebot_plugin_alconna")
    nonebot.load_plugin("nonebot_plugin_session")

    names = [
        "zhenxun",
        "zhenxun.configs",
        "zhenxun.configs.config",
        "zhenxun.configs.path_config",
        "zhenxun.configs.utils",
        "zhenxun.models",
        "zhenxun.models.ban_console",
        "zhenxun.services",
        "zhenxun.services.log",
        "zhenxun.utils",
        "zhenxun.utils.enum",
        "zhenxun.utils.message",
        "zhenxun.utils.platform",
        "zhenxun.utils.rules",
        "zhenxun.utils.utils",
    ]
    previous = {name: sys.modules.get(name) for name in names}
    for name in names:
        module = ModuleType(name)
        module.__path__ = []
        sys.modules[name] = module

    class PluginType(str, Enum):
        PARENT = "PARENT"
        DEPENDANT = "DEPENDANT"
        ADMIN = "ADMIN"

    class RegisterConfig(BaseModel):
        key: str
        value: Any
        help: str
        default_value: Any
        type: Any

    class PluginExtraData(BaseModel):
        author: str
        version: str
        plugin_type: PluginType
        menu_type: str = ""
        admin_level: int | None = None
        configs: list[RegisterConfig] | None = None

    class Config:
        @staticmethod
        def get(name):
            return {
                "MUTE_DEFAULT_COUNT": 10,
                "MUTE_DEFAULT_TIME": 7,
                "MUTE_DEFAULT_DURATION": 10,
                "MUTE_LEVEL": 5,
            }

    class BanConsole:
        is_ban = AsyncMock(return_value=False)

    class MessageUtils:
        @staticmethod
        def build_message(content):
            return SimpleNamespace(send=AsyncMock(), finish=AsyncMock())

    class PlatformUtils:
        ban_user = AsyncMock()

    class FreqLimiter:
        def __init__(self, seconds):
            self.seconds = seconds

        def check(self, key):
            return True

        def start_cd(self, key):
            pass

    async def allow():
        return True

    sys.modules["zhenxun.configs.config"].Config = Config
    sys.modules["zhenxun.configs.config"].BotConfig = SimpleNamespace(
        self_nickname="真寻"
    )
    sys.modules["zhenxun.configs.path_config"].DATA_PATH = data_path
    sys.modules["zhenxun.configs.utils"].PluginExtraData = PluginExtraData
    sys.modules["zhenxun.configs.utils"].RegisterConfig = RegisterConfig
    sys.modules["zhenxun.models.ban_console"].BanConsole = BanConsole
    sys.modules["zhenxun.services.log"].logger = MagicMock()
    sys.modules["zhenxun.utils.enum"].PluginType = PluginType
    sys.modules["zhenxun.utils.message"].MessageUtils = MessageUtils
    sys.modules["zhenxun.utils.platform"].PlatformUtils = PlatformUtils
    sys.modules["zhenxun.utils.rules"].admin_check = lambda level: Rule(allow)
    sys.modules["zhenxun.utils.rules"].ensure_group = Rule(allow)
    sys.modules["zhenxun.utils.utils"].FreqLimiter = FreqLimiter

    plugin = nonebot.load_plugin("mute")
    assert plugin is not None, "Mute parent plugin failed to load"
    importlib.import_module("mute.mute_message")
    importlib.import_module("mute.mute_setting")
    yield plugin

    for name, module in previous.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module
