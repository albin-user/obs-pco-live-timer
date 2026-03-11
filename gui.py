#!/usr/bin/env python3
"""
PCO Live Timer — System Tray GUI (Xubuntu / XFCE)

Alternative entry point to run.py. Provides a system tray icon and
configuration window instead of headless CLI operation.

Requirements (Xubuntu 24.04):
    sudo apt install python3-gi gir1.2-appindicator3-0.1 gir1.2-gtk-3.0
"""
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


def main():
    try:
        import gi
        gi.require_version("Gtk", "3.0")
        gi.require_version("AppIndicator3", "0.1")
    except (ImportError, ValueError) as e:
        logger.error(
            "GTK3 or AppIndicator3 not available: %s\n"
            "Install with: sudo apt install python3-gi "
            "gir1.2-appindicator3-0.1 gir1.2-gtk-3.0",
            e,
        )
        sys.exit(1)

    from gi.repository import Gtk

    logger.info("Starting PCO Live Timer GUI")
    from src.gui.tray_app import TrayApp

    app = TrayApp()

    try:
        Gtk.main()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt — shutting down")
        app.stop_engine()


if __name__ == "__main__":
    main()
