import logging
import os
import time
import threading
from datetime import datetime, timezone, timedelta
from enum import Enum, auto
from typing import List, Optional, Dict
from .pco_client import PCOClient
from .models import Service, TimerResult, TeamMember
from .team_members import fetch_and_cache_team
from .timing_core import calculate_timers
import dateutil.parser

logger = logging.getLogger(__name__)


class SyncState(Enum):
    IDLE = auto()
    SCANNING = auto()
    TRACKING = auto()


class PlanManager:
    # Intervals (seconds)
    IDLE_RESCAN_INTERVAL = 30
    TRACKING_POLL_INTERVAL = 3
    TRACKING_FULL_SCAN_INTERVAL = 60

    def __init__(self, client: PCOClient, target_service_type_ids: List[str],
                 start_thread: bool = True, team_enabled: bool = True,
                 team_cache_dir: str = "", team_slots: list = None,
                 team_placeholder_photo: str = ""):
        self.client = client
        self.target_ids = target_service_type_ids

        self.current_plan: Optional[Service] = None
        self.last_poll_time = 0
        self.last_error: Optional[str] = None

        # State machine
        self._state = SyncState.IDLE
        self._tracked_plan_key: Optional[tuple] = None  # (type_id, plan_id)
        self._last_full_scan: float = 0
        self._last_rescan: float = 0
        self._candidates: List[Service] = []

        # Cache for service type names: {type_id: name}
        self._service_type_names: Dict[str, str] = {}

        # Team members
        self._team_members: List[TeamMember] = []
        self._team_plan_key: Optional[tuple] = None
        self._team_enabled = team_enabled
        self._team_cache_dir = team_cache_dir
        self._team_slots: List[str] = team_slots or []
        self._team_placeholder_photo: str = team_placeholder_photo
        if team_enabled and team_cache_dir:
            os.makedirs(team_cache_dir, exist_ok=True)

        # USE RLock (Recursive Lock) to prevent deadlocks
        self._lock = threading.RLock()

        self._stop_event = threading.Event()
        self._sync_thread = None

        # Fetch service type names on init
        self._fetch_service_type_names()

        if start_thread:
            self._sync_thread = threading.Thread(target=self._background_sync_loop, daemon=True)
            self._sync_thread.start()
            logger.info("Background sync thread started for IDs: %s", target_service_type_ids)

    @property
    def state(self) -> SyncState:
        with self._lock:
            return self._state

    def tick(self) -> Optional[TimerResult]:
        """
        FAST LOCAL TICK.
        Lightning fast, thread-safe access to cached plan data.
        """
        now = datetime.now(timezone.utc)

        with self._lock:
            if not self.current_plan:
                return None
            return calculate_timers(self.current_plan, now)

    def sync(self) -> Optional[TimerResult]:
        """
        MANUAL SYNC (Blocks until finished).
        Useful for testing or forcing an update.
        """
        now = datetime.now(timezone.utc)
        self._perform_sync(now)
        return self.tick()

    def _background_sync_loop(self):
        """
        Separates network latency from UI responsiveness.
        """
        while not self._stop_event.is_set():
            try:
                now = datetime.now(timezone.utc)
                self._perform_sync(now)

                # Fetch interval safely
                with self._lock:
                    interval = self._get_dynamic_interval()

                # Sleep in small chunks to permit rapid shutdown
                for _ in range(int(interval * 10)):
                    if self._stop_event.is_set(): break
                    time.sleep(0.1)

            except Exception as e:
                logger.error("Background sync error: %s", e)
                time.sleep(5)

    def _refresh_candidates(self):
        """Fetch lightweight candidate plans from all service types."""
        candidates = self.client.get_next_plans_for_types(self.target_ids)
        for plan in candidates:
            plan.service_type_name = self._service_type_names.get(plan.type_id, "Unknown")
        with self._lock:
            self._candidates = candidates
            self._last_rescan = time.monotonic()

    @staticmethod
    def _extract_live_info(live_data: Dict) -> tuple:
        """Extract live_start_at and live_item_id from a /live response.

        Returns (live_start_at, live_item_id) or (None, None) if not live.
        """
        included = live_data.get('included', [])
        data = live_data.get('data', {})
        cit_rel = data.get('relationships', {}).get('current_item_time', {}).get('data')
        if not cit_rel:
            return None, None

        cit_id = cit_rel.get('id')
        cit = next((res for res in included if res['type'] == 'ItemTime' and res['id'] == cit_id), None)
        if not cit:
            return None, None

        live_start_at_str = cit.get('attributes', {}).get('live_start_at')
        if not live_start_at_str:
            return None, None

        try:
            live_start_at = dateutil.parser.isoparse(live_start_at_str)
        except (ValueError, TypeError):
            logger.warning("Invalid live_start_at date: %s", live_start_at_str)
            return None, None
        item_data = cit.get('relationships', {}).get('item', {}).get('data')
        live_item_id = item_data.get('id') if isinstance(item_data, dict) else None
        return live_start_at, live_item_id

    def _scan_for_live(self, candidates: List[Service]) -> Optional[Service]:
        """Poll /live for all candidates, return the one with most recent live_start_at."""
        best_plan = None
        latest_click = datetime.min.replace(tzinfo=timezone.utc)

        for plan in candidates:
            try:
                live_data = self.client.get_live_status(plan.type_id, plan.id)
                live_start_at, live_item_id = self._extract_live_info(live_data)
                if live_start_at:
                    plan.live_start_at = live_start_at
                    if live_item_id is not None:
                        plan.live_item_id = live_item_id
                    if live_start_at > latest_click:
                        latest_click = live_start_at
                        best_plan = plan
            except Exception as e:
                logger.warning("Failed to get live status for plan %s: %s", plan.plan_title, e)
                continue

        return best_plan

    def _poll_tracked_plan(self, plan: Service) -> bool:
        """Poll /live for a single tracked plan. Returns True if still live."""
        try:
            live_data = self.client.get_live_status(plan.type_id, plan.id)
            live_start_at, live_item_id = self._extract_live_info(live_data)

            if live_start_at:
                plan.live_start_at = live_start_at
                plan.live_item_id = live_item_id

                # Fetch notes for current live item
                if plan.live_item_id:
                    try:
                        raw_notes = self.client.get_item_notes(plan.type_id, plan.id, plan.live_item_id)
                        item = next((i for i in plan.items if i.id == plan.live_item_id), None)
                        if item:
                            item.notes = {n['category']: n['content'] for n in raw_notes}
                    except Exception as e:
                        logger.debug("Failed to fetch notes for item %s: %s", plan.live_item_id, e)

                return True

            # No current_item_time → not live anymore
            plan.live_item_id = None
            plan.live_start_at = None
            return False
        except Exception as e:
            logger.warning("Error polling tracked plan %s: %s", plan.plan_title, e)
            return False

    def _perform_sync(self, now: datetime):
        """
        State machine: IDLE → SCANNING → TRACKING
        """
        try:
            with self._lock:
                state = self._state

            if state == SyncState.IDLE:
                self._sync_idle(now)
            elif state == SyncState.SCANNING:
                self._sync_scanning(now)
            elif state == SyncState.TRACKING:
                self._sync_tracking(now)

        except Exception as e:
            with self._lock:
                self.last_error = str(e)
            logger.error("Sync failure: %s", e)

    def _sync_idle(self, now: datetime):
        """IDLE: Refresh candidates periodically, check for live."""
        mono_now = time.monotonic()

        # Refresh candidates every IDLE_RESCAN_INTERVAL
        with self._lock:
            has_candidates = bool(self._candidates)
            last_rescan = self._last_rescan
        if not has_candidates or mono_now - last_rescan >= self.IDLE_RESCAN_INTERVAL:
            self._refresh_candidates()

        with self._lock:
            has_candidates = bool(self._candidates)
        if not has_candidates:
            with self._lock:
                self.current_plan = None
                self.last_poll_time = time.monotonic()
                self.last_error = None
            return

        # Transition to SCANNING to check for live
        with self._lock:
            self._state = SyncState.SCANNING

        self._sync_scanning(now)

    def _sync_scanning(self, now: datetime):
        """SCANNING: Poll /live for all candidates, pick best, transition out."""
        with self._lock:
            candidates = list(self._candidates)
        best_plan = self._scan_for_live(candidates)

        if best_plan:
            # Populate items for the winner
            try:
                self.client.populate_plan_details(best_plan)
            except Exception as e:
                logger.warning("Failed to populate items for plan %s: %s", best_plan.plan_title, e)

            with self._lock:
                self.current_plan = best_plan
                self._tracked_plan_key = (best_plan.type_id, best_plan.id)
                self._state = SyncState.TRACKING
                self._last_full_scan = time.monotonic()
                self.last_poll_time = time.monotonic()
                self.last_error = None
            logger.info("TRACKING plan: %s", best_plan.plan_title)
            self._fetch_team_for_plan(best_plan)
        else:
            # Nothing live — pick closest upcoming plan via smart_distance
            best_upcoming = self._pick_nearest_upcoming(now)

            with self._lock:
                self.current_plan = best_upcoming
                self._state = SyncState.IDLE
                self.last_poll_time = time.monotonic()
                self.last_error = None

    def _sync_tracking(self, now: datetime):
        """TRACKING: Poll only the tracked plan. Periodic full scan every 60s."""
        with self._lock:
            plan = self.current_plan
            tracked_key = self._tracked_plan_key

        if not plan or not tracked_key:
            with self._lock:
                self._state = SyncState.SCANNING
            return

        still_live = self._poll_tracked_plan(plan)

        if not still_live:
            logger.info("Tracked plan %s no longer live, switching to SCANNING", plan.plan_title)
            with self._lock:
                self.current_plan = plan  # keep showing it while scanning
                self._tracked_plan_key = None
                self._state = SyncState.SCANNING
                self._team_members = []
                self._team_plan_key = None
            # Immediately scan to see if another plan took over
            self._sync_scanning(now)
            return

        # Periodic full scan to catch abandoned-session takeover
        mono_now = time.monotonic()
        if mono_now - self._last_full_scan >= self.TRACKING_FULL_SCAN_INTERVAL:
            self._last_full_scan = mono_now
            # Refresh candidates
            self._refresh_candidates()
            with self._lock:
                scan_candidates = list(self._candidates)
            better = self._scan_for_live(scan_candidates)
            if better and better.live_start_at and plan.live_start_at:
                if better.live_start_at > plan.live_start_at and (better.type_id, better.id) != tracked_key:
                    # A newer plan is live — switch to it
                    self.client.populate_plan_details(better)
                    with self._lock:
                        self.current_plan = better
                        self._tracked_plan_key = (better.type_id, better.id)
                    logger.info("Switched to newer live plan: %s", better.plan_title)
                    self._fetch_team_for_plan(better)

        with self._lock:
            self.last_poll_time = time.monotonic()
            self.last_error = None

    def _pick_nearest_upcoming(self, now: datetime) -> Optional[Service]:
        """Pick the nearest upcoming plan from candidates using smart_distance."""
        with self._lock:
            candidates = list(self._candidates)
        if not candidates:
            return None

        def smart_distance(plan):
            if plan.start_time < now:
                end_time = plan.start_time + timedelta(seconds=plan.total_length)
                return abs((end_time - now).total_seconds())
            else:
                return abs((plan.start_time - now).total_seconds())

        sorted_plans = sorted(candidates, key=smart_distance)
        best = sorted_plans[0]
        # Populate items for display
        self.client.populate_plan_details(best)
        return best

    def _get_dynamic_interval(self) -> int:
        """
        Determines how aggressively to poll based on state.
        """
        if self._state == SyncState.TRACKING:
            return self.TRACKING_POLL_INTERVAL
        if self._state == SyncState.SCANNING:
            return 1  # fast transition
        return self.IDLE_RESCAN_INTERVAL

    def _fetch_service_type_names(self):
        """
        Fetch and cache service type names from PCO API.
        """
        try:
            service_types = self.client.get_service_types()
            for st in service_types:
                st_id = st.get('id')
                st_name = st.get('name')
                if st_id and st_name:
                    self._service_type_names[st_id] = st_name
            logger.info("Cached %d service type names", len(self._service_type_names))
        except Exception as e:
            logger.warning("Failed to fetch service type names: %s", e)

    @property
    def team_members(self) -> List[TeamMember]:
        with self._lock:
            return list(self._team_members)

    def _fetch_team_for_plan(self, plan: Service):
        """Fetch team members for a plan (once per plan)."""
        if not self._team_enabled:
            return
        if self._team_plan_key == (plan.type_id, plan.id):
            return
        try:
            members = fetch_and_cache_team(
                self.client, plan.type_id, plan.id, self._team_cache_dir
            )
            with self._lock:
                self._team_members = members
                self._team_plan_key = (plan.type_id, plan.id)
            logger.info("Fetched %d team members for plan %s", len(members), plan.plan_title)
        except Exception as e:
            logger.warning("Failed to fetch team for plan %s: %s", plan.plan_title, e)

    def stop(self):
        self._stop_event.set()
        if self._sync_thread and self._sync_thread.is_alive():
            self._sync_thread.join(timeout=1)
