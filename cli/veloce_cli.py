"""
Command-Line Interface for the Veloce Accelerated Downloader.
Displays real-time multi-threaded segment progress bars.
"""

import os
import sys
import time
import argparse
import urllib.request

from engine.segmenter import DownloadTask
from engine.server import run_server


def format_bytes(num_bytes: float) -> str:
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
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

    # Progress bar rendering
    bar_width = 30
    filled = int(bar_width * percent / 100) if percent > 0 else 0
    bar = "█" * filled + "░" * (bar_width - filled)

    speed_str = f"{format_bytes(speed)}/s"
    downloaded_str = f"{format_bytes(downloaded)} / {format_bytes(total)}" if total > 0 else format_bytes(downloaded)
    eta_str = f"ETA: {int(eta)}s" if eta > 0 else ""

    sys.stdout.write(f"\r⚡ [{status}] [{bar}] {percent:.1f}% | {downloaded_str} | {speed_str} | {eta_str}   ")
    sys.stdout.flush()


def run_download(url: str, output_path: str = None, connections: int = 16):
    if not output_path:
        output_path = os.path.expanduser("~/Downloads")

    print(f"\n🚀 Initializing Veloce Dynamic Engine: {url}")
    print(f"⚡ Allocated Connections: {connections}")

    task = DownloadTask(
        url=url,
        output_path=output_path,
        num_connections=connections,
        progress_callback=print_progress
    )

    try:
        task.start()
        print("\n\n✅ Download complete! Saved to:", task.output_path)
    except KeyboardInterrupt:
        task.pause()
        print("\n\n⏸️  Download paused by user.")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")


def main():
    parser = argparse.ArgumentParser(description="Veloce - High Performance Dynamic Multi-Stream Downloader")
    subparsers = parser.add_subparsers(dest="command")

    # Download command
    dl_parser = subparsers.add_parser("download", help="Accelerate URL download with dynamic multi-streaming")
    dl_parser.add_argument("url", help="URL of the target file to download")
    dl_parser.add_argument("-o", "--output", help="Destination file or directory path", default=None)
    dl_parser.add_argument("-c", "--connections", type=int, default=16, help="Concurrent dynamic connections (default: 16)")

    # Daemon command
    daemon_parser = subparsers.add_parser("daemon", help="Run background local API server for browser extension")
    daemon_parser.add_argument("--port", type=int, default=9229, help="Port to listen on (default: 9229)")
    daemon_parser.add_argument("--host", default="127.0.0.1", help="Host address (default: 127.0.0.1)")

    args = parser.parse_args()

    if args.command == "download":
        run_download(args.url, args.output, args.connections)
    elif args.command == "daemon":
        run_server(port=args.port, host=args.host)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
