#!/usr/bin/env python3
"""
Estimate the final mirror size by querying the PyPI JSON API for every package.

Fetches the full simple index, then queries each package's JSON in parallel
to sum filtered file sizes (cp310/abi3/none-any wheels, manylinux x86_64,
latest N releases). Takes ~30-60 min for all of PyPI at 50 workers.

Progress is checkpointed to size_estimate_checkpoint.json every 100 packages.
If the run is interrupted, re-run to resume. Use --reset to start over.
"""
import argparse
import json
import re
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table

from config import PYPI_MASTER, PYTHON_VERSION, KEEP_RELEASES
from generate_conf import allowlist_patterns

DEFAULT_WORKERS = 50
CHECKPOINT_FILE = Path("size_estimate_checkpoint.json")
DEFAULT_CHECKPOINT_INTERVAL = 1000  # save every N completions


def compile_patterns(python_version: str) -> list[re.Pattern]:
    return [re.compile(p) for p in allowlist_patterns(python_version)]


def matches_any(filename: str, patterns: list[re.Pattern]) -> bool:
    return any(p.match(filename) for p in patterns)


def latest_versions(releases: dict, keep: int) -> list[str]:
    def latest_upload(files):
        times = [f.get("upload_time", "") for f in files if f.get("upload_time")]
        return max(times) if times else ""

    ordered = sorted(releases.items(), key=lambda kv: latest_upload(kv[1]), reverse=True)
    return [v for v, _ in ordered[:keep]]


def fetch_package_names(master: str) -> list[str]:
    with urllib.request.urlopen(f"{master}/simple/", timeout=15) as r:
        html = r.read().decode()
    return re.findall(r'href="[^"]+">([^<]+)</a>', html)


def filtered_size(name: str, master: str, patterns: list[re.Pattern], keep: int) -> int:
    try:
        with urllib.request.urlopen(f"{master}/pypi/{name}/json", timeout=15) as r:
            data = json.loads(r.read())
    except Exception:
        return 0

    releases = data.get("releases", {})
    total = 0
    for version in latest_versions(releases, keep):
        for f in releases.get(version, []):
            if matches_any(f.get("filename", ""), patterns):
                total += f.get("size", 0)
    return total


def load_checkpoint() -> dict[str, int]:
    if CHECKPOINT_FILE.exists():
        return json.loads(CHECKPOINT_FILE.read_text())
    return {}


def save_checkpoint(data: dict[str, int]) -> None:
    CHECKPOINT_FILE.write_text(json.dumps(data))


def fmt(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                        help=f"parallel HTTP workers (default: {DEFAULT_WORKERS}; back off if PyPI rate-limits you)")
    parser.add_argument("--checkpoint-interval", type=int, default=DEFAULT_CHECKPOINT_INTERVAL,
                        help=f"save checkpoint every N packages (default: {DEFAULT_CHECKPOINT_INTERVAL})")
    parser.add_argument("--reset", action="store_true",
                        help="ignore existing checkpoint and start from scratch")
    args = parser.parse_args()

    console = Console()
    patterns = compile_patterns(PYTHON_VERSION)

    if args.reset and CHECKPOINT_FILE.exists():
        CHECKPOINT_FILE.unlink()
        console.print("[yellow]Checkpoint cleared — starting from scratch.[/yellow]\n")

    checkpoint = load_checkpoint()
    if checkpoint:
        console.print(f"[yellow]Resuming from checkpoint:[/yellow] {len(checkpoint):,} packages already done\n")

    with console.status("Fetching package list from PyPI..."):
        packages = fetch_package_names(PYPI_MASTER)
    total = len(packages)
    remaining = [p for p in packages if p not in checkpoint]
    console.print(f"[bold]{total:,}[/bold] packages total — "
                  f"[bold]{len(remaining):,}[/bold] remaining — "
                  f"{args.workers} workers\n")

    total_bytes = sum(checkpoint.values())
    checkpoint_lock = threading.Lock()
    since_last_save = 0

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=40),
        MofNCompleteColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        TextColumn("[cyan]{task.fields[running_total]}"),
        console=console,
        refresh_per_second=5,
    )

    with progress:
        task = progress.add_task(
            f"[green]Scanning PyPI (py{PYTHON_VERSION}, keep={KEEP_RELEASES})",
            total=total,
            completed=len(checkpoint),
            running_total=fmt(total_bytes),
        )
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {
                pool.submit(filtered_size, name, PYPI_MASTER, patterns, KEEP_RELEASES): name
                for name in remaining
            }
            for future in as_completed(futures):
                name = futures[future]
                size = future.result()
                with checkpoint_lock:
                    total_bytes += size
                    checkpoint[name] = size
                    since_last_save += 1
                    if since_last_save >= args.checkpoint_interval:
                        save_checkpoint(checkpoint)
                        since_last_save = 0
                progress.advance(task)
                progress.update(task, running_total=fmt(total_bytes))

    save_checkpoint(checkpoint)

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_row("[bold]Packages queried[/bold]", f"{total:,}")
    table.add_row("[bold]Python version[/bold]", PYTHON_VERSION)
    table.add_row("[bold]Releases kept[/bold]", str(KEEP_RELEASES))
    table.add_row("[bold]Estimated size[/bold]", f"[bold green]{fmt(total_bytes)}[/bold green]")
    console.print("\n[bold]Results[/bold]")
    console.print(table)
    console.print(f"\n[dim]Checkpoint saved to {CHECKPOINT_FILE} — use --reset to start over.[/dim]")


if __name__ == "__main__":
    main()
