from types import SimpleNamespace


def _manager(*, count: int = 3, window: int = 10, duration: int = 30):
    from mute._data_source import GroupData, MuteManage

    manager = MuteManage.__new__(MuteManage)
    manager._group_data = {
        "group": GroupData(count=count, time=window, duration=duration)
    }
    return manager


def test_different_images_share_the_same_spam_signature():
    from mute.mute_message import _normalize_raw_segment

    first = SimpleNamespace(type="image", data={"file": "first.jpg"})
    second = SimpleNamespace(type="image", data={"file": "second.jpg"})

    assert _normalize_raw_segment(first) == "[image]"
    assert _normalize_raw_segment(second) == "[image]"


def test_replayed_messages_outside_window_are_not_counted():
    manager = _manager()

    for _ in range(10):
        assert (
            manager.add_message(
                "user",
                "group",
                "same message",
                event_time=100.0,
                received_time=120.0,
            )
            == 0
        )

    assert manager._group_data["group"].message_data == {}


def test_identical_live_messages_still_trigger_mute():
    manager = _manager()

    for timestamp in (100.0, 101.0, 102.0):
        assert (
            manager.add_message(
                "user",
                "group",
                "same message",
                event_time=timestamp,
                received_time=timestamp,
            )
            == 0
        )

    assert (
        manager.add_message(
            "user",
            "group",
            "same message",
            event_time=103.0,
            received_time=103.0,
        )
        == 30
    )


def test_similar_but_different_messages_do_not_share_a_counter():
    manager = _manager(count=1)

    assert (
        manager.add_message(
            "user",
            "group",
            "月消息统计",
            event_time=100.0,
            received_time=100.0,
        )
        == 0
    )
    assert (
        manager.add_message(
            "user",
            "group",
            "请执行月消息统计",
            event_time=101.0,
            received_time=101.0,
        )
        == 0
    )
