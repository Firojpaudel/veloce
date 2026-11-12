"""
System-tray icon for the Veloce desktop app (optional: needs `pystray` + `Pillow`).

The tray is how people know the engine is running. Its tooltip shows live activity, and the menu
offers the few things anyone needs: open the dashboard, open the downloads folder, toggle start at
login, quit. When pystray isn't available (or there is no desktop session), the caller falls back
to running headless.
"""

import logging
import os
import threading
import time
from typing import Callable

logger = logging.getLogger("VeloceTray")

LOGO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui", "logo.png")


def _fmt_speed(bps: float) -> str:
    for unit in ("B/s", "KB/s", "MB/s", "GB/s"):
        if bps < 1024:
            return f"{bps:.1f} {unit}" if unit != "B/s" else f"{int(bps)} {unit}"
        bps /= 1024
    return f"{bps:.1f} TB/s"


def run_tray(open_dashboard: Callable[[], None], open_folder: Callable[[], None],
             on_quit: Callable[[], None], activity: Callable[[], tuple]) -> bool:
    """
    Blocks running the tray icon until the user picks Quit. Returns False immediately if a tray
    can't be shown on this system, so the caller can keep the engine running another way.
    `activity()` returns (active_download_count, total_bytes_per_second).
    """
    try:
        import pystray
        from PIL import Image
    except Exception as e:
        logger.info(f"System tray unavailable ({e}); running without a tray icon")
        return False

    from . import autostart

    def toggle_autostart(icon, item):
        try:
            autostart.disable() if autostart.is_enabled() else autostart.enable()
        except Exception as e:
            logger.warning(f"Couldn't change start-at-login: {e}")
        icon.update_menu()

    def quit_app(icon, item):
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem("Open Veloce", lambda icon, item: open_dashboard(), default=True),
        pystray.MenuItem("Open downloads folder", lambda icon, item: open_folder()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Start at login", toggle_autostart, checked=lambda item: autostart.is_enabled()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit Veloce", quit_app),
    )
    try:
        image = Image.open(LOGO)
        icon = pystray.Icon("veloce", image, "Veloce", menu)
    except Exception as e:
        logger.info(f"Couldn't create tray icon ({e})")
        return False

    stop = threading.Event()

    def update_tooltip():
        while not stop.wait(2.0):
            try:
                active, speed = activity()
                icon.title = (f"Veloce — {active} download{'s' if active != 1 else ''} · {_fmt_speed(speed)}"
                              if active else "Veloce — ready")
            except Exception:
                pass

    threading.Thread(target=update_tooltip, daemon=True).start()
    try:
        icon.run()
    except Exception as e:
        logger.info(f"Tray icon failed ({e})")
        stop.set()
        return False
    stop.set()
    on_quit()
    return True
