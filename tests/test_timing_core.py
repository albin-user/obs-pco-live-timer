"""Tests for timing_core.calculate_timers()."""

from datetime import datetime, timedelta, timezone

from src.models import Service, Item, TimerResult
from src.timing_core import calculate_timers


def _make_service(start_time=None, total_length=3600, items=None,
                  live_item_id=None, live_start_at=None):
    if start_time is None:
        start_time = datetime(2026, 2, 8, 10, 0, tzinfo=timezone.utc)
    if items is None:
        items = [
            Item(id="i1", title="Worship", length=1800, sequence=1, start_time_offset=0),
            Item(id="i2", title="Sermon", length=1800, sequence=2, start_time_offset=1800),
        ]
    return Service(
        id="100", type_id="393738", series_title="Series",
        plan_title="Sunday", dates="Feb 8", start_time=start_time,
        items=items, total_length=total_length,
        live_item_id=live_item_id, live_start_at=live_start_at,
    )


# ── No service data ──────────────────────────────────────────────


class TestNoData:

    def test_none_service(self):
        result = calculate_timers(None, datetime.now(timezone.utc))
        assert result.is_live is False
        assert result.message == "No Service Data"

    def test_empty_items(self):
        svc = _make_service(items=[], total_length=0)
        now = svc.start_time + timedelta(minutes=5)
        result = calculate_timers(svc, now)
        assert result.is_finished is True


# ── Live item with countdown ─────────────────────────────────────


class TestLiveItem:

    def test_positive_countdown(self):
        svc = _make_service(
            live_item_id="i1",
            live_start_at=datetime(2026, 2, 8, 10, 0, tzinfo=timezone.utc),
        )
        now = svc.start_time + timedelta(minutes=10)
        result = calculate_timers(svc, now)
        assert result.is_live is True
        # 1800s item, 600s elapsed → 1200s remaining
        assert result.live_countdown == 1200.0

    def test_zero_countdown(self):
        svc = _make_service(
            live_item_id="i1",
            live_start_at=datetime(2026, 2, 8, 10, 0, tzinfo=timezone.utc),
        )
        now = svc.start_time + timedelta(seconds=1800)
        result = calculate_timers(svc, now)
        assert result.live_countdown == 0.0

    def test_negative_countdown_overtime(self):
        svc = _make_service(
            live_item_id="i1",
            live_start_at=datetime(2026, 2, 8, 10, 0, tzinfo=timezone.utc),
        )
        now = svc.start_time + timedelta(seconds=1900)
        result = calculate_timers(svc, now)
        assert result.live_countdown < 0

    def test_overrun_calculation(self):
        """When live item has been running longer than scheduled, overrun is positive."""
        svc = _make_service(
            live_item_id="i1",
            live_start_at=datetime(2026, 2, 8, 10, 0, tzinfo=timezone.utc),
        )
        # 35 minutes into a 30-minute item → 5 min overtime for item
        # remaining = 0 (current) + 1800 (next) = 1800s
        # projected_end = now + 1800
        # scheduled_end = start + 3600 = 11:00
        # now = 10:35, projected_end = 11:05 → overrun = 5 min
        now = svc.start_time + timedelta(minutes=35)
        result = calculate_timers(svc, now)
        assert result.overrun_minutes > 0

    def test_ahead_of_schedule(self):
        """If item advanced early, overrun should be negative (ahead)."""
        svc = _make_service(
            live_item_id="i2",
            live_start_at=datetime(2026, 2, 8, 10, 15, tzinfo=timezone.utc),
        )
        # At 10:15, item 2 started (was scheduled for 10:30)
        # remaining = 1800 (full item) since it just started
        # projected_end = 10:15 + 1800 = 10:45
        # scheduled_end = 11:00 → overrun = -15 min (ahead)
        now = datetime(2026, 2, 8, 10, 15, tzinfo=timezone.utc)
        result = calculate_timers(svc, now)
        assert result.overrun_minutes < 0


# ── No live_item_id (fallback to wall-clock) ─────────────────────


class TestWallClockFallback:

    def test_no_live_item_uses_wall_clock(self):
        svc = _make_service()
        now = svc.start_time + timedelta(minutes=5)  # 5 min into item 1
        result = calculate_timers(svc, now)
        assert result.is_live is True
        assert result.current_item is not None
        assert result.current_item.id == "i1"

    def test_wall_clock_second_item(self):
        svc = _make_service()
        now = svc.start_time + timedelta(minutes=35)  # 5 min into item 2
        result = calculate_timers(svc, now)
        assert result.current_item.id == "i2"


# ── Service not started yet ──────────────────────────────────────


class TestNotStarted:

    def test_before_start(self):
        svc = _make_service()
        now = svc.start_time - timedelta(minutes=30)
        result = calculate_timers(svc, now)
        assert result.is_live is False
        assert result.is_finished is False
        assert "Starts in" in result.message

    def test_next_item_set_before_start(self):
        svc = _make_service()
        now = svc.start_time - timedelta(minutes=5)
        result = calculate_timers(svc, now)
        assert result.next_item is not None
        assert result.next_item.id == "i1"

    def test_before_start_empty_items(self):
        svc = _make_service(items=[], total_length=0)
        now = svc.start_time - timedelta(minutes=5)
        result = calculate_timers(svc, now)
        assert result.next_item is None


# ── Service finished ─────────────────────────────────────────────


class TestFinished:

    def test_after_total_length(self):
        svc = _make_service()
        now = svc.start_time + timedelta(seconds=3601)
        result = calculate_timers(svc, now)
        assert result.is_finished is True
        assert result.message == "Service Finished"


# ── Progress tracking ────────────────────────────────────────────


class TestProgress:

    def test_plan_index_and_total(self):
        svc = _make_service(
            live_item_id="i1",
            live_start_at=datetime(2026, 2, 8, 10, 0, tzinfo=timezone.utc),
        )
        now = svc.start_time + timedelta(minutes=5)
        result = calculate_timers(svc, now)
        assert result.plan_index == 1
        assert result.plan_total == 2

    def test_second_item_progress(self):
        svc = _make_service(
            live_item_id="i2",
            live_start_at=datetime(2026, 2, 8, 10, 30, tzinfo=timezone.utc),
        )
        now = datetime(2026, 2, 8, 10, 35, tzinfo=timezone.utc)
        result = calculate_timers(svc, now)
        assert result.plan_index == 2
        assert result.plan_total == 2

    def test_headers_excluded_from_total(self):
        items = [
            Item(id="h1", title="Pre-Service", length=0, sequence=0, type="header"),
            Item(id="i1", title="Worship", length=1800, sequence=1, start_time_offset=0),
            Item(id="i2", title="Sermon", length=1800, sequence=2, start_time_offset=1800),
        ]
        svc = _make_service(
            items=items, total_length=3600,
            live_item_id="i1",
            live_start_at=datetime(2026, 2, 8, 10, 0, tzinfo=timezone.utc),
        )
        now = svc.start_time + timedelta(minutes=5)
        result = calculate_timers(svc, now)
        assert result.plan_total == 2  # headers excluded


# ── Timezone handling ────────────────────────────────────────────


class TestTimezone:

    def test_naive_current_time(self):
        """Naive current_time gets treated as UTC."""
        svc = _make_service()
        naive_now = datetime(2026, 2, 8, 10, 5)  # no tzinfo
        result = calculate_timers(svc, naive_now)
        assert result.current_item is not None
