"""
Command-Line Interface for the Veloce download accelerator.

  veloce                      start the engine (same as `veloce daemon`)
  veloce download URL         accelerated download with a live progress bar
  veloce daemon [--background]
  veloce autostart enable|disable|status
"""

import argparse
import logging
import os
import socket
import sys


def format_bytes(num_bytes: float) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:3.2f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.2f} PB"


def print_progress(data: dict):
    percent = data.get("percent", 0.0)
    speed = data.get("speed", 0.0)
    downloaded = data.get("downloaded", 0)
    total = data.get("total_size", 0)
    eta = data.get("eta", 0)
    status = data.get("status", "")

    bar_width = 30
    filled = int(bar_width * percent / 100) if percent > 0 else 0
    bar = "█" * filled + "░" * (bar_width - filled)

    speed_str = f"{format_bytes(speed)}/s"
    downloaded_str = f"{format_bytes(downloaded)} / {format_bytes(total)}" if total > 0 else format_bytes(downloaded)
    eta_str = f"ETA {int(eta)}s" if eta > 0 else ""

    sys.stdout.write(f"\r[{status:<11}] {bar} {percent:5.1f}% | {downloaded_str} | {speed_str} | {eta_str}   ")
    sys.stdout.flush()


def run_download(url: str, output_path: str = None, connections: int = 16):
    from engine.segmenter import DownloadTask

    if not output_path:
        output_path = os.path.join(os.path.expanduser("~/Downloads"), "veloce")
        os.makedirs(output_path, exist_ok=True)

    print(f"\n[INFO] Target: {url}")
    print(f"[INFO] Concurrent connections: {connections}")

    task = DownloadTask(url=url, output_path=output_path, num_connections=connections,
                        progress_callback=print_progress)
    try:
        task.start()
        print(f"\n\n[OK] Saved to {task.output_path}")
    except KeyboardInterrupt:
        task.pause()
        print(f"\n\n[PAUSED] Partial file kept at {task.output_path}")
    except Exception as e:
        print(f"\n\n[ERROR] {e}")
        sys.exit(1)


def port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def enter_background_mode():
    """Detach from any console and send output to ~/.veloce/engine.log."""
    if sys.platform == "win32":
        try:
            import ctypes
            hwnd = ctypes.windll.kernel32.GetConsoleWindow()
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE
        except Exception:
            pass
    log_dir = os.path.expanduser(os.environ.get("VELOCE_HOME", "~/.veloce"))
    os.makedirs(log_dir, exist_ok=True)
    log = open(os.path.join(log_dir, "engine.log"), "a", buffering=1, encoding="utf-8")
    sys.stdout = sys.stderr = log
    logging.basicConfig(stream=log, level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", force=True)


def run_daemon(host: str, port: int):
    """Headless engine in the foreground (servers, terminals, debugging)."""
    if port_in_use(host, port):
        print(f"[OK] Veloce engine is already running on {host}:{port}.")
        return
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    from engine.server import run_server
    try:
        run_server(port=port, host=host)
    except OSError as e:
        print(f"\n[ERROR] Failed to start engine: {e}")
        sys.exit(1)


def run_app(port: int = 9229, background: bool = False):
    """
    The desktop app: engine + system-tray icon + dashboard.
      - Launched again while running → just opens the dashboard (no second instance).
      - background=True (start-at-login) → quietly sits in the tray; nothing opens.
      - First launch ever → opens the dashboard, which offers start-at-login (opt-in).
    """
    import threading
    import webbrowser

    host = "127.0.0.1"
    dashboard = f"http://{host}:{port}/"
    if port_in_use(host, port):
        if not background:
            webbrowser.open(dashboard)
        print(f"[OK] Veloce is already running — opened {dashboard}")
        return

    if background or sys.stdout is None:  # no console (start-at-login, or a windowed build)
        enter_background_mode()
    else:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    from engine.server import create_server, reveal_in_explorer, STORE, DEFAULT_DOWNLOAD_DIR
    try:
        httpd = create_server(port=port, host=host)
    except OSError as e:
        print(f"[ERROR] Failed to start engine: {e}")
        sys.exit(1)
    server_thread = threading.Thread(target=httpd.serve_forever, name="engine", daemon=True)
    server_thread.start()

    marker = os.path.join(os.path.expanduser(os.environ.get("VELOCE_HOME", "~/.veloce")), ".first-run-done")
    first_run = not os.path.exists(marker)
    if first_run:
        os.makedirs(os.path.dirname(marker), exist_ok=True)
        open(marker, "w").close()
    if not background or first_run:
        webbrowser.open(dashboard)

    def activity():
        tasks = STORE.list_tasks()
        running = [t for t in tasks if t.get("status") in ("QUEUED", "INITIALIZING", "DOWNLOADING")]
        return len(running), sum(t.get("speed") or 0 for t in running)

    def shutdown():
        httpd.shutdown()
        httpd.server_close()

    from engine.tray import run_tray
    if run_tray(open_dashboard=lambda: webbrowser.open(dashboard),
                open_folder=lambda: reveal_in_explorer(DEFAULT_DOWNLOAD_DIR),
                on_quit=shutdown, activity=activity):
        return

    # No tray available: keep running until Ctrl+C / logout
    print(f"[OK] Veloce is running — dashboard at {dashboard}  (Ctrl+C to quit)", flush=True)
    try:
        while server_thread.is_alive():
            server_thread.join(1.0)
    except KeyboardInterrupt:
        print("\n[INFO] Stopping Veloce...", flush=True)
        shutdown()


def main():
    parser = argparse.ArgumentParser(prog="veloce", description="Veloce dynamic multi-connection downloader")
    subparsers = parser.add_subparsers(dest="command")

    dl = subparsers.add_parser("download", help="Download a URL with dynamic segmentation")
    dl.add_argument("url", help="Target URL to download")
    dl.add_argument("-o", "--output", help="Destination file or directory path", default=None)
    dl.add_argument("-c", "--connections", type=int, default=16, help="Concurrent connections (1-32, default 16)")

    app = subparsers.add_parser("app", help="Start the desktop app: engine, tray icon and dashboard (default)")
    app.add_argument("--background", action="store_true",
                     help="Start quietly in the tray (used for start-at-login); log to ~/.veloce/engine.log")
    app.add_argument("--port", type=int, default=9229)

    daemon = subparsers.add_parser("daemon", help="Run the engine headless in this terminal")
    daemon.add_argument("--port", type=int, default=9229, help="Listen port (default: 9229)")
    daemon.add_argument("--host", default="127.0.0.1", help="Listen address (default: 127.0.0.1)")
    daemon.add_argument("--background", action="store_true", help=argparse.SUPPRESS)  # old autostart entries

    auto = subparsers.add_parser("autostart", help="Start the engine automatically when you log in")
    auto.add_argument("action", choices=["enable", "disable", "status"])

    if len(sys.argv) > 1 and sys.argv[1] == "media-worker":  # internal: out-of-process yt-dlp job
        from engine.media_worker import worker_main
        worker_main()
        return
    if sys.stdout is None:  # windowed build (no console): keep output in the log file
        enter_background_mode()
    args = parser.parse_args()

    if args.command == "download":
        logging.basicConfig(level=logging.WARNING)
        run_download(args.url, args.output, max(1, min(args.connections, 32)))
    elif args.command == "app":
        run_app(port=args.port, background=args.background)
    elif args.command == "daemon":
        if args.background:  # start-at-login entries written by v1.1 pre-releases
            run_app(port=args.port, background=True)
        else:
            run_daemon(args.host, args.port)
    elif args.command == "autostart":
        from engine import autostart
        if args.action == "enable":
            print(f"[OK] {autostart.enable()}")
            print("[OK] Veloce will start in the background every time you log in.")
        elif args.action == "disable":
            print(f"[OK] {autostart.disable()}")
        else:
            print("enabled" if autostart.is_enabled() else "disabled")
    else:
        # Double-clicked or launched without arguments: the desktop app
        run_app()


if __name__ == "__main__":
    main()
