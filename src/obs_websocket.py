"""
OBS WebSocket integration for PCO Live Timer.
Pushes timer data to individual OBS Text sources via obs-websocket 5.x protocol.
"""
import logging
import threading
import time
from typing import Optional, Set

from .manager import PlanManager
from .formatting import build_timer_response

logger = logging.getLogger("obs_websocket")

# Color constants (ABGR format for OBS FreeType2/GDI+ text sources)
COLOR_GREEN = 0xFF80DE4A   # #4ade80
COLOR_RED = 0xFF4444EF     # #ef4444
COLOR_WHITE = 0xFFFFFFFF   # #ffffff


class OBSTextPusher:
    """Connects to OBS WebSocket and pushes PCO timer data to named text sources."""

    def __init__(
        self,
        manager: PlanManager,
        host: str = "localhost",
        port: int = 4455,
        password: str = "",
        update_interval_ms: int = 1000,
    ):
        self.manager = manager
        self.host = host
        self.port = port
        self.password = password
        self.update_interval = update_interval_ms / 1000.0

        self._ws = None  # obsws_python.ReqClient
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._missing_sources: Set[str] = set()  # track sources that don't exist

    # ── Connection management ──────────────────────────────────────────

    def _connect(self) -> bool:
        """Connect to OBS WebSocket. Returns True on success."""
        try:
            import obsws_python as obs

            self._ws = obs.ReqClient(
                host=self.host,
                port=self.port,
                password=self.password if self.password else None,
                timeout=5,
            )
            self._missing_sources.clear()
            logger.info("Connected to OBS at %s:%d", self.host, self.port)
            return True
        except Exception as e:
            logger.warning("Connection failed (%s), retrying in 5s...", e)
            self._ws = None
            return False

    def _disconnect(self):
        """Clean disconnect from OBS WebSocket."""
        if self._ws:
            try:
                self._ws.base_client.ws.close()
            except Exception:
                pass
            self._ws = None

    # ── Background loop ────────────────────────────────────────────────

    def start(self):
        """Start the background push thread."""
        self._thread = threading.Thread(target=self._push_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Signal stop and wait for thread to finish."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._disconnect()

    def _push_loop(self):
        """Main loop: connect, then tick → format → push on interval."""
        while not self._stop_event.is_set():
            # Ensure connected
            if not self._ws:
                if not self._connect():
                    self._stop_event.wait(5)
                    continue

            try:
                self._push_all_values()
            except Exception as e:
                logger.warning("Push error (%s), reconnecting...", e)
                self._disconnect()
                continue

            self._stop_event.wait(self.update_interval)

    # ── Push logic ─────────────────────────────────────────────────────

    def _push_all_values(self):
        """Get timer data and push each value to its OBS source."""
        data = build_timer_response(self.manager)

        # Service metadata
        self._set_text(
            "PCO Service Type",
            (data["service_type_name"] or "").upper(),
        )
        self._set_text("PCO Service Date", data["service_date"] or "")
        self._set_text(
            "PCO Plan Title",
            f'"{data["plan_title"]}"' if data["plan_title"] else "",
        )

        # Progress
        self._set_text(
            "PCO Progress",
            data["progress"]["text"] if data["progress"] else "",
        )

        # Current item
        if data["current_item"]:
            ci = data["current_item"]
            countdown_secs = ci["countdown_seconds"]

            self._set_text(
                "PCO Countdown",
                ci["countdown_formatted"],
                color=self._countdown_color(countdown_secs),
            )
            self._set_text("PCO Current Title", ci["title"])
            self._set_text("PCO Current Description", ci["description"] or "")
            self._set_text("PCO Item Length", ci["length_formatted"])
        else:
            self._set_text("PCO Countdown", "", color=self._countdown_color(0))
            self._set_text("PCO Current Title", "")
            self._set_text("PCO Current Description", "")
            self._set_text("PCO Item Length", "")

        # Next item
        if data["next_item"]:
            ni = data["next_item"]
            self._set_text("PCO Next Title", ni["title"])
            self._set_text("PCO Next Length", f'({ni["length_formatted"]})')
        else:
            self._set_text("PCO Next Title", "")
            self._set_text("PCO Next Length", "")

        # Service end
        if data["service_end"]:
            se = data["service_end"]
            self._set_text(
                "PCO Service End",
                se["status_text"],
                color=self._service_end_color(se["overrun_minutes"]),
            )
        else:
            self._set_text("PCO Service End", "")

        # Team members
        for member in data.get("team_members", []):
            self._set_text(member["name_source"], member["name"])
            self._set_text(member["position_source"], member["position"])
            self._set_image(member["photo_source"], member.get("photo_path", ""))

    def _set_text(self, source_name: str, text: str, color: Optional[int] = None):
        """Push text (and optional color) to a named OBS text source."""
        if not self._ws or source_name in self._missing_sources:
            return

        settings = {"text": text}
        if color is not None:
            settings["color1"] = color
            settings["color2"] = color

        try:
            self._ws.set_input_settings(source_name, settings, overlay=True)
        except Exception as e:
            err_msg = str(e)
            # OBS returns error 600 when source doesn't exist
            if "600" in err_msg or "No source" in err_msg:
                self._missing_sources.add(source_name)
                logger.info("Source '%s' not found in OBS, skipping", source_name)
            else:
                raise

    def _set_image(self, source_name: str, file_path: str):
        """Push a file path to a named OBS image source."""
        if not self._ws or source_name in self._missing_sources:
            return

        settings = {"file": file_path}
        try:
            self._ws.set_input_settings(source_name, settings, overlay=True)
        except Exception as e:
            err_msg = str(e)
            if "600" in err_msg or "No source" in err_msg:
                self._missing_sources.add(source_name)
                logger.info("Source '%s' not found in OBS, skipping", source_name)
            else:
                raise

    # ── Color logic ────────────────────────────────────────────────────

    @staticmethod
    def _countdown_color(seconds: float) -> int:
        """Return ABGR color int based on countdown state."""
        if seconds < 0:
            return COLOR_RED
        else:
            return COLOR_GREEN

    @staticmethod
    def _service_end_color(overrun_minutes: float) -> int:
        """Return ABGR color int based on service end overrun."""
        if round(overrun_minutes) > 0:
            return COLOR_RED
        else:
            return COLOR_WHITE
