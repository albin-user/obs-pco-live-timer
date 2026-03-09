"""Tests for PlanManager state machine (IDLE/SCANNING/TRACKING).

All tests use unittest.mock to avoid real API calls.
"""

import sys
import os
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, PropertyMock

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.manager import PlanManager, SyncState
from src.models import Service, Item


# ── Helpers ─────────────────────────────────────────────────────────────────


def _make_service(plan_id="100", type_id="393738", title="Sunday Service",
                  start_time=None, total_length=3600, live_item_id=None,
                  live_start_at=None):
    """Create a Service for testing."""
    if start_time is None:
        start_time = datetime(2026, 2, 8, 10, 0, tzinfo=timezone.utc)
    return Service(
        id=plan_id,
        type_id=type_id,
        series_title="Test Series",
        plan_title=title,
        dates="8 February 2026",
        start_time=start_time,
        total_length=total_length,
        items=[
            Item(id="item1", title="Worship", length=1800, sequence=1),
            Item(id="item2", title="Sermon", length=1800, sequence=2,
                 start_time_offset=1800),
        ],
        live_item_id=live_item_id,
        live_start_at=live_start_at,
    )


def _make_live_response(cit_id, item_id, live_start_at_str, item_length=300):
    """Build a /live?include=current_item_time,items response."""
    return {
        "data": {
            "type": "Live",
            "id": "84849612",
            "attributes": {},
            "relationships": {
                "current_item_time": {
                    "data": {"type": "ItemTime", "id": cit_id},
                },
            },
        },
        "included": [
            {
                "type": "ItemTime",
                "id": cit_id,
                "attributes": {"live_start_at": live_start_at_str},
                "relationships": {
                    "item": {"data": {"type": "Item", "id": item_id}},
                },
            },
            {
                "type": "Item",
                "id": item_id,
                "attributes": {
                    "title": "Test Item",
                    "length": item_length,
                    "service_position": "during",
                    "sequence": 1,
                },
            },
        ],
    }


def _make_not_live_response():
    """Build a /live response with no current_item_time."""
    return {
        "data": {
            "type": "Live",
            "id": "84849612",
            "attributes": {},
            "relationships": {
                "current_item_time": {"data": None},
            },
        },
        "included": [],
    }


def _make_manager(candidates=None):
    """Create a PlanManager with mocked client and no background thread."""
    mock_client = MagicMock()
    mock_client.get_service_types.return_value = []
    mock_client.get_next_plans_for_types.return_value = candidates or []
    mock_client.populate_plan_details.return_value = None

    manager = PlanManager(mock_client, ["393738"], start_thread=False)

    if candidates:
        manager._candidates = candidates
        manager._last_rescan = 0  # force rescan to think it already ran

    return manager


# ── 1. Initial state ───────────────────────────────────────────────────────


class TestInitialState:

    def test_starts_in_idle(self):
        manager = _make_manager()
        assert manager.state == SyncState.IDLE

    def test_no_current_plan(self):
        manager = _make_manager()
        assert manager.current_plan is None

    def test_tracked_plan_key_none(self):
        manager = _make_manager()
        assert manager._tracked_plan_key is None


# ── 2. IDLE → SCANNING transition ────────────────────────────────────────


class TestIdleToScanning:

    def test_idle_refreshes_candidates(self):
        """IDLE rescan fetches new candidates."""
        svc = _make_service()
        manager = _make_manager()
        manager.client.get_next_plans_for_types.return_value = [svc]
        # No live response
        manager.client.get_live_status.return_value = _make_not_live_response()

        now = datetime.now(timezone.utc)
        manager._perform_sync(now)

        manager.client.get_next_plans_for_types.assert_called()

    def test_idle_transitions_to_scanning_with_candidates(self):
        """When candidates found, transitions to SCANNING then back to IDLE (nothing live)."""
        svc = _make_service()
        manager = _make_manager()
        manager.client.get_next_plans_for_types.return_value = [svc]
        manager.client.get_live_status.return_value = _make_not_live_response()

        now = datetime.now(timezone.utc)
        manager._perform_sync(now)

        # After scanning finds nothing live, should go back to IDLE
        assert manager.state == SyncState.IDLE


# ── 3. SCANNING → TRACKING transition ───────────────────────────────────


class TestScanningToTracking:

    def test_scan_finds_live_transitions_to_tracking(self):
        """When a live plan is found, transitions to TRACKING."""
        svc = _make_service()
        manager = _make_manager(candidates=[svc])
        manager._state = SyncState.SCANNING

        live_resp = _make_live_response(
            "cit1", "item1", "2026-02-08T10:30:00Z"
        )
        manager.client.get_live_status.return_value = live_resp

        now = datetime.now(timezone.utc)
        manager._sync_scanning(now)

        assert manager.state == SyncState.TRACKING
        assert manager._tracked_plan_key == (svc.type_id, svc.id)
        assert manager.current_plan is not None

    def test_scan_picks_most_recent_live_start_at(self):
        """When two plans are live, picks the one with newer live_start_at."""
        old_svc = _make_service(plan_id="100", type_id="393738", title="Old Plan")
        new_svc = _make_service(plan_id="200", type_id="772177", title="New Plan")

        manager = _make_manager(candidates=[old_svc, new_svc])
        manager._state = SyncState.SCANNING

        old_live = _make_live_response("cit1", "item1", "2026-02-08T10:30:00Z")
        new_live = _make_live_response("cit2", "item1", "2026-02-08T15:45:00Z")

        def get_live_side_effect(type_id, plan_id):
            if plan_id == "100":
                return old_live
            elif plan_id == "200":
                return new_live
            return _make_not_live_response()

        manager.client.get_live_status.side_effect = get_live_side_effect

        now = datetime.now(timezone.utc)
        manager._sync_scanning(now)

        assert manager.state == SyncState.TRACKING
        assert manager._tracked_plan_key == ("772177", "200")

    def test_scan_nothing_live_goes_to_idle(self):
        """When no plan is live, transitions to IDLE."""
        svc = _make_service()
        manager = _make_manager(candidates=[svc])
        manager._state = SyncState.SCANNING

        manager.client.get_live_status.return_value = _make_not_live_response()

        now = datetime.now(timezone.utc)
        manager._sync_scanning(now)

        assert manager.state == SyncState.IDLE

    def test_scan_populates_items_for_winner(self):
        """populate_plan_details is called for the live plan."""
        svc = _make_service()
        manager = _make_manager(candidates=[svc])
        manager._state = SyncState.SCANNING

        live_resp = _make_live_response("cit1", "item1", "2026-02-08T10:30:00Z")
        manager.client.get_live_status.return_value = live_resp

        now = datetime.now(timezone.utc)
        manager._sync_scanning(now)

        manager.client.populate_plan_details.assert_called_once()


# ── 4. TRACKING behavior ────────────────────────────────────────────────


class TestTracking:

    def _setup_tracking(self, manager, svc, live_start="2026-02-08T10:30:00Z"):
        """Put manager into TRACKING state for the given service."""
        manager._state = SyncState.TRACKING
        manager._tracked_plan_key = (svc.type_id, svc.id)
        manager.current_plan = svc
        manager._last_full_scan = 9999999999  # prevent full scan

    def test_tracking_polls_only_tracked_plan(self):
        """In TRACKING, only the tracked plan is polled."""
        svc = _make_service()
        manager = _make_manager(candidates=[svc])
        self._setup_tracking(manager, svc)

        live_resp = _make_live_response("cit1", "item1", "2026-02-08T10:30:00Z")
        manager.client.get_live_status.return_value = live_resp

        now = datetime.now(timezone.utc)
        manager._sync_tracking(now)

        manager.client.get_live_status.assert_called_once_with(svc.type_id, svc.id)

    def test_tracking_stays_when_still_live(self):
        """TRACKING stays in TRACKING when plan is still live."""
        svc = _make_service()
        manager = _make_manager(candidates=[svc])
        self._setup_tracking(manager, svc)

        live_resp = _make_live_response("cit1", "item1", "2026-02-08T10:30:00Z")
        manager.client.get_live_status.return_value = live_resp

        now = datetime.now(timezone.utc)
        manager._sync_tracking(now)

        assert manager.state == SyncState.TRACKING

    def test_tracking_goes_to_scanning_when_not_live(self):
        """TRACKING → SCANNING when tracked plan is no longer live."""
        svc = _make_service()
        other_svc = _make_service(plan_id="200", type_id="772177")
        manager = _make_manager(candidates=[svc, other_svc])
        self._setup_tracking(manager, svc)

        # Tracked plan returns not-live
        manager.client.get_live_status.return_value = _make_not_live_response()

        now = datetime.now(timezone.utc)
        manager._sync_tracking(now)

        # Should transition to SCANNING (or IDLE if scanning finds nothing)
        assert manager.state in (SyncState.SCANNING, SyncState.IDLE)

    def test_tracking_periodic_full_scan_switches_plan(self):
        """Periodic full scan detects a newer live plan and switches."""
        old_svc = _make_service(plan_id="100", type_id="393738", title="Old")
        new_svc = _make_service(plan_id="200", type_id="772177", title="New")

        manager = _make_manager(candidates=[old_svc, new_svc])
        self._setup_tracking(manager, old_svc, "2026-02-08T10:30:00Z")
        # Force full scan to trigger
        manager._last_full_scan = 0

        old_live = _make_live_response("cit1", "item1", "2026-02-08T10:30:00Z")
        new_live = _make_live_response("cit2", "item1", "2026-02-08T15:45:00Z")

        call_count = 0

        def get_live_side_effect(type_id, plan_id):
            nonlocal call_count
            call_count += 1
            # First call: tracked plan (still live)
            if call_count == 1:
                return old_live
            # Subsequent calls during full scan
            if plan_id == "100":
                return old_live
            elif plan_id == "200":
                return new_live
            return _make_not_live_response()

        manager.client.get_live_status.side_effect = get_live_side_effect

        now = datetime.now(timezone.utc)
        manager._sync_tracking(now)

        # Should have switched to the newer plan
        assert manager._tracked_plan_key == ("772177", "200")


# ── 5. _pick_nearest_upcoming ────────────────────────────────────────────


class TestPickNearestUpcoming:

    def test_picks_closest_future(self):
        """Picks the future plan closest to now."""
        now = datetime(2026, 2, 8, 11, 0, tzinfo=timezone.utc)
        far = _make_service(plan_id="1", title="Far",
                            start_time=now + timedelta(hours=5))
        close = _make_service(plan_id="2", title="Close",
                              start_time=now + timedelta(minutes=30))

        manager = _make_manager(candidates=[far, close])
        result = manager._pick_nearest_upcoming(now)

        assert result.plan_title == "Close"

    def test_prefers_running_over_future(self):
        """A running service (closer to end) beats a future one."""
        now = datetime(2026, 2, 8, 11, 30, tzinfo=timezone.utc)
        running = _make_service(
            plan_id="1", title="Running",
            start_time=now - timedelta(hours=1),
            total_length=7200,  # ends in 1 hour
        )
        future = _make_service(
            plan_id="2", title="Future",
            start_time=now + timedelta(hours=2),
        )

        manager = _make_manager(candidates=[running, future])
        result = manager._pick_nearest_upcoming(now)

        assert result.plan_title == "Running"

    def test_empty_candidates_returns_none(self):
        manager = _make_manager(candidates=[])
        manager._candidates = []
        result = manager._pick_nearest_upcoming(datetime.now(timezone.utc))
        assert result is None


# ── 6. _get_dynamic_interval ─────────────────────────────────────────────


class TestDynamicInterval:

    def test_tracking_interval(self):
        manager = _make_manager()
        manager._state = SyncState.TRACKING
        assert manager._get_dynamic_interval() == PlanManager.TRACKING_POLL_INTERVAL

    def test_scanning_interval(self):
        manager = _make_manager()
        manager._state = SyncState.SCANNING
        assert manager._get_dynamic_interval() == 1

    def test_idle_interval(self):
        manager = _make_manager()
        manager._state = SyncState.IDLE
        assert manager._get_dynamic_interval() == PlanManager.IDLE_RESCAN_INTERVAL


# ── 7. populate_plan_details ─────────────────────────────────────────────


class TestPopulatePlanDetails:

    def test_per_page_is_3(self):
        """get_upcoming_services uses per_page=3."""
        from src.pco_client import PCOClient
        client = PCOClient("app", "secret")
        with patch.object(client, '_get', return_value={"data": [], "included": []}) as mock_get:
            client.get_upcoming_services("393738")
        call_args = mock_get.call_args
        assert call_args[1]["params"]["per_page"] == 3

    def test_populate_skips_if_items_present(self):
        """populate_plan_details does nothing when items already populated."""
        from src.pco_client import PCOClient
        client = PCOClient("app", "secret")
        svc = _make_service()  # already has items
        with patch.object(client, '_populate_items') as mock_pop:
            client.populate_plan_details(svc)
        mock_pop.assert_not_called()

    def test_populate_fetches_when_no_items(self):
        """populate_plan_details fetches items when empty."""
        from src.pco_client import PCOClient
        client = PCOClient("app", "secret")
        svc = _make_service()
        svc.items = []  # clear items
        with patch.object(client, '_populate_items') as mock_pop:
            client.populate_plan_details(svc)
        mock_pop.assert_called_once_with(svc)
