#!/usr/bin/env python3
"""
Veloce Benchmark Suite
Executes end-to-end performance transfer tests across 12 distinct international CDN,
cloud storage, and media streaming sources to measure single-stream vs. Veloce 16-connection dynamic engine throughput.
"""

import os
import sys
import time
import shutil
import urllib.request
from typing import Dict, List, Tuple

# Add repository root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.segmenter import DownloadTask

BENCHMARK_TARGETS = [
    {
        "name": "Amazon S3 (GitHub Release)",
        "type": "Release Binary (S3)",
        "url": "https://github.com/git-for-windows/git/releases/download/v2.44.0.windows.1/Git-2.44.0-64-bit.tar.bz2",
        "filename": "git_s3.tar.bz2",
        "max_bytes": 25 * 1024 * 1024
    },
    {
        "name": "Internet Archive (Big Buck Bunny)",
        "type": "HD Video (MP4)",
        "url": "https://archive.org/download/BigBuckBunny_124/Content/big_buck_bunny_720p_surround.mp4",
        "filename": "bunny_720p.mp4",
        "max_bytes": 20 * 1024 * 1024
    },
    {
        "name": "SoundHelix Audio Master 1",
        "type": "Audio Track (MP3)",
        "url": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3",
        "filename": "soundhelix_1.mp3"
    },
    {
        "name": "SoundHelix Audio Master 2",
        "type": "Audio Track (MP3)",
        "url": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-2.mp3",
        "filename": "soundhelix_2.mp3"
    },
    {
        "name": "Free Music Archive Track",
        "type": "Studio Audio (MP3)",
        "url": "https://files.freemusicarchive.org/storage-freemusicarchive-org/music/WFMU/Broke_For_Free/Directionless_EP/Broke_For_Free_-_01_-_Night_Owl.mp3",
        "filename": "fma_night_owl.mp3"
    },
    {
        "name": "Fastly CDN (Python Source)",
        "type": "Software Archive",
        "url": "https://www.python.org/ftp/python/3.11.8/Python-3.11.8.tar.xz",
        "filename": "python_fastly.tar.xz"
    },
    {
        "name": "Mozilla CDN (Firefox Package)",
        "type": "Application Binary",
        "url": "https://download-installer.cdn.mozilla.net/pub/firefox/releases/124.0/linux-x86_64/en-US/firefox-124.0.tar.bz2",
        "filename": "firefox_pkg.tar.bz2",
        "max_bytes": 25 * 1024 * 1024
    },
    {
        "name": "Apache Foundation Archive",
        "type": "Server Package",
        "url": "https://archive.apache.org/dist/httpd/httpd-2.4.58.tar.gz",
        "filename": "apache_httpd.tar.gz"
    },
    {
        "name": "Kernel.org CDN",
        "type": "Kernel Archive",
        "url": "https://cdn.kernel.org/pub/linux/kernel/v6.x/patch-6.8.xz",
        "filename": "kernel_patch.xz"
    },
    {
        "name": "OVH Telecom Datacenter (FR)",
        "type": "Datacenter Mirror",
        "url": "http://proof.ovh.net/files/10Mb.dat",
        "filename": "ovh_10mb.dat"
    },
    {
        "name": "Cloudflare Anycast Speedtest",
        "type": "Edge CDN Payload",
        "url": "https://speed.cloudflare.com/__down?bytes=10000000",
        "filename": "cloudflare_10mb.bin"
    },
    {
        "name": "Canonical Ubuntu Mirror",
        "type": "Distribution Mirror",
        "url": "https://releases.ubuntu.com/22.04/ubuntu-22.04.5-desktop-amd64.iso.zsync",
        "filename": "ubuntu_zsync.dat"
    }
]

import tempfile
TMP_DIR = os.path.join(tempfile.gettempdir(), "veloce_benchmarks")


def benchmark_single_stream(url: str, output_path: str, max_bytes: int = None) -> Tuple[float, float, int]:
    """Measures single-stream browser baseline download."""
    start_time = time.time()
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    bytes_downloaded = 0
    with urllib.request.urlopen(req, timeout=25) as resp, open(output_path, "wb") as f:
        while True:
            chunk = resp.read(64 * 1024)
            if not chunk:
                break
            f.write(chunk)
            bytes_downloaded += len(chunk)
            if max_bytes and bytes_downloaded >= max_bytes:
                break
    elapsed = max(time.time() - start_time, 0.001)
    mb = bytes_downloaded / (1024 * 1024)
    speed_mb_s = mb / elapsed
    return elapsed, speed_mb_s, bytes_downloaded


def benchmark_veloce(url: str, output_path: str) -> Tuple[float, float, int]:
    """Measures the Veloce engine (adaptive, up to 16 connections)."""
    start_time = time.time()
    task = DownloadTask(
        url=url,
        output_path=output_path,
        num_connections=16
    )
    task.start()
    elapsed = max(time.time() - start_time, 0.001)
    bytes_downloaded = os.path.getsize(task.output_path) if os.path.exists(task.output_path) else 0
    mb = bytes_downloaded / (1024 * 1024)
    speed_mb_s = mb / elapsed
    return elapsed, speed_mb_s, bytes_downloaded


def main():
    os.makedirs(TMP_DIR, exist_ok=True)
    results = []

    print("\n" + "=" * 80)
    print("  VELOCE MULTI-STREAM ENGINE BENCHMARK SUITE (12 DIVERSE SOURCES)")
    print("  Comparing Single-Stream Browser vs. Veloce Dynamic 16x Work-Stealing Engine")
    print("=" * 80 + "\n")

    for i, target in enumerate(BENCHMARK_TARGETS, 1):
        name = target["name"]
        ttype = target["type"]
        url = target["url"]
        fname = target["filename"]

        single_out = os.path.join(TMP_DIR, f"single_{fname}")
        veloce_out = os.path.join(TMP_DIR, f"veloce_{fname}")

        print(f"[{i:02d}/12] Benchmarking: {name} ({ttype})")
        sys.stdout.write("       -> Single Stream (Browser): ")
        sys.stdout.flush()

        single_speed = 0.0
        single_elapsed = 0.0
        try:
            single_elapsed, single_speed, single_bytes = benchmark_single_stream(url, single_out, target.get("max_bytes"))
            print(f"{single_speed:.2f} MB/s ({single_elapsed:.2f}s, {single_bytes / (1024*1024):.1f} MB)")
        except Exception as e:
            # Never substitute a made-up baseline: that would inflate the speedup. Skip the source.
            print(f"FAILED ({e}) — skipping this source")
            continue

        sys.stdout.write("       -> Veloce Engine (16x):     ")
        sys.stdout.flush()

        veloce_speed = 0.0
        veloce_elapsed = 0.0
        try:
            veloce_elapsed, veloce_speed, veloce_bytes = benchmark_veloce(url, veloce_out)
            speedup = (veloce_speed / single_speed) if single_speed > 0 else 1.0
            print(f"{veloce_speed:.2f} MB/s ({veloce_elapsed:.2f}s, {veloce_bytes / (1024*1024):.1f} MB) => {speedup:.1f}x")
            results.append({
                "source": name,
                "type": ttype,
                "size_mb": veloce_bytes / (1024 * 1024),
                "single_speed": single_speed,
                "single_time": single_elapsed,
                "veloce_speed": veloce_speed,
                "veloce_time": veloce_elapsed,
                "speedup": speedup
            })
        except Exception as e:
            print(f"FAILED ({e})")

        # Cleanup
        if os.path.exists(single_out):
            try: os.remove(single_out)
            except: pass
        if os.path.exists(veloce_out):
            try: os.remove(veloce_out)
            except: pass

    shutil.rmtree(TMP_DIR, ignore_errors=True)

    print("\n" + "=" * 80)
    print("  FINAL 12-SOURCE BENCHMARK RESULTS")
    print("=" * 80)
    print("\n| # | Source & Platform | Payload Type | Payload Size | Single Stream (Browser) | Veloce 16x Turbo | Speedup Multiplier |")
    print("| :-: | :--- | :--- | :--- | :--- | :--- | :--- |")
    for idx, r in enumerate(results, 1):
        print(f"| {idx:02d} | **{r['source']}** | {r['type']} | {r['size_mb']:.1f} MB | {r['single_speed']:.2f} MB/s ({r['single_time']:.1f}s) | **{r['veloce_speed']:.2f} MB/s** ({r['veloce_time']:.1f}s) | **{r['speedup']:.1f}x** |")

    avg_speedup = sum(r['speedup'] for r in results) / len(results) if results else 0
    avg_veloce = sum(r['veloce_speed'] for r in results) / len(results) if results else 0
    print(f"\n[SUMMARY] Evaluated {len(results)}/12 sources. Average Veloce Throughput: {avg_veloce:.2f} MB/s. Average Speedup: {avg_speedup:.1f}x.\n")


if __name__ == "__main__":
    main()
