"""
TrayApp: AppIndicator3 system tray icon, menu, and engine lifecycle.
"""
import logging
import os
import threading
from pathlib import Path

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("AppIndicator3", "0.1")
from gi.repository import Gtk, GLib, AppIndicator3

from .icons import generate_all_icons, generate_placeholder_png
from .config_io import load_config, validate_config

logger = logging.getLogger(__name__)

_CONFIG_PATH = str(Path(__file__).resolve().parent.parent.parent / "config.toml")
_ICON_CACHE_DIR = os.path.join(
    os.path.expanduser("~"), ".cache", "obs-pco-live-timer", "icons"
)


class TrayApp:
    """System tray application — owns the engine lifecycle and main window."""

    def __init__(self):
        self.icons = generate_all_icons(_ICON_CACHE_DIR)
        self.manager = None
        self.obs_pusher = None
        self._window = None
        self._config = None

        # Create AppIndicator
        self.indicator = AppIndicator3.Indicator.new(
            "pco-live-timer",
            self.icons["gray"],
            AppIndicator3.IndicatorCategory.APPLICATION_STATUS,
        )
        self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        self.indicator.set_menu(self._build_menu())

        # Status polling timer (updates tray icon color)
        self._status_timer_id = GLib.timeout_add(2000, self._update_tray_icon)

        # Try to load config and start engine
        self._load_and_start()

    # ── Menu ────────────────────────────────────────────────────────

    def _build_menu(self) -> Gtk.Menu:
        menu = Gtk.Menu()

        item_show = Gtk.MenuItem(label="Show")
        item_show.connect("activate", self._on_show)
        menu.append(item_show)

        menu.append(Gtk.SeparatorMenuItem())

        item_quit = Gtk.MenuItem(label="Quit")
        item_quit.connect("activate", self._on_quit)
        menu.append(item_quit)

        menu.show_all()
        return menu

    # ── Menu handlers ───────────────────────────────────────────────

    def _on_show(self, _widget):
        self._ensure_window().present()

    def _on_quit(self, _widget):
        logger.info("Quit requested from tray menu")
        self.stop_engine()
        Gtk.main_quit()

    # ── Window ──────────────────────────────────────────────────────

    def _ensure_window(self):
        if self._window is None:
            from .main_window import MainWindow
            self._window = MainWindow(self)
        return self._window

    # ── Engine lifecycle ────────────────────────────────────────────

    def _load_and_start(self):
        """Load config and start engine if valid. Otherwise open Settings tab."""
        self._config = load_config(_CONFIG_PATH)
        errors = validate_config(self._config)
        if errors:
            logger.info("Config invalid or missing — opening Settings tab")
            self._set_icon("gray")
            # Open window on Settings tab on next idle
            GLib.idle_add(self._show_settings_tab)
            return
        self._start_engine(self._config)

    def _show_settings_tab(self):
        win = self._ensure_window()
        win.show_settings_tab(first_run=True)
        win.present()
        return False  # don't repeat

    def _start_engine(self, config):
        """Create PCOClient, PlanManager, and OBSTextPusher from config."""
        from src.pco_client import PCOClient
        from src.manager import PlanManager

        mode = config["pco"].get("discovery_mode", "folder")
        client = PCOClient(
            app_id=config["pco"]["app_id"],
            secret=config["pco"]["secret"],
        )

        # Discover service types
        try:
            if mode == "service_types":
                service_type_ids = list(config["pco"].get("service_type_ids", []))
            elif mode == "all":
                service_types = client.get_service_types()
                service_type_ids = [st["id"] for st in service_types]
            else:  # folder
                folder_id = config["pco"]["folder_id"]
                service_types = client.get_folder_service_types(folder_id)
                service_type_ids = [st["id"] for st in service_types]
        except Exception as e:
            logger.error("Failed to fetch service types: %s", e)
            self._set_icon("red")
            return

        if not service_type_ids:
            logger.error("No service types found")
            self._set_icon("red")
            return

        # Team config
        team_config = config.get("team", {})
        team_cache_dir = team_config.get("photo_cache_dir", "") or os.path.join(
            os.path.expanduser("~"), ".cache", "obs-pco-live-timer", "photos"
        )

        # Placeholder photo
        placeholder_photo_path = team_config.get("placeholder_photo", "")
        if not placeholder_photo_path and team_config.get("enabled", True):
            os.makedirs(team_cache_dir, exist_ok=True)
            placeholder_photo_path = os.path.join(team_cache_dir, "placeholder_avatar.png")
            if not os.path.exists(placeholder_photo_path):
                generate_placeholder_png(placeholder_photo_path)

        self.manager = PlanManager(
            client=client,
            target_service_type_ids=service_type_ids,
            start_thread=True,
            team_enabled=team_config.get("enabled", True),
            team_cache_dir=team_cache_dir,
            team_slots=team_config.get("slots", []),
            team_placeholder_photo=placeholder_photo_path,
        )

        # Start OBS pusher if enabled
        obs_config = config.get("obs", {})
        if obs_config.get("enabled", False):
            from src.obs_websocket import OBSTextPusher
            self.obs_pusher = OBSTextPusher(
                manager=self.manager,
                host=obs_config.get("host", "localhost"),
                port=obs_config.get("port", 4455),
                password=obs_config.get("password", ""),
                update_interval_ms=obs_config.get("update_interval_ms", 1000),
            )
            self.obs_pusher.start()

        self._config = config
        logger.info("Engine started with %d service types", len(service_type_ids))

    def stop_engine(self):
        """Stop manager and OBS pusher."""
        if self.obs_pusher:
            self.obs_pusher.stop()
            self.obs_pusher = None
        if self.manager:
            self.manager.stop()
            self.manager = None

    def restart_engine(self, config):
        """Stop current engine and start with new config."""
        self.stop_engine()
        self._config = config
        self._start_engine(config)

    @property
    def config(self):
        return self._config

    @property
    def config_path(self):
        return _CONFIG_PATH

    # ── Icon state ──────────────────────────────────────────────────

    def _set_icon(self, state: str):
        path = self.icons.get(state, self.icons["gray"])
        self.indicator.set_icon_full(path, state)

    def _update_tray_icon(self) -> bool:
        """Periodic callback to update tray icon based on manager state."""
        if not self.manager:
            self._set_icon("gray")
            return True

        if self.manager.last_error:
            self._set_icon("red")
            return True

        from src.manager import SyncState
        state = self.manager.state
        if state == SyncState.TRACKING:
            self._set_icon("green")
        elif state in (SyncState.IDLE, SyncState.SCANNING):
            self._set_icon("yellow")
        else:
            self._set_icon("gray")

        return True  # keep timer running
