from types import SimpleNamespace

from nonebot.exception import FinishedException
import pytest


@pytest.mark.parametrize("content", ["{broken json", '{"group": {"count": 3}}', "[]"])
def test_invalid_configuration_does_not_stop_loading_or_overwrite_file(
    tmp_path, mocker, content
):
    from mute import _data_source as source

    path = tmp_path / "group_mute_data.json"
    path.write_text(content, encoding="utf-8")
    mocker.patch.object(source.MuteManage, "file", path)
    warning = mocker.patch.object(source.logger, "warning")

    manager = source.MuteManage()
    defaults = manager.get_group_data("new-group")

    assert (defaults.count, defaults.time, defaults.duration) == (10, 7, 10)
    assert path.read_text(encoding="utf-8") == content
    warning.assert_called_once()


def test_valid_configuration_is_kept(tmp_path, mocker):
    from mute import _data_source as source

    path = tmp_path / "group_mute_data.json"
    path.write_text(
        '{"group": {"count": 5, "time": 12, "duration": 0}}', encoding="utf-8"
    )
    mocker.patch.object(source.MuteManage, "file", path)

    settings = source.MuteManage().get_group_data("group")

    assert (settings.count, settings.time, settings.duration) == (5, 12, 0)


@pytest.mark.parametrize(("window", "threshold"), [(7, 60), (100, 300)])
def test_stale_counters_are_removed_without_touching_recent_users(window, threshold):
    from mute._data_source import GroupData, MuteManage

    manager = MuteManage.__new__(MuteManage)
    settings = GroupData(count=3, time=window, duration=30)
    settings.message_data = {
        "expired": {"time": -1.0, "count": 2, "message": "old"},
        "boundary": {"time": 0.0, "count": 2, "message": "kept"},
        "active": {"time": threshold - 1.0, "count": 3, "message": "active"},
    }
    manager._group_data = {"group": settings}

    manager.add_message(
        "new", "group", "new", event_time=threshold, received_time=threshold
    )

    assert "expired" not in settings.message_data
    assert settings.message_data["boundary"]["count"] == 2
    assert settings.message_data["active"]["count"] == 3
    assert settings.message_data["new"]["count"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("time_value", "count_value", "duration_value", "expected_message"),
    [
        (0, None, None, "检测时长必须大于 0 秒"),
        (-1, None, None, "检测时长必须大于 0 秒"),
        (None, 0, None, "检测次数必须大于 0 次"),
        (None, -1, None, "检测次数必须大于 0 次"),
        (None, None, -1, "禁言时长不能小于 0 分钟"),
        (20, 0, 5, "检测次数必须大于 0 次"),
    ],
)
async def test_invalid_settings_leave_entire_configuration_unchanged(
    mocker, time_value, count_value, duration_value, expected_message
):
    from mute import mute_setting as plugin

    settings = SimpleNamespace(time=7, count=10, duration=10)
    mocker.patch.object(plugin.mute_manage, "get_group_data", return_value=settings)
    save = mocker.patch.object(plugin.mute_manage, "save_data")
    response = SimpleNamespace(finish=mocker.AsyncMock(side_effect=FinishedException))
    build = mocker.patch.object(
        plugin.MessageUtils, "build_message", return_value=response
    )
    option = lambda value: SimpleNamespace(available=value is not None, result=value)

    with pytest.raises(FinishedException):
        await plugin._(
            SimpleNamespace(id1="user", id2="group"),
            mocker.MagicMock(),
            option(time_value),
            option(count_value),
            option(duration_value),
        )

    assert (settings.time, settings.count, settings.duration) == (7, 10, 10)
    save.assert_not_called()
    build.assert_called_once_with(expected_message)


@pytest.mark.asyncio
async def test_zero_duration_still_disables_detection(mocker):
    from mute import mute_setting as plugin

    settings = SimpleNamespace(time=7, count=10, duration=10)
    mocker.patch.object(plugin.mute_manage, "get_group_data", return_value=settings)
    save = mocker.patch.object(plugin.mute_manage, "save_data")
    response = SimpleNamespace(send=mocker.AsyncMock())
    mocker.patch.object(plugin.MessageUtils, "build_message", return_value=response)
    absent = SimpleNamespace(available=False, result=None)

    await plugin._(
        SimpleNamespace(id1="user", id2="group"),
        mocker.MagicMock(),
        absent,
        absent,
        SimpleNamespace(available=True, result=0),
    )

    assert settings.duration == 0
    save.assert_called_once()
