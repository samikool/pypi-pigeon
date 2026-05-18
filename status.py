#!/usr/bin/env python3
"""Quick status check for the running bandersnatch mirror."""
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path

from config import MIRROR_DIR, PYPI_MASTER


def get_pypi_total():
    result = subprocess.run(
        ["curl", "-s", f"{PYPI_MASTER}/simple/"],
        capture_output=True, text=True, timeout=15
    )
    return result.stdout.count("href=")


def get_bandersnatch_pid():
    result = subprocess.run(
        ["pgrep", "-f", "bandersnatch.*mirror"],
        capture_output=True, text=True
    )
    pids = result.stdout.strip().splitlines()
    return int(pids[0]) if pids else None


def get_process_info(pid):
    result = subprocess.run(
        ["ps", "-p", str(pid), "-o", "lstart=,etime=,pcpu="],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return None
    parts = result.stdout.strip()
    # lstart is 24 chars, then etime, then pcpu
    lstart_str = parts[:24].strip()
    rest = parts[24:].split()
    etime_str = rest[0] if rest else "0"
    pcpu = rest[1] if len(rest) > 1 else "?"

    start_time = datetime.strptime(lstart_str, "%a %b %d %H:%M:%S %Y")

    # etime format: [[DD-]HH:]MM:SS
    elapsed_seconds = 0
    etime_str = etime_str.strip()
    if "-" in etime_str:
        days, etime_str = etime_str.split("-", 1)
        elapsed_seconds += int(days) * 86400
    parts_t = etime_str.split(":")
    if len(parts_t) == 3:
        elapsed_seconds += int(parts_t[0]) * 3600 + int(parts_t[1]) * 60 + int(parts_t[2])
    elif len(parts_t) == 2:
        elapsed_seconds += int(parts_t[0]) * 60 + int(parts_t[1])

    return start_time, elapsed_seconds, pcpu


def main():
    simple_dir = Path(MIRROR_DIR) / "web" / "simple"
    if not simple_dir.exists():
        print(f"Mirror directory not found: {simple_dir}")
        return

    print("Fetching PyPI total package count...", end=" ", flush=True)
    total = get_pypi_total()
    print(f"{total:,}")

    done = sum(1 for _ in simple_dir.iterdir())
    pid = get_bandersnatch_pid()

    if not pid:
        print("\nbandersnatch is NOT running.")
        print(f"Packages mirrored: {done:,} / {total:,} ({done/total*100:.1f}%)")
        return

    info = get_process_info(pid)
    if not info:
        print(f"Could not read process info for PID {pid}")
        return

    start_time, elapsed_secs, pcpu = info
    elapsed_hours = elapsed_secs / 3600
    rate_per_hour = done / elapsed_hours if elapsed_hours > 0 else 0
    remaining = total - done
    eta_hours = remaining / rate_per_hour if rate_per_hour > 0 else float("inf")
    eta_time = datetime.now() + timedelta(hours=eta_hours)

    bar_width = 40
    filled = int(bar_width * done / total)
    bar = "#" * filled + "-" * (bar_width - filled)

    print(f"\n  PID {pid} — running since {start_time.strftime('%a %b %d %H:%M')} ({elapsed_hours:.1f}h), CPU {pcpu}%")
    print(f"\n  [{bar}] {done/total*100:.1f}%")
    print(f"  {done:,} / {total:,} packages")
    print(f"\n  Rate:      {rate_per_hour:,.0f} packages/hour")
    print(f"  Remaining: {remaining:,} packages")
    print(f"  ETA:       {eta_hours:.1f}h  ({eta_time.strftime('%a %b %d ~ %I:%M %p')})")


if __name__ == "__main__":
    main()
