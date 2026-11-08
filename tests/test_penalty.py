from datetime import datetime
from zoneinfo import ZoneInfo

import pytest


@pytest.mark.parametrize(
    ("penalty_level", "duration"),
    [
        (1, 10),
        (2, 30),
        (3, 60),
        (4, 360),
        (5, 720),
        (6, 1440),
        (7, 2880),
        (8, 5760),
        (9, 11520),
        (10, 23040),
        (11, 43200),
        (12, 43200),
    ],
)
def test_mute_duration_escalates_from_group_base_duration(
    penalty_level,
    duration,
):
    from mute.penalty import get_mute_duration

    assert get_mute_duration(10, penalty_level) == duration


def test_mute_duration_respects_platform_maximum():
    from mute.penalty import (
        MAX_MUTE_DURATION_MINUTES,
        get_mute_duration,
    )

    assert get_mute_duration(2000, 4) == MAX_MUTE_DURATION_MINUTES


def test_mute_duration_handles_extreme_penalty_level():
    from mute.penalty import (
        MAX_MUTE_DURATION_MINUTES,
        get_mute_duration,
    )

    assert get_mute_duration(10, 1_000_000) == MAX_MUTE_DURATION_MINUTES


@pytest.mark.asyncio
async def test_penalty_count_persists_and_resets_next_friday(tmp_path):
    from mute.penalty import MutePenaltyStore

    database_path = tmp_path / "mute_penalties.sqlite3"
    store = MutePenaltyStore(database_path)

    assert await store.get_next_count("10001", "20001", "2026-08-14") == 1
    await store.record_count("10001", "20001", "2026-08-14", 1)
    assert await store.get_next_count("10001", "20001", "2026-08-14") == 2
    await store.record_count("10001", "20001", "2026-08-14", 4)

    reloaded_store = MutePenaltyStore(database_path)
    assert await reloaded_store.get_next_count("10001", "20001", "2026-08-14") == 5
    assert await reloaded_store.get_next_count("10001", "20002", "2026-08-14") == 1
    assert await reloaded_store.get_next_count("10001", "20001", "2026-08-21") == 1


@pytest.mark.asyncio
async def test_existing_daily_key_is_kept_during_current_week(tmp_path):
    from mute.penalty import MutePenaltyStore

    store = MutePenaltyStore(tmp_path / "mute_penalties.sqlite3")
    await store.record_count("10001", "20001", "2026-08-16", 2)

    assert await store.get_next_count("10001", "20001", "2026-08-14") == 3


def test_penalty_period_resets_at_friday_midnight_in_shanghai():
    from mute.penalty import current_penalty_period

    utc = ZoneInfo("UTC")
    assert current_penalty_period(datetime(2026, 8, 20, 15, 59, tzinfo=utc)) == (
        "2026-08-14"
    )
    assert current_penalty_period(datetime(2026, 8, 20, 16, 0, tzinfo=utc)) == (
        "2026-08-21"
    )


@pytest.mark.parametrize(
    ("penalty_count", "expected"),
    [
        (1, "检测到恶意刷屏，七宫要把你关进小黑屋！"),
        (
            2,
            "检测到恶意刷屏，七宫要把你关进小黑屋！"
            "这周已经是第2次啦，希望你好好反省！",
        ),
        (
            5,
            "检测到恶意刷屏，七宫要把你关进小黑屋！"
            "这周已经是第5次啦，希望你好好反省！",
        ),
    ],
)
def test_mute_notice_uses_bot_name_and_only_shows_count_after_first(
    mocker,
    penalty_count,
    expected,
):
    from mute import mute_message

    mocker.patch.object(mute_message.BotConfig, "self_nickname", "七宫")

    assert mute_message._build_mute_notice(penalty_count) == expected


@pytest.mark.asyncio
async def test_mute_handler_uses_user_and_group_cooldown_key(mocker):
    from mute import mute_message

    bot = mocker.MagicMock()
    event = mocker.MagicMock()
    session = mocker.MagicMock()
    session.id1 = "10001"
    session.id2 = "20001"
    message = mocker.MagicMock()

    mocker.patch.object(
        mute_message.BanConsole,
        "is_ban",
        new=mocker.AsyncMock(return_value=False),
    )
    mocker.patch.object(mute_message, "_build_mute_message", return_value="spam")
    mocker.patch.object(mute_message.mute_manage, "add_message", return_value=10)
    reset = mocker.patch.object(mute_message.mute_manage, "reset")
    limiter = mocker.MagicMock()
    limiter.check.return_value = True
    mocker.patch.object(mute_message, "_flmt", limiter)

    store = mocker.MagicMock()
    store.get_next_count = mocker.AsyncMock(return_value=2)
    store.record_count = mocker.AsyncMock()
    mocker.patch.object(mute_message, "_get_penalty_store", return_value=store)
    mocker.patch.object(
        mute_message,
        "current_penalty_period",
        return_value="2026-08-07",
    )
    ban_user = mocker.patch.object(
        mute_message.PlatformUtils,
        "ban_user",
        new=mocker.AsyncMock(),
    )
    built_message = mocker.MagicMock()
    built_message.send = mocker.AsyncMock()
    mocker.patch.object(
        mute_message.MessageUtils,
        "build_message",
        return_value=built_message,
    )

    await mute_message._(bot, event, session, message)

    limiter.check.assert_called_once_with(("10001", "20001"))
    limiter.start_cd.assert_called_once_with(("10001", "20001"))
    ban_user.assert_awaited_once_with(bot, "10001", "20001", 30)
    store.record_count.assert_awaited_once_with(
        "10001",
        "20001",
        "2026-08-07",
        2,
    )
    reset.assert_called_once_with("10001", "20001")


@pytest.mark.asyncio
async def test_failed_mute_is_not_recorded_as_penalty(mocker):
    from mute import mute_message

    bot = mocker.MagicMock()
    session = mocker.MagicMock()
    session.id1 = "10001"
    session.id2 = "20001"

    mocker.patch.object(
        mute_message.BanConsole,
        "is_ban",
        new=mocker.AsyncMock(return_value=False),
    )
    mocker.patch.object(mute_message, "_build_mute_message", return_value="spam")
    mocker.patch.object(mute_message.mute_manage, "add_message", return_value=10)
    limiter = mocker.MagicMock()
    limiter.check.return_value = True
    mocker.patch.object(mute_message, "_flmt", limiter)

    store = mocker.MagicMock()
    store.get_next_count = mocker.AsyncMock(return_value=1)
    store.record_count = mocker.AsyncMock()
    mocker.patch.object(mute_message, "_get_penalty_store", return_value=store)
    mocker.patch.object(
        mute_message,
        "current_penalty_period",
        return_value="2026-08-07",
    )
    mocker.patch.object(
        mute_message.PlatformUtils,
        "ban_user",
        new=mocker.AsyncMock(side_effect=RuntimeError("ban failed")),
    )
    log_error = mocker.patch.object(mute_message.logger, "error")

    await mute_message._(
        bot,
        mocker.MagicMock(),
        session,
        mocker.MagicMock(),
    )

    store.record_count.assert_not_awaited()
    log_error.assert_called_once()
