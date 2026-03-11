"""
OBS Source Reference panel — table of all OBS source names with copy-to-clipboard buttons.
"""
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk


# Fixed sources that are always present
FIXED_SOURCES = [
    ("PCO Countdown", "Item countdown timer (MM:SS)", "Text (FreeType2)"),
    ("PCO Current Title", "Current item name", "Text (FreeType2)"),
    ("PCO Current Description", "Item description / song keys", "Text (FreeType2)"),
    ("PCO Item Length", "Current item total length", "Text (FreeType2)"),
    ("PCO Next Title", "Next item name", "Text (FreeType2)"),
    ("PCO Next Length", "Next item length in parentheses", "Text (FreeType2)"),
    ("PCO Service Type", "Service type name (uppercase)", "Text (FreeType2)"),
    ("PCO Service Date", "Service date and start time", "Text (FreeType2)"),
    ("PCO Plan Title", "Plan title in quotes", "Text (FreeType2)"),
    ("PCO Progress", "Item progress (e.g. 4 of 12)", "Text (FreeType2)"),
    ("PCO Service End", "Service end status with color", "Text (FreeType2)"),
]


def build_obs_reference_panel(slots=None) -> Gtk.Box:
    """Build the OBS Reference tab content."""
    vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    vbox.set_margin_start(12)
    vbox.set_margin_end(12)
    vbox.set_margin_top(12)
    vbox.set_margin_bottom(12)

    # Header note
    note = Gtk.Label()
    note.set_markup(
        '<span size="small">'
        "Create these as <b>Text (FreeType2)</b> sources in OBS. "
        "Names are case-sensitive. Photo sources should be <b>Image</b> sources. "
        "Missing sources are silently skipped."
        "</span>"
    )
    note.set_line_wrap(True)
    note.set_xalign(0)
    vbox.pack_start(note, False, False, 0)

    # Scrolled window for the table
    scrolled = Gtk.ScrolledWindow()
    scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scrolled.set_vexpand(True)

    # Build the table as a ListBox for easy updates
    listbox = Gtk.ListBox()
    listbox.set_selection_mode(Gtk.SelectionMode.NONE)

    # Header row
    header = _make_row("<b>Source Name</b>", "<b>Description</b>", "<b>Type</b>", is_header=True)
    listbox.add(header)

    # Fixed sources
    for name, desc, src_type in FIXED_SOURCES:
        row = _make_row(name, desc, src_type)
        listbox.add(row)

    # Team sources from slots
    if slots:
        # Separator
        sep_row = Gtk.ListBoxRow()
        sep_row.set_selectable(False)
        sep_label = Gtk.Label()
        sep_label.set_markup('<span weight="bold">Team Member Sources</span>')
        sep_label.set_xalign(0)
        sep_label.set_margin_top(8)
        sep_label.set_margin_bottom(4)
        sep_label.set_margin_start(6)
        sep_row.add(sep_label)
        listbox.add(sep_row)

        position_count = {}
        for pos in slots:
            idx = position_count.get(pos, 0)
            position_count[pos] = idx + 1
            num = idx + 1
            name_src = f"PCO Position {pos} {num} Name"
            pos_src = f"PCO Position {pos} {num} Position"
            photo_src = f"PCO Position {pos} {num} Photo"
            listbox.add(_make_row(name_src, f"{pos} #{num} first name", "Text (FreeType2)"))
            listbox.add(_make_row(pos_src, f"{pos} #{num} position title", "Text (FreeType2)"))
            listbox.add(_make_row(photo_src, f"{pos} #{num} photo", "Image"))

    scrolled.add(listbox)
    vbox.pack_start(scrolled, True, True, 0)

    # Store listbox reference for refreshing
    vbox._listbox = listbox
    return vbox


def _make_row(name: str, description: str, source_type: str, is_header: bool = False) -> Gtk.ListBoxRow:
    row = Gtk.ListBoxRow()
    row.set_selectable(False)
    hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    hbox.set_margin_start(6)
    hbox.set_margin_end(6)
    hbox.set_margin_top(3)
    hbox.set_margin_bottom(3)

    if is_header:
        lbl_name = Gtk.Label()
        lbl_name.set_markup(name)
        lbl_name.set_xalign(0)
        lbl_name.set_size_request(280, -1)
        hbox.pack_start(lbl_name, False, False, 0)

        lbl_desc = Gtk.Label()
        lbl_desc.set_markup(description)
        lbl_desc.set_xalign(0)
        hbox.pack_start(lbl_desc, True, True, 0)

        lbl_type = Gtk.Label()
        lbl_type.set_markup(source_type)
        lbl_type.set_xalign(0)
        lbl_type.set_size_request(130, -1)
        hbox.pack_start(lbl_type, False, False, 0)

        # Spacer for copy button column
        hbox.pack_start(Gtk.Label(label=""), False, False, 30)
    else:
        lbl_name = Gtk.Label(label=name)
        lbl_name.set_xalign(0)
        lbl_name.set_selectable(True)
        lbl_name.set_size_request(280, -1)
        hbox.pack_start(lbl_name, False, False, 0)

        lbl_desc = Gtk.Label(label=description)
        lbl_desc.set_xalign(0)
        hbox.pack_start(lbl_desc, True, True, 0)

        lbl_type = Gtk.Label(label=source_type)
        lbl_type.set_xalign(0)
        lbl_type.set_size_request(130, -1)
        hbox.pack_start(lbl_type, False, False, 0)

        btn = Gtk.Button(label="Copy")
        btn.connect("clicked", _on_copy_clicked, name)
        hbox.pack_start(btn, False, False, 0)

    row.add(hbox)
    return row


def _on_copy_clicked(_button, source_name: str):
    clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
    clipboard.set_text(source_name, -1)
    clipboard.store()
