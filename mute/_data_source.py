# Source: HibiKier / zhenxun-org/zhenxun_bot_plugins (AGPL-3.0).
# Modified on 2026-11-08; see CHANGELOG.md.

import time

from pydantic import BaseModel, Field
import ujson as json

from zhenxun.configs.config import Config
from zhenxun.configs.path_config import DATA_PATH
from zhenxun.services.log import logger

base_config = Config.get("mute_setting")


class GroupData(BaseModel):
    count: int
    """次数"""
    time: int
    """检测时长"""
    duration: int
    """禁言时长"""
    message_data: dict = Field(default_factory=dict)
    """消息存储"""


class MuteManage:
    file = DATA_PATH / "group_mute_data.json"

    def __init__(self) -> None:
        self._group_data: dict[str, GroupData] = {}
        if self.file.exists():
            try:
                with self.file.open(encoding="utf-8") as f:
                    _data = json.load(f)
                for gid, group_data in _data.items():
                    self._group_data[gid] = GroupData(
                        count=group_data["count"],
                        time=group_data["time"],
                        duration=group_data["duration"],
                    )
            except Exception as e:
                logger.warning(f"加载禁言配置失败，已使用默认配置: {e}", "mute")

    def get_group_data(self, group_id: str) -> GroupData:
        """获取群组数据

        参数:
            group_id: 群组id

        返回:
            GroupData: GroupData
        """
        if group_id not in self._group_data:
            self._group_data[group_id] = GroupData(
                count=base_config.get("MUTE_DEFAULT_COUNT", 10) or 10,
                time=base_config.get("MUTE_DEFAULT_TIME", 7) or 7,
                duration=base_config.get("MUTE_DEFAULT_DURATION", 10) or 10,
            )
        return self._group_data[group_id]

    def reset(self, user_id: str, group_id: str):
        """重置用户检查次数

        参数:
            user_id: 用户id
            group_id: 群组id
        """
        if group_data := self._group_data.get(group_id):
            if user_id in group_data.message_data:
                group_data.message_data[user_id]["count"] = 0

    def save_data(self):
        """保存数据"""
        data = {}
        for gid in self._group_data:
            data[gid] = {
                "count": self._group_data[gid].count,
                "time": self._group_data[gid].time,
                "duration": self._group_data[gid].duration,
            }
        with self.file.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def add_message(
        self,
        user_id: str,
        group_id: str,
        message: str,
        *,
        event_time: float | None = None,
        received_time: float | None = None,
    ) -> int:
        """添加消息

        参数:
            user_id: 用户id
            group_id: 群组id
            message: 消息内容
            event_time: 平台事件携带的原始时间戳
            received_time: Bot 收到事件的时间戳

        返回:
            int: 禁言时长
        """
        if group_id not in self._group_data:
            self._group_data[group_id] = GroupData(
                count=base_config.get("MUTE_DEFAULT_COUNT"),
                time=base_config.get("MUTE_DEFAULT_TIME"),
                duration=base_config.get("MUTE_DEFAULT_DURATION"),
            )
        group_data = self._group_data[group_id]
        if group_data.duration == 0:
            return 0
        received_at = received_time if received_time is not None else time.time()
        occurred_at = event_time if event_time is not None else received_at

        # OneBot 会在 Bot 重连后补发断线期间积压的事件。此时这些消息虽然在
        # 同一瞬间被处理，但原始刷屏窗口早已结束，不应再触发延迟禁言。
        if received_at - occurred_at > group_data.time:
            return 0

        message_data = group_data.message_data
        stale_threshold = max(group_data.time * 3, 60)
        stale_users = [
            uid
            for uid, data in message_data.items()
            if received_at - data["time"] > stale_threshold
        ]
        for uid in stale_users:
            del message_data[uid]

        if not message_data.get(user_id):
            message_data[user_id] = {
                "time": occurred_at,
                "count": 1,
                "message": message,
            }
        else:
            previous = message_data[user_id]
            window_expired = (
                occurred_at < previous["time"]
                or occurred_at - previous["time"] > group_data.time
            )
            if not window_expired and message == previous["message"]:
                message_data[user_id]["count"] += 1
            else:
                message_data[user_id]["time"] = occurred_at
                message_data[user_id]["count"] = 1
            message_data[user_id]["message"] = message
            if (
                message_data[user_id]["count"] > group_data.count
                and occurred_at - message_data[user_id]["time"] <= group_data.time
            ):
                return group_data.duration
        return 0


mute_manage = MuteManage()
