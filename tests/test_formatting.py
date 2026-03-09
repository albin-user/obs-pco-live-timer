"""Tests for formatting.py (build_timer_response, format_seconds, format_end_time)."""

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, PropertyMock, patch

from src.formatting import format_seconds, format_end_time, build_timer_response
from src.models import Service, Item, TimerResult


# ── format_seconds() ─────────────────────────────────────────────────


class TestFormatSeconds:

    def test_zero(self):
        assert format_seconds(0) == "00:00"

    def test_positive_under_minute(self):
        assert format_seconds(45) == "00:45"

    def test_positive_minutes_and_seconds(self):
        assert format_seconds(125) == "02:05"

    def test_positive_exact_minute(self):
        assert format_seconds(300) == "05:00"

    def test_negative_overtime(self):
        assert format_seconds(-90) == "-01:30"

    def test_large_value(self):
        assert format_seconds(3661) == "61:01"

    def test_negative_small(self):
        assert format_seconds(-5) == "-00:05"

    def test_float_truncated(self):
        # float seconds should be truncated to int
        assert format_seconds(61.9) == "01:01"


# ── format_end_time() ────────────────────────────────────────────────


class TestFormatEndTime:

    def test_morning_time(self):
        dt = datetime(2026, 2, 8, 9, 30, tzinfo=timezone.utc)
        result = format_end_time(dt)
        assert "9:30" in result
        assert "AM" in result

    def test_afternoon_time(self):
        dt = datetime(2026, 2, 8, 14, 15, tzinfo=timezone.utc)
        result = format_end_time(dt)
        assert "2:15" in result
        assert "PM" in result

    def test_none_returns_empty(self):
        assert format_end_time(None) == ""


# ── build_timer_response() no data ───────────────────────────────────


def _make_mock_manager(plan=None, tick_result=None):
    """Create a mock PlanManager for build_timer_response tests."""
    import threading
    manager = MagicMock()
    manager._lock = threading.RLock()
    manager.current_plan = plan
    manager.tick.return_value = tick_result
    return manager


class TestBuildTimerResponseNoData:

    def test_no_result_no_plan(self):
        manager = _make_mock_manager(plan=None, tick_result=None)
        resp = build_timer_response(manager)
        assert resp["is_live"] is False
        assert resp["is_finished"] is False
        assert resp["current_item"] is None
        assert resp["next_item"] is None
        assert resp["service_end"] is None
        assert resp["progress"] is None
        assert "Waiting" in resp["message"]

    def test_result_but_no_plan(self):
        result = TimerResult(
            current_item=None, live_countdown=0,
            service_end_time=datetime.now(timezone.utc),
            projected_end_time=datetime.now(timezone.utc),
            service_end_countdown=0, overrun_minutes=0,
            is_live=False, is_finished=False, message="No Service Data"
        )
        manager = _make_mock_manager(plan=None, tick_result=result)
        resp = build_timer_response(manager)
        assert resp["message"] == "No Service Data"


# ── build_timer_response() with full data ────────────────────────────


def _make_full_plan():
    return Service(
        id="100", type_id="st1", series_title="Series",
        plan_title="Sunday", dates="Feb 8",
        start_time=datetime(2026, 2, 8, 10, 0, tzinfo=timezone.utc),
        total_length=3600, service_type_name="WORSHIP",
        items=[
            Item(id="i1", title="Worship", length=1800, sequence=1),
            Item(id="i2", title="Sermon", length=1800, sequence=2, start_time_offset=1800),
        ],
    )


def _make_full_result():
    now = datetime(2026, 2, 8, 10, 15, tzinfo=timezone.utc)
    return TimerResult(
        current_item=Item(id="i1", title="Worship", length=1800, sequence=1,
                          description="Acoustic set", key_name="G"),
        next_item=Item(id="i2", title="Sermon", length=1800, sequence=2,
                       description="Main message"),
        live_countdown=900.0,
        service_end_time=datetime(2026, 2, 8, 11, 0, tzinfo=timezone.utc),
        projected_end_time=datetime(2026, 2, 8, 11, 0, tzinfo=timezone.utc),
        service_end_countdown=2700.0,
        overrun_minutes=0.0,
        is_live=True,
        is_finished=False,
        plan_index=1,
        plan_total=2,
    )


class TestBuildTimerResponseFullData:

    def test_has_current_item(self):
        plan = _make_full_plan()
        result = _make_full_result()
        manager = _make_mock_manager(plan=plan, tick_result=result)
        resp = build_timer_response(manager)
        assert resp["current_item"] is not None
        assert resp["current_item"]["title"] == "Worship"
        assert resp["current_item"]["countdown_formatted"] == "15:00"
        assert resp["current_item"]["is_overtime"] is False

    def test_has_next_item(self):
        plan = _make_full_plan()
        result = _make_full_result()
        manager = _make_mock_manager(plan=plan, tick_result=result)
        resp = build_timer_response(manager)
        assert resp["next_item"]["title"] == "Sermon"

    def test_progress(self):
        plan = _make_full_plan()
        result = _make_full_result()
        manager = _make_mock_manager(plan=plan, tick_result=result)
        resp = build_timer_response(manager)
        assert resp["progress"]["current"] == 1
        assert resp["progress"]["total"] == 2
        assert resp["progress"]["text"] == "1 of 2"

    def test_service_end_on_time(self):
        plan = _make_full_plan()
        result = _make_full_result()
        manager = _make_mock_manager(plan=plan, tick_result=result)
        resp = build_timer_response(manager)
        assert "On time" in resp["service_end"]["status_text"]

    def test_description_includes_key(self):
        plan = _make_full_plan()
        result = _make_full_result()
        manager = _make_mock_manager(plan=plan, tick_result=result)
        resp = build_timer_response(manager)
        assert "Key: G" in resp["current_item"]["description"]

    def test_is_live_true(self):
        plan = _make_full_plan()
        result = _make_full_result()
        manager = _make_mock_manager(plan=plan, tick_result=result)
        resp = build_timer_response(manager)
        assert resp["is_live"] is True

    def test_service_metadata(self):
        plan = _make_full_plan()
        result = _make_full_result()
        manager = _make_mock_manager(plan=plan, tick_result=result)
        resp = build_timer_response(manager)
        assert resp["service_type_name"] == "WORSHIP"
        assert resp["plan_title"] == "Sunday"
        assert resp["series_title"] == "Series"


# ── build_timer_response() overtime ──────────────────────────────────


class TestBuildTimerResponseOvertime:

    def test_current_item_overtime(self):
        plan = _make_full_plan()
        result = _make_full_result()
        result.live_countdown = -90.0
        result.overrun_minutes = 5.0
        result.projected_end_time = datetime(2026, 2, 8, 11, 5, tzinfo=timezone.utc)

        manager = _make_mock_manager(plan=plan, tick_result=result)
        resp = build_timer_response(manager)
        assert resp["current_item"]["is_overtime"] is True
        assert resp["current_item"]["countdown_formatted"] == "-01:30"

    def test_service_end_behind_schedule(self):
        plan = _make_full_plan()
        result = _make_full_result()
        result.overrun_minutes = 5.0
        result.projected_end_time = datetime(2026, 2, 8, 11, 5, tzinfo=timezone.utc)

        manager = _make_mock_manager(plan=plan, tick_result=result)
        resp = build_timer_response(manager)
        assert "behind" in resp["service_end"]["status_text"]
        assert resp["service_end"]["overrun_minutes"] == 5

    def test_service_end_ahead_of_schedule(self):
        plan = _make_full_plan()
        result = _make_full_result()
        result.overrun_minutes = -10.0
        result.projected_end_time = datetime(2026, 2, 8, 10, 50, tzinfo=timezone.utc)

        manager = _make_mock_manager(plan=plan, tick_result=result)
        resp = build_timer_response(manager)
        assert "ahead" in resp["service_end"]["status_text"]
        assert resp["service_end"]["overrun_minutes"] == -10


# ── build_timer_response() no progress ───────────────────────────────


class TestBuildTimerResponseNoProgress:

    def test_zero_plan_total(self):
        plan = _make_full_plan()
        result = _make_full_result()
        result.plan_total = 0
        manager = _make_mock_manager(plan=plan, tick_result=result)
        resp = build_timer_response(manager)
        assert resp["progress"] is None


# ── build_timer_response() song block integration ────────────────


class TestBuildTimerResponseSongBlock:

    def test_song_block_description(self):
        """Song block → title is 'Worship Set', description lists all songs."""
        plan = Service(
            id="100", type_id="st1", series_title="Series",
            plan_title="Sunday", dates="Feb 8",
            start_time=datetime(2026, 2, 8, 10, 0, tzinfo=timezone.utc),
            total_length=3600, service_type_name="WORSHIP",
            items=[
                Item(id="s1", title="Løfte vore hænder", length=0, sequence=1,
                     type="song", description="Lead: John"),
                Item(id="s2", title="What A Beautiful Name", length=0, sequence=2,
                     type="song", description="Lead: Sarah"),
                Item(id="s3", title="Agnus Dei", length=1080, sequence=3,
                     type="song", key_name="D", description="Lead: David"),
            ],
        )
        current = plan.items[2]  # time holder
        result = TimerResult(
            current_item=current,
            next_item=None,
            live_countdown=862.0,
            service_end_time=datetime(2026, 2, 8, 11, 0, tzinfo=timezone.utc),
            projected_end_time=datetime(2026, 2, 8, 11, 0, tzinfo=timezone.utc),
            service_end_countdown=2700.0,
            overrun_minutes=0.0,
            is_live=True, is_finished=False,
            plan_index=1, plan_total=3,
        )
        manager = _make_mock_manager(plan=plan, tick_result=result)
        resp = build_timer_response(manager)

        assert resp["current_item"]["title"] == "Worship Set"
        desc = resp["current_item"]["description"]
        assert "Løfte vore hænder" in desc
        assert "What A Beautiful Name" in desc
        assert "Agnus Dei" in desc
        assert "Lead: John" in desc
        assert "Lead: David" in desc
        assert "Key: D" in desc

    def test_single_song_normal_description(self):
        """A single song (not in a block) keeps normal title/description."""
        plan = Service(
            id="100", type_id="st1", series_title="Series",
            plan_title="Sunday", dates="Feb 8",
            start_time=datetime(2026, 2, 8, 10, 0, tzinfo=timezone.utc),
            total_length=3600, service_type_name="WORSHIP",
            items=[
                Item(id="i1", title="Prayer", length=120, sequence=1),
                Item(id="s1", title="Amazing Grace", length=300, sequence=2,
                     type="song", key_name="G", description="Acoustic"),
                Item(id="i2", title="Sermon", length=1800, sequence=3),
            ],
        )
        current = plan.items[1]
        result = TimerResult(
            current_item=current,
            next_item=plan.items[2],
            live_countdown=200.0,
            service_end_time=datetime(2026, 2, 8, 11, 0, tzinfo=timezone.utc),
            projected_end_time=datetime(2026, 2, 8, 11, 0, tzinfo=timezone.utc),
            service_end_countdown=2700.0,
            overrun_minutes=0.0,
            is_live=True, is_finished=False,
            plan_index=2, plan_total=3,
        )
        manager = _make_mock_manager(plan=plan, tick_result=result)
        resp = build_timer_response(manager)

        assert resp["current_item"]["title"] == "Amazing Grace"
        desc = resp["current_item"]["description"]
        assert "Key: G" in desc
        assert "Acoustic" in desc
