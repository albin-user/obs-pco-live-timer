"""
MainWindow: Single GTK window with 4 tabs — Live Status, OBS Reference, Settings, Help.
"""
import logging
import os
import threading

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, GdkPixbuf, Pango

from .config_io import load_config, save_config, validate_config
from .obs_reference_panel import build_obs_reference_panel

logger = logging.getLogger(__name__)


class MainWindow(Gtk.Window):

    def __init__(self, tray_app):
        super().__init__(title="PCO Live Timer")
        self.tray_app = tray_app
        self.set_default_size(720, 580)
        self.set_position(Gtk.WindowPosition.CENTER)

        # Hide on close instead of destroy
        self.connect("delete-event", self._on_delete)

        self.notebook = Gtk.Notebook()
        self.add(self.notebook)

        # Tab 1: Live Status
        self._live_box = self._build_live_status_tab()
        self.notebook.append_page(self._live_box, Gtk.Label(label="Live Status"))

        # Tab 2: OBS Reference
        self._obs_ref_box = build_obs_reference_panel(
            slots=self._get_slots()
        )
        self.notebook.append_page(self._obs_ref_box, Gtk.Label(label="OBS Reference"))

        # Tab 3: Settings
        self._settings_box = self._build_settings_tab()
        self.notebook.append_page(self._settings_box, Gtk.Label(label="Settings"))

        # Tab 4: Help
        self._help_box = self._build_help_tab()
        self.notebook.append_page(self._help_box, Gtk.Label(label="Help"))

        # Live Status refresh timer
        self._refresh_timer_id = None
        self.notebook.connect("switch-page", self._on_tab_switched)

        self.show_all()

        # Start refresh if live tab is active
        self._start_live_refresh()

    # ── Window behavior ─────────────────────────────────────────────

    def _on_delete(self, widget, event):
        self.hide()
        self._stop_live_refresh()
        return True  # prevent destroy

    def show_settings_tab(self, first_run=False):
        """Switch to Settings tab. Optionally show welcome banner."""
        self.notebook.set_current_page(2)
        if first_run and hasattr(self, "_welcome_banner"):
            self._welcome_banner.show()

    # ── Helpers ─────────────────────────────────────────────────────

    def _get_slots(self):
        config = self.tray_app.config
        if config:
            return config.get("team", {}).get("slots", [])
        return []

    # ── Tab 1: Live Status ──────────────────────────────────────────

    def _build_live_status_tab(self) -> Gtk.Box:
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        vbox.set_margin_start(16)
        vbox.set_margin_end(16)
        vbox.set_margin_top(12)
        vbox.set_margin_bottom(12)

        # State banner
        self._state_label = Gtk.Label()
        self._state_label.set_markup('<span weight="bold" size="large">Waiting for data...</span>')
        self._state_label.set_xalign(0)
        vbox.pack_start(self._state_label, False, False, 0)

        # Service info line
        self._service_info_label = Gtk.Label()
        self._service_info_label.set_xalign(0)
        self._service_info_label.set_line_wrap(True)
        vbox.pack_start(self._service_info_label, False, False, 0)

        vbox.pack_start(Gtk.Separator(), False, False, 4)

        # Countdown
        self._countdown_label = Gtk.Label()
        self._countdown_label.set_markup('<span font="48" weight="bold">--:--</span>')
        vbox.pack_start(self._countdown_label, False, False, 0)

        # Current item
        self._current_title_label = Gtk.Label()
        self._current_title_label.set_xalign(0)
        self._current_title_label.set_ellipsize(Pango.EllipsizeMode.END)
        vbox.pack_start(self._current_title_label, False, False, 0)

        self._current_desc_label = Gtk.Label()
        self._current_desc_label.set_xalign(0)
        self._current_desc_label.set_line_wrap(True)
        vbox.pack_start(self._current_desc_label, False, False, 0)

        # Progress + item length line
        self._progress_label = Gtk.Label()
        self._progress_label.set_xalign(0)
        vbox.pack_start(self._progress_label, False, False, 0)

        vbox.pack_start(Gtk.Separator(), False, False, 4)

        # Next item
        self._next_label = Gtk.Label()
        self._next_label.set_xalign(0)
        vbox.pack_start(self._next_label, False, False, 0)

        # Service end
        self._service_end_label = Gtk.Label()
        self._service_end_label.set_xalign(0)
        vbox.pack_start(self._service_end_label, False, False, 0)

        vbox.pack_start(Gtk.Separator(), False, False, 4)

        # Team members grid
        team_label = Gtk.Label()
        team_label.set_markup('<span weight="bold">Team Members</span>')
        team_label.set_xalign(0)
        vbox.pack_start(team_label, False, False, 0)

        self._team_grid = Gtk.FlowBox()
        self._team_grid.set_max_children_per_line(6)
        self._team_grid.set_min_children_per_line(3)
        self._team_grid.set_selection_mode(Gtk.SelectionMode.NONE)
        self._team_grid.set_homogeneous(True)

        team_scroll = Gtk.ScrolledWindow()
        team_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        team_scroll.set_vexpand(True)
        team_scroll.add(self._team_grid)
        vbox.pack_start(team_scroll, True, True, 0)

        return vbox

    def _start_live_refresh(self):
        if self._refresh_timer_id is None:
            self._refresh_timer_id = GLib.timeout_add(500, self._refresh_live_status)

    def _stop_live_refresh(self):
        if self._refresh_timer_id is not None:
            GLib.source_remove(self._refresh_timer_id)
            self._refresh_timer_id = None

    def _on_tab_switched(self, notebook, page, page_num):
        if page_num == 0 and self.get_visible():
            self._start_live_refresh()
        else:
            self._stop_live_refresh()

    def _refresh_live_status(self) -> bool:
        """Called every 500ms to update the Live Status tab."""
        if not self.get_visible() or self.notebook.get_current_page() != 0:
            self._refresh_timer_id = None
            return False  # stop timer

        manager = self.tray_app.manager
        if not manager:
            self._state_label.set_markup(
                '<span weight="bold" size="large" foreground="gray">'
                "No configuration \u2014 go to Settings tab</span>"
            )
            return True

        from src.formatting import build_timer_response
        data = build_timer_response(manager)

        # State banner
        from src.manager import SyncState
        state = manager.state
        if data.get("is_live"):
            stype = data.get("service_type_name") or ""
            self._state_label.set_markup(
                f'<span weight="bold" size="large" foreground="#4ade80">'
                f'TRACKING: {GLib.markup_escape_text(stype.upper())}</span>'
            )
        elif data.get("is_finished"):
            self._state_label.set_markup(
                '<span weight="bold" size="large" foreground="gray">Service Finished</span>'
            )
        elif state == SyncState.SCANNING:
            self._state_label.set_markup(
                '<span weight="bold" size="large" foreground="#facc15">Scanning...</span>'
            )
        else:
            msg = data.get("message") or "Waiting..."
            self._state_label.set_markup(
                f'<span weight="bold" size="large" foreground="#facc15">'
                f'{GLib.markup_escape_text(msg)}</span>'
            )

        # Service info
        parts = []
        if data.get("service_date"):
            parts.append(data["service_date"])
        if data.get("plan_title"):
            parts.append(f'"{data["plan_title"]}"')
        self._service_info_label.set_text("    ".join(parts))

        # Countdown
        ci = data.get("current_item")
        if ci:
            secs = ci["countdown_seconds"]
            formatted = ci["countdown_formatted"]
            color = "#ef4444" if secs < 0 else "#4ade80"
            self._countdown_label.set_markup(
                f'<span font="48" weight="bold" foreground="{color}">{formatted}</span>'
            )
            self._current_title_label.set_markup(
                f'<span weight="bold" size="large">'
                f'{GLib.markup_escape_text(ci["title"])}</span>'
            )
            desc = ci.get("description") or ""
            length = ci.get("length_formatted", "")
            desc_text = f"Item Length: {length}"
            if desc:
                desc_text += f"    {desc}"
            self._current_desc_label.set_text(desc_text)
        else:
            self._countdown_label.set_markup(
                '<span font="48" weight="bold" foreground="gray">--:--</span>'
            )
            self._current_title_label.set_text("")
            self._current_desc_label.set_text("")

        # Progress
        prog = data.get("progress")
        if prog:
            self._progress_label.set_text(f"Progress: {prog['text']}")
        else:
            self._progress_label.set_text("")

        # Next item
        ni = data.get("next_item")
        if ni:
            self._next_label.set_markup(
                f'Next: <b>{GLib.markup_escape_text(ni["title"])}</b>'
                f'    ({ni["length_formatted"]})'
            )
        else:
            self._next_label.set_text("")

        # Service end
        se = data.get("service_end")
        if se:
            overrun = se.get("overrun_minutes", 0)
            color = "#ef4444" if overrun > 0 else "white"
            self._service_end_label.set_markup(
                f'<span foreground="{color}">'
                f'{GLib.markup_escape_text(se["status_text"])}</span>'
            )
        else:
            self._service_end_label.set_text("")

        # Team members
        self._update_team_grid(data.get("team_members", []))

        return True  # keep timer running

    def _update_team_grid(self, team_data):
        """Update the team member FlowBox."""
        # Clear existing children
        for child in self._team_grid.get_children():
            self._team_grid.remove(child)

        for member in team_data:
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            card.set_margin_start(4)
            card.set_margin_end(4)
            card.set_margin_top(4)
            card.set_margin_bottom(4)

            # Photo
            photo_path = member.get("photo_path", "")
            if photo_path and os.path.exists(photo_path):
                try:
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                        photo_path, 64, 64, True
                    )
                    img = Gtk.Image.new_from_pixbuf(pixbuf)
                except Exception:
                    img = Gtk.Image.new_from_icon_name("avatar-default", Gtk.IconSize.DIALOG)
            else:
                img = Gtk.Image.new_from_icon_name("avatar-default", Gtk.IconSize.DIALOG)
            card.pack_start(img, False, False, 0)

            # Name
            name_label = Gtk.Label(label=member.get("name", ""))
            name_label.set_ellipsize(Pango.EllipsizeMode.END)
            name_label.set_max_width_chars(10)
            card.pack_start(name_label, False, False, 0)

            # Position
            pos_label = Gtk.Label()
            pos_text = member.get("position", "")
            pos_label.set_markup(f'<span size="small" foreground="gray">{GLib.markup_escape_text(pos_text)}</span>')
            pos_label.set_ellipsize(Pango.EllipsizeMode.END)
            pos_label.set_max_width_chars(10)
            card.pack_start(pos_label, False, False, 0)

            self._team_grid.add(card)

        self._team_grid.show_all()

    # ── Tab 2: OBS Reference (built externally) ────────────────────

    # ── Tab 3: Settings ─────────────────────────────────────────────

    def _build_settings_tab(self) -> Gtk.Box:
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        vbox.set_margin_start(16)
        vbox.set_margin_end(16)
        vbox.set_margin_top(12)
        vbox.set_margin_bottom(12)

        # Welcome banner (hidden by default)
        self._welcome_banner = Gtk.InfoBar()
        self._welcome_banner.set_message_type(Gtk.MessageType.INFO)
        banner_label = Gtk.Label(
            label="Enter your PCO credentials to get started. See the Help tab for instructions."
        )
        banner_label.set_line_wrap(True)
        self._welcome_banner.get_content_area().add(banner_label)
        self._welcome_banner.set_no_show_all(True)
        vbox.pack_start(self._welcome_banner, False, False, 0)

        # ── PCO Connection ──────────────────────────────────────────
        vbox.pack_start(self._section_header("PCO Connection"), False, False, 4)

        grid_pco = Gtk.Grid(column_spacing=12, row_spacing=6)
        config = self.tray_app.config or load_config(self.tray_app.config_path)

        grid_pco.attach(Gtk.Label(label="App ID:", xalign=1), 0, 0, 1, 1)
        self._entry_app_id = Gtk.Entry()
        self._entry_app_id.set_text(config["pco"]["app_id"])
        self._entry_app_id.set_hexpand(True)
        grid_pco.attach(self._entry_app_id, 1, 0, 2, 1)

        grid_pco.attach(Gtk.Label(label="Secret:", xalign=1), 0, 1, 1, 1)
        self._entry_secret = Gtk.Entry()
        self._entry_secret.set_text(config["pco"]["secret"])
        self._entry_secret.set_visibility(False)
        self._entry_secret.set_hexpand(True)
        grid_pco.attach(self._entry_secret, 1, 1, 2, 1)

        btn_test_pco = Gtk.Button(label="Test PCO Connection")
        btn_test_pco.connect("clicked", self._on_test_pco)
        grid_pco.attach(btn_test_pco, 0, 2, 1, 1)
        self._pco_status_label = Gtk.Label(label="")
        self._pco_status_label.set_xalign(0)
        self._pco_status_label.set_line_wrap(True)
        grid_pco.attach(self._pco_status_label, 1, 2, 2, 1)

        # Folder
        grid_pco.attach(Gtk.Label(label="Folder:", xalign=1), 0, 3, 1, 1)
        self._folder_combo = Gtk.ComboBoxText()
        self._folder_combo.set_hexpand(True)
        self._folder_combo.connect("changed", self._on_folder_changed)
        grid_pco.attach(self._folder_combo, 1, 3, 1, 1)

        btn_fetch_folders = Gtk.Button(label="Fetch Folders")
        btn_fetch_folders.connect("clicked", self._on_fetch_folders)
        grid_pco.attach(btn_fetch_folders, 2, 3, 1, 1)

        # Pre-populate folder_id if we have one
        self._folder_id_manual = config["pco"]["folder_id"]
        if self._folder_id_manual:
            self._folder_combo.append(self._folder_id_manual, f"ID: {self._folder_id_manual}")
            self._folder_combo.set_active_id(self._folder_id_manual)

        # Service types discovered (read-only display)
        self._service_types_label = Gtk.Label(label="")
        self._service_types_label.set_xalign(0)
        self._service_types_label.set_line_wrap(True)
        grid_pco.attach(self._service_types_label, 0, 4, 3, 1)

        vbox.pack_start(grid_pco, False, False, 0)

        # ── OBS Connection ──────────────────────────────────────────
        vbox.pack_start(self._section_header("OBS Connection"), False, False, 4)

        grid_obs = Gtk.Grid(column_spacing=12, row_spacing=6)

        self._chk_obs_enabled = Gtk.CheckButton(label="Enable OBS WebSocket")
        self._chk_obs_enabled.set_active(config["obs"]["enabled"])
        grid_obs.attach(self._chk_obs_enabled, 0, 0, 3, 1)

        grid_obs.attach(Gtk.Label(label="Host:", xalign=1), 0, 1, 1, 1)
        self._entry_obs_host = Gtk.Entry()
        self._entry_obs_host.set_text(config["obs"]["host"])
        self._entry_obs_host.set_hexpand(True)
        grid_obs.attach(self._entry_obs_host, 1, 1, 2, 1)

        grid_obs.attach(Gtk.Label(label="Port:", xalign=1), 0, 2, 1, 1)
        self._spin_obs_port = Gtk.SpinButton.new_with_range(1, 65535, 1)
        self._spin_obs_port.set_value(config["obs"]["port"])
        grid_obs.attach(self._spin_obs_port, 1, 2, 1, 1)

        grid_obs.attach(Gtk.Label(label="Password:", xalign=1), 0, 3, 1, 1)
        self._entry_obs_password = Gtk.Entry()
        self._entry_obs_password.set_text(config["obs"]["password"])
        self._entry_obs_password.set_visibility(False)
        self._entry_obs_password.set_hexpand(True)
        grid_obs.attach(self._entry_obs_password, 1, 3, 2, 1)

        grid_obs.attach(Gtk.Label(label="Update interval (ms):", xalign=1), 0, 4, 1, 1)
        self._spin_interval = Gtk.SpinButton.new_with_range(100, 5000, 100)
        self._spin_interval.set_value(config["obs"]["update_interval_ms"])
        grid_obs.attach(self._spin_interval, 1, 4, 1, 1)

        btn_test_obs = Gtk.Button(label="Test OBS Connection")
        btn_test_obs.connect("clicked", self._on_test_obs)
        grid_obs.attach(btn_test_obs, 0, 5, 1, 1)
        self._obs_status_label = Gtk.Label(label="")
        self._obs_status_label.set_xalign(0)
        grid_obs.attach(self._obs_status_label, 1, 5, 2, 1)

        vbox.pack_start(grid_obs, False, False, 0)

        # ── Team Positions ──────────────────────────────────────────
        vbox.pack_start(self._section_header("Team Positions"), False, False, 4)

        self._chk_team_enabled = Gtk.CheckButton(label="Enable team members")
        self._chk_team_enabled.set_active(config.get("team", {}).get("enabled", True))
        vbox.pack_start(self._chk_team_enabled, False, False, 0)

        team_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        # Available positions (left)
        avail_frame = Gtk.Frame(label="Available Positions")
        avail_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        avail_vbox.set_margin_start(4)
        avail_vbox.set_margin_end(4)
        avail_vbox.set_margin_top(4)
        avail_vbox.set_margin_bottom(4)

        btn_fetch_positions = Gtk.Button(label="Fetch from PCO")
        btn_fetch_positions.connect("clicked", self._on_fetch_positions)
        avail_vbox.pack_start(btn_fetch_positions, False, False, 0)

        self._avail_listbox = Gtk.ListBox()
        self._avail_listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        avail_scroll = Gtk.ScrolledWindow()
        avail_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        avail_scroll.set_size_request(-1, 150)
        avail_scroll.add(self._avail_listbox)
        avail_vbox.pack_start(avail_scroll, True, True, 0)
        avail_frame.add(avail_vbox)
        team_hbox.pack_start(avail_frame, True, True, 0)

        # Add/Remove buttons (center)
        btn_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        btn_vbox.set_valign(Gtk.Align.CENTER)
        btn_add = Gtk.Button(label="Add >>")
        btn_add.connect("clicked", self._on_add_slot)
        btn_vbox.pack_start(btn_add, False, False, 0)
        btn_remove = Gtk.Button(label="<< Remove")
        btn_remove.connect("clicked", self._on_remove_slot)
        btn_vbox.pack_start(btn_remove, False, False, 0)
        btn_up = Gtk.Button(label="Move Up")
        btn_up.connect("clicked", self._on_move_slot_up)
        btn_vbox.pack_start(btn_up, False, False, 0)
        btn_down = Gtk.Button(label="Move Down")
        btn_down.connect("clicked", self._on_move_slot_down)
        btn_vbox.pack_start(btn_down, False, False, 0)
        team_hbox.pack_start(btn_vbox, False, False, 0)

        # Configured slots (right)
        slots_frame = Gtk.Frame(label="Configured Slots (OBS Order)")
        slots_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        slots_vbox.set_margin_start(4)
        slots_vbox.set_margin_end(4)
        slots_vbox.set_margin_top(4)
        slots_vbox.set_margin_bottom(4)

        self._slots_listbox = Gtk.ListBox()
        self._slots_listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        slots_scroll = Gtk.ScrolledWindow()
        slots_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        slots_scroll.set_size_request(-1, 150)
        slots_scroll.add(self._slots_listbox)
        slots_vbox.pack_start(slots_scroll, True, True, 0)
        slots_frame.add(slots_vbox)
        team_hbox.pack_start(slots_frame, True, True, 0)

        vbox.pack_start(team_hbox, False, False, 0)

        # Populate configured slots from config
        for s in config.get("team", {}).get("slots", []):
            self._slots_listbox.add(self._make_slot_row(s))
        self._slots_listbox.show_all()

        # ── Save button ─────────────────────────────────────────────
        save_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        save_box.set_margin_top(12)

        btn_save = Gtk.Button(label="Save & Restart")
        btn_save.get_style_context().add_class("suggested-action")
        btn_save.connect("clicked", self._on_save)
        save_box.pack_end(btn_save, False, False, 0)

        self._save_status_label = Gtk.Label(label="")
        self._save_status_label.set_xalign(0)
        save_box.pack_start(self._save_status_label, True, True, 0)

        vbox.pack_start(save_box, False, False, 0)

        scrolled.add(vbox)
        return scrolled

    def _section_header(self, text: str) -> Gtk.Label:
        label = Gtk.Label()
        label.set_markup(f'<span weight="bold" size="large">{text}</span>')
        label.set_xalign(0)
        return label

    def _make_slot_row(self, position_name: str) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        row.add(Gtk.Label(label=position_name, xalign=0))
        row._position_name = position_name
        return row

    # ── Settings: PCO test ──────────────────────────────────────────

    def _on_test_pco(self, _button):
        self._pco_status_label.set_text("Testing...")
        app_id = self._entry_app_id.get_text().strip()
        secret = self._entry_secret.get_text().strip()

        def _test():
            from src.pco_client import PCOClient
            client = PCOClient(app_id=app_id, secret=secret)
            ok, msg = client.test_connection()
            GLib.idle_add(self._pco_status_label.set_text, msg)

        threading.Thread(target=_test, daemon=True).start()

    # ── Settings: Fetch folders ─────────────────────────────────────

    def _on_fetch_folders(self, _button):
        self._pco_status_label.set_text("Fetching folders...")
        app_id = self._entry_app_id.get_text().strip()
        secret = self._entry_secret.get_text().strip()

        def _fetch():
            from src.pco_client import PCOClient
            client = PCOClient(app_id=app_id, secret=secret)
            try:
                folders = client.get_folders()
                GLib.idle_add(self._populate_folder_combo, folders)
            except Exception as e:
                GLib.idle_add(self._pco_status_label.set_text, f"Error: {e}")

        threading.Thread(target=_fetch, daemon=True).start()

    def _populate_folder_combo(self, folders):
        self._folder_combo.remove_all()
        for f in folders:
            self._folder_combo.append(f["id"], f"{f['name']} (ID: {f['id']})")
        if folders:
            # Try to select previously configured folder
            if self._folder_id_manual and not self._folder_combo.set_active_id(self._folder_id_manual):
                self._folder_combo.set_active(0)
            else:
                self._folder_combo.set_active(0)
            self._pco_status_label.set_text(f"Found {len(folders)} folders")
        else:
            self._pco_status_label.set_text("No folders found")

    def _on_folder_changed(self, combo):
        folder_id = combo.get_active_id()
        if not folder_id:
            return
        app_id = self._entry_app_id.get_text().strip()
        secret = self._entry_secret.get_text().strip()

        def _fetch():
            from src.pco_client import PCOClient
            client = PCOClient(app_id=app_id, secret=secret)
            try:
                types = client.get_folder_service_types(folder_id)
                names = ", ".join(t["name"] for t in types)
                GLib.idle_add(
                    self._service_types_label.set_text,
                    f"Service types: {names}" if names else "No service types in this folder"
                )
            except Exception as e:
                GLib.idle_add(self._service_types_label.set_text, f"Error: {e}")

        threading.Thread(target=_fetch, daemon=True).start()

    # ── Settings: OBS test ──────────────────────────────────────────

    def _on_test_obs(self, _button):
        self._obs_status_label.set_text("Testing...")
        host = self._entry_obs_host.get_text().strip()
        port = int(self._spin_obs_port.get_value())
        password = self._entry_obs_password.get_text()

        def _test():
            try:
                import obsws_python as obs
                ws = obs.ReqClient(
                    host=host, port=port,
                    password=password if password else None,
                    timeout=5,
                )
                version = ws.get_version()
                ws.base_client.ws.close()
                GLib.idle_add(
                    self._obs_status_label.set_text,
                    f"Connected! OBS v{version.obs_version}"
                )
            except Exception as e:
                GLib.idle_add(self._obs_status_label.set_text, f"Error: {e}")

        threading.Thread(target=_test, daemon=True).start()

    # ── Settings: Team positions ────────────────────────────────────

    def _on_fetch_positions(self, _button):
        app_id = self._entry_app_id.get_text().strip()
        secret = self._entry_secret.get_text().strip()
        folder_id = self._folder_combo.get_active_id()
        if not folder_id:
            return

        def _fetch():
            from src.pco_client import PCOClient
            client = PCOClient(app_id=app_id, secret=secret)
            try:
                types = client.get_folder_service_types(folder_id)
                type_ids = [t["id"] for t in types]
                positions = client.get_team_positions_for_types(type_ids)
                GLib.idle_add(self._populate_available_positions, positions)
            except Exception as e:
                logger.warning("Failed to fetch positions: %s", e)

        threading.Thread(target=_fetch, daemon=True).start()

    def _populate_available_positions(self, positions):
        for child in self._avail_listbox.get_children():
            self._avail_listbox.remove(child)
        for pos in positions:
            row = Gtk.ListBoxRow()
            row.add(Gtk.Label(label=pos, xalign=0))
            row._position_name = pos
            self._avail_listbox.add(row)
        self._avail_listbox.show_all()

    def _on_add_slot(self, _button):
        row = self._avail_listbox.get_selected_row()
        if row:
            pos = row._position_name
            new_row = self._make_slot_row(pos)
            self._slots_listbox.add(new_row)
            self._slots_listbox.show_all()

    def _on_remove_slot(self, _button):
        row = self._slots_listbox.get_selected_row()
        if row:
            self._slots_listbox.remove(row)

    def _on_move_slot_up(self, _button):
        row = self._slots_listbox.get_selected_row()
        if row:
            idx = row.get_index()
            if idx > 0:
                self._slots_listbox.remove(row)
                self._slots_listbox.insert(row, idx - 1)
                self._slots_listbox.select_row(row)

    def _on_move_slot_down(self, _button):
        row = self._slots_listbox.get_selected_row()
        if row:
            idx = row.get_index()
            n = len(self._slots_listbox.get_children())
            if idx < n - 1:
                self._slots_listbox.remove(row)
                self._slots_listbox.insert(row, idx + 1)
                self._slots_listbox.select_row(row)

    # ── Settings: Save ──────────────────────────────────────────────

    def _on_save(self, _button):
        config = self._collect_config()
        errors = validate_config(config)
        if errors:
            self._save_status_label.set_markup(
                f'<span foreground="red">{GLib.markup_escape_text("; ".join(errors))}</span>'
            )
            return

        save_config(self.tray_app.config_path, config)
        self._save_status_label.set_markup(
            '<span foreground="#4ade80">Saved! Restarting engine...</span>'
        )
        self._welcome_banner.hide()

        # Restart engine in background
        def _restart():
            try:
                self.tray_app.restart_engine(config)
                GLib.idle_add(self._post_restart_success)
            except Exception as e:
                GLib.idle_add(
                    self._save_status_label.set_markup,
                    f'<span foreground="red">Restart failed: {GLib.markup_escape_text(str(e))}</span>'
                )

        threading.Thread(target=_restart, daemon=True).start()

    def _post_restart_success(self):
        self._save_status_label.set_markup(
            '<span foreground="#4ade80">Engine running!</span>'
        )
        # Refresh OBS reference tab with new slots
        self._refresh_obs_reference()
        # Switch to Live Status tab
        self.notebook.set_current_page(0)
        self._start_live_refresh()

    def _collect_config(self) -> dict:
        """Gather all settings fields into a config dict."""
        slots = []
        for row in self._slots_listbox.get_children():
            slots.append(row._position_name)

        return {
            "pco": {
                "app_id": self._entry_app_id.get_text().strip(),
                "secret": self._entry_secret.get_text().strip(),
                "folder_id": self._folder_combo.get_active_id() or "",
            },
            "obs": {
                "enabled": self._chk_obs_enabled.get_active(),
                "host": self._entry_obs_host.get_text().strip(),
                "port": int(self._spin_obs_port.get_value()),
                "password": self._entry_obs_password.get_text(),
                "update_interval_ms": int(self._spin_interval.get_value()),
            },
            "team": {
                "enabled": self._chk_team_enabled.get_active(),
                "photo_cache_dir": "",
                "placeholder_photo": "",
                "slots": slots,
            },
        }

    def _refresh_obs_reference(self):
        """Rebuild the OBS Reference tab with current slots."""
        page_num = 1  # OBS Reference is tab index 1
        old_page = self.notebook.get_nth_page(page_num)
        if old_page:
            self.notebook.remove_page(page_num)
        self._obs_ref_box = build_obs_reference_panel(slots=self._get_slots())
        self.notebook.insert_page(
            self._obs_ref_box, Gtk.Label(label="OBS Reference"), page_num
        )
        self._obs_ref_box.show_all()

    # ── Tab 4: Help ─────────────────────────────────────────────────

    def _build_help_tab(self) -> Gtk.ScrolledWindow:
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        vbox.set_margin_start(16)
        vbox.set_margin_end(16)
        vbox.set_margin_top(12)
        vbox.set_margin_bottom(12)

        title = Gtk.Label()
        title.set_markup('<span weight="bold" size="x-large">Setup Guide</span>')
        title.set_xalign(0)
        vbox.pack_start(title, False, False, 0)

        steps = [
            (
                "1. Create a PCO Personal Access Token",
                'Go to <a href="https://api.planningcenteronline.com/oauth/applications">'
                "api.planningcenteronline.com/oauth/applications</a>\n"
                "Click <b>New Personal Access Token</b>. Give it a name (e.g. \"OBS Timer\").\n"
                "Copy the <b>Application ID</b> and <b>Secret</b>.",
            ),
            (
                "2. Enter credentials in Settings",
                "Switch to the <b>Settings</b> tab.\n"
                "Paste the App ID and Secret into the PCO Connection fields.",
            ),
            (
                "3. Test PCO Connection",
                "Click <b>Test PCO Connection</b>. You should see "
                '"Connected! Found N service types".',
            ),
            (
                "4. Select a Folder",
                "Click <b>Fetch Folders</b> to load your PCO folders.\n"
                "Select the folder that contains your worship service types.\n"
                "The service types in that folder will be listed below.",
            ),
            (
                "5. Configure OBS Connection",
                "Enable OBS WebSocket in OBS: <b>Tools > WebSocket Server Settings</b>.\n"
                "The default port is 4455. Set a password if desired.\n"
                "Enter matching settings in the OBS Connection section.",
            ),
            (
                "6. Configure Team Positions",
                "Click <b>Fetch from PCO</b> to discover position names from your plans.\n"
                "Select positions on the left and click <b>Add >></b> to add OBS slots.\n"
                "Duplicates are allowed (e.g. two Vocalist slots for two singers).\n"
                "Use Move Up/Down to set the display order.",
            ),
            (
                "7. Save",
                "Click <b>Save & Restart</b>. The timer engine will start and the\n"
                "Live Status tab will show real-time data.\n"
                "Create the OBS text sources listed in the <b>OBS Reference</b> tab.",
            ),
        ]

        for heading, body in steps:
            h = Gtk.Label()
            h.set_markup(f'<span weight="bold">{heading}</span>')
            h.set_xalign(0)
            h.set_margin_top(8)
            vbox.pack_start(h, False, False, 0)

            b = Gtk.Label()
            b.set_markup(body)
            b.set_xalign(0)
            b.set_line_wrap(True)
            b.set_margin_start(16)
            vbox.pack_start(b, False, False, 0)

        scrolled.add(vbox)
        return scrolled
