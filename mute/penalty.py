# Source: HibiKier / zhenxun-org/zhenxun_bot_plugins (AGPL-3.0).
# Modified on 2026-11-08; see CHANGELOG.md.

import asyncio
from contextlib import closing
from datetime import date, datetime, timedelta
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
MAX_MUTE_DURATION_MINUTES = 30 * 24 * 60
_DURATION_MULTIPLIERS = (1, 3, 6, 36)


class MutePenaltyStore:
    """持久化每个用户在每个群当前周期的刷屏处罚次数。

    SQLite 沿用旧字段名，避免迁移现有运行数据。
    """

    def __init__(self, database_path: Path):
        self.database_path = database_path
        self._lock = asyncio.Lock()

    async def get_next_count(
        self,
        user_id: str,
        group_id: str,
        period_key: str,
    ) -> int:
        async with self._lock:
            return await asyncio.to_thread(
                self._get_next_count_sync,
                user_id,
                group_id,
                period_key,
            )

    async def record_count(
        self,
        user_id: str,
        group_id: str,
        period_key: str,
        penalty_count: int,
    ) -> None:
        async with self._lock:
            await asyncio.to_thread(
                self._record_count_sync,
                user_id,
                group_id,
                period_key,
                penalty_count,
            )

    def _connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS penalty_state (
                user_id TEXT NOT NULL,
                group_id TEXT NOT NULL,
                penalty_day TEXT NOT NULL,
                penalty_level INTEGER NOT NULL,
                PRIMARY KEY (user_id, group_id)
            )
            """
        )
        connection.commit()
        return connection

    def _get_next_count_sync(
        self,
        user_id: str,
        group_id: str,
        period_key: str,
    ) -> int:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT penalty_day, penalty_level
                FROM penalty_state
                WHERE user_id = ? AND group_id = ?
                """,
                (user_id, group_id),
            ).fetchone()
        current_count = 0
        if row:
            period_start = date.fromisoformat(period_key)
            stored_date = date.fromisoformat(row[0])
            if period_start <= stored_date < period_start + timedelta(days=7):
                current_count = int(row[1])
        return current_count + 1

    def _record_count_sync(
        self,
        user_id: str,
        group_id: str,
        period_key: str,
        penalty_count: int,
    ) -> None:
        normalized_count = max(penalty_count, 1)
        with closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO penalty_state (
                    user_id, group_id, penalty_day, penalty_level
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, group_id) DO UPDATE SET
                    penalty_day = excluded.penalty_day,
                    penalty_level = excluded.penalty_level
                """,
                (user_id, group_id, period_key, normalized_count),
            )
            connection.commit()


def current_penalty_period(now: datetime | None = None) -> str:
    """获取北京时间最近一个周五的日期，作为当前处罚周期标识。"""
    current = now.astimezone(SHANGHAI_TZ) if now else datetime.now(SHANGHAI_TZ)
    days_since_friday = (current.weekday() - 4) % 7
    return (current.date() - timedelta(days=days_since_friday)).isoformat()


def get_mute_duration(base_duration: int, penalty_level: int) -> int:
    base_duration = max(int(base_duration), 0)
    penalty_level = max(int(penalty_level), 1)
    if penalty_level <= len(_DURATION_MULTIPLIERS):
        duration = base_duration * _DURATION_MULTIPLIERS[penalty_level - 1]
        return min(duration, MAX_MUTE_DURATION_MINUTES)

    duration = base_duration * _DURATION_MULTIPLIERS[-1]
    if duration <= 0:
        return 0
    if duration >= MAX_MUTE_DURATION_MINUTES:
        return MAX_MUTE_DURATION_MINUTES

    extra_doublings = penalty_level - len(_DURATION_MULTIPLIERS)
    max_multiplier = MAX_MUTE_DURATION_MINUTES // duration
    if extra_doublings >= max_multiplier.bit_length():
        return MAX_MUTE_DURATION_MINUTES
    return min(
        duration * (1 << extra_doublings),
        MAX_MUTE_DURATION_MINUTES,
    )
