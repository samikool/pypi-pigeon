"""pymirror dry-run — fetch PyPI metadata to estimate mirror size before committing to a full sync."""
from __future__ import annotations

import heapq
import json
import re
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Footer, Header, Label, ProgressBar, Rule, Static

from pymirror.config import Config, PYPI_MASTER, allowlist_patterns

CHECKPOINT_FILE = Path("pymirror_dryrun_checkpoint.json")
DEFAULT_WORKERS = 50
LEADERBOARD_SIZE = 20
_FLUSH_INTERVAL = 0.2


# ── Helpers (also imported by sync.py) ───────────────────────────────────────

def _compile_patterns(config: Config) -> list[re.Pattern]:
    return [re.compile(p) for p in allowlist_patterns(
        config.filter.python_versions,
        config.filter.platforms,
        config.filter.include_sdists,
    )]


def _matches_any(filename: str, patterns: list[re.Pattern]) -> bool:
    return any(p.match(filename) for p in patterns)


def _latest_versions(releases: dict, keep: int) -> list[str]:
    def latest_upload(files):
        times = [f.get("upload_time", "") for f in files if f.get("upload_time")]
        return max(times) if times else ""
    ordered = sorted(releases.items(), key=lambda kv: latest_upload(kv[1]), reverse=True)
    return [v for v, _ in ordered[:keep]]


def fetch_package_names() -> list[str]:
    with urllib.request.urlopen(f"{PYPI_MASTER}/simple/", timeout=30) as r:
        html = r.read().decode()
    return re.findall(r'href="[^"]+">([^<]+)</a>', html)


def filtered_size_breakdown(name: str, config: Config, patterns: list[re.Pattern]) -> dict[str, int]:
    try:
        with urllib.request.urlopen(f"{PYPI_MASTER}/pypi/{name}/json", timeout=15) as r:
            data = json.loads(r.read())
    except Exception:
        return {"cp": 0, "abi3": 0, "any": 0}

    keep = config.mirror.keep_releases
    result = {"cp": 0, "abi3": 0, "any": 0}
    for version in _latest_versions(data.get("releases", {}), keep):
        for f in data["releases"].get(version, []):
            filename = f.get("filename", "")
            if not _matches_any(filename, patterns):
                continue
            size = f.get("size", 0)
            if filename.endswith("-none-any.whl"):
                result["any"] += size
            elif "-abi3-" in filename:
                result["abi3"] += size
            else:
                result["cp"] += size
    return result


def load_checkpoint() -> dict[str, int]:
    if CHECKPOINT_FILE.exists():
        try:
            return json.loads(CHECKPOINT_FILE.read_text())
        except Exception:
            pass
    return {}


def save_checkpoint(data: dict[str, int]) -> None:
    CHECKPOINT_FILE.write_text(json.dumps(data))


def fmt(n: float) -> str:
    for unit, thresh in [("TB", 1e12), ("GB", 1e9), ("MB", 1e6), ("KB", 1e3)]:
        if n >= thresh:
            return f"{n / thresh:.1f} {unit}"
    return f"{n:.0f} B"


def _fmt_eta(secs: float) -> str:
    if secs == float("inf") or secs > 86400:
        return "—"
    h, rem = divmod(int(secs), 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


# ── Headless mode ────────────────────────────────────────────────────────────

def run_headless(config: Config, workers: int = DEFAULT_WORKERS, reset: bool = False) -> None:
    """Run dry-run without a TUI, printing progress to stdout."""
    if reset and CHECKPOINT_FILE.exists():
        CHECKPOINT_FILE.unlink()

    print("Fetching package list from PyPI…")
    packages = fetch_package_names()
    checkpoint = load_checkpoint()
    remaining = [p for p in packages if p not in checkpoint]
    total = len(packages)

    print(f"{total:,} packages total  •  {len(checkpoint):,} cached  •  {len(remaining):,} to fetch")

    if not remaining:
        print(f"Done (checkpoint complete)  •  Estimated size: {fmt(sum(checkpoint.values()))}")
        return

    patterns = _compile_patterns(config)
    total_bytes = sum(checkpoint.values())
    completed = len(checkpoint)
    since_save = 0
    checkpoint_lock = threading.Lock()
    start = time.monotonic()
    last_print = start

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(filtered_size_breakdown, name, config, patterns): name
            for name in remaining
        }
        for i, future in enumerate(as_completed(futures), 1):
            name = futures[future]
            bd = future.result()
            size = sum(bd.values())
            with checkpoint_lock:
                checkpoint[name] = size
                total_bytes += size
                completed += 1
                since_save += 1
                if since_save >= 1000:
                    save_checkpoint(checkpoint)
                    since_save = 0

            now = time.monotonic()
            if now - last_print >= 0.01 or i == len(remaining):
                elapsed = now - start
                rate = i / elapsed if elapsed > 0 else 0
                eta = (len(remaining) - i) / rate if rate > 0 else float("inf")
                print(
                    f"  {completed:,} / {total:,}  "
                    f"{rate:,.0f} pkg/s  ETA {_fmt_eta(eta)}  {fmt(total_bytes)}",
                    flush=True,
                )
                last_print = now

    save_checkpoint(checkpoint)
    print(f"\nDone!  {total:,} packages  •  Estimated mirror size: {fmt(total_bytes)}")


# ── CSS ───────────────────────────────────────────────────────────────────────

CSS = """
Screen { height: 100vh; }

#body { height: 1fr; }

#left {
    width: 44;
    padding: 1 2;
    border-right: solid $primary-darken-2;
}

#right { width: 1fr; padding: 1 2; }

#main-bar { width: 100%; margin-bottom: 1; }

#stats { color: $text-muted; margin-bottom: 1; }

#running-total { text-style: bold; margin-bottom: 1; }

#breakdown-title { color: $text-muted; margin-top: 1; margin-bottom: 1; }

.type-row { height: 3; }

.type-label {
    width: 6;
    content-align: left middle;
    color: $text-muted;
}

.type-bar { width: 1fr; }

.type-stat {
    width: 14;
    content-align: right middle;
    color: $text-muted;
}

#leaderboard-title { text-style: bold; margin-bottom: 1; }

#leaderboard { height: 1fr; }
"""


# ── App ───────────────────────────────────────────────────────────────────────

class DryRunApp(App):
    CSS = CSS
    TITLE = "pymirror — dry run"
    BINDINGS = [
        Binding("s", "go_sync", "Run sync now", show=False),
        Binding("q", "go_quit", "Quit"),
    ]

    def __init__(self, config: Config, workers: int = DEFAULT_WORKERS, reset: bool = False) -> None:
        super().__init__()
        self._config = config
        self._fetch_workers = workers
        self._reset = reset
        self.next_command: str | None = None

        self._total_packages = 0
        self._completed = 0
        self._this_run_completed = 0
        self._total_bytes = 0
        self._cp_bytes = 0
        self._abi3_bytes = 0
        self._any_bytes = 0
        self._heap: list[tuple[int, str]] = []

        self._pending: list[tuple[str, dict[str, int]]] = []
        self._pending_lock = threading.Lock()
        self._start_time = 0.0
        self._done = False
        self._stop = threading.Event()
        self._executor: ThreadPoolExecutor | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="body"):
            with Vertical(id="left"):
                yield ProgressBar(id="main-bar", show_eta=True)
                yield Static("Starting…", id="stats")
                yield Static("", id="running-total")
                yield Rule()
                yield Label("By wheel type", id="breakdown-title")
                with Horizontal(classes="type-row"):
                    yield Label("cp", classes="type-label")
                    yield ProgressBar(total=1, show_eta=False, show_percentage=False, id="cp-bar", classes="type-bar")
                    yield Static("", id="cp-stat", classes="type-stat")
                with Horizontal(classes="type-row"):
                    yield Label("abi3", classes="type-label")
                    yield ProgressBar(total=1, show_eta=False, show_percentage=False, id="abi3-bar", classes="type-bar")
                    yield Static("", id="abi3-stat", classes="type-stat")
                with Horizontal(classes="type-row"):
                    yield Label("any", classes="type-label")
                    yield ProgressBar(total=1, show_eta=False, show_percentage=False, id="any-bar", classes="type-bar")
                    yield Static("", id="any-stat", classes="type-stat")
            with Vertical(id="right"):
                yield Label("Top Packages by Size", id="leaderboard-title")
                yield DataTable(id="leaderboard", show_cursor=False)
        yield Footer()

    def on_mount(self) -> None:
        if self._reset and CHECKPOINT_FILE.exists():
            CHECKPOINT_FILE.unlink()

        table = self.query_one("#leaderboard", DataTable)
        table.add_column("", key="rank", width=4)
        table.add_column("Package", key="package", width=35)
        table.add_column("Size", key="size", width=12)
        for i in range(1, LEADERBOARD_SIZE + 1):
            table.add_row(str(i), "—", "—", key=str(i))

        self.set_interval(_FLUSH_INTERVAL, self._flush)
        self._run_dry_run()

    @work(thread=True)
    def _run_dry_run(self) -> None:
        self.call_from_thread(
            self.query_one("#stats", Static).update,
            "Fetching package list from PyPI…",
        )

        packages = fetch_package_names()
        checkpoint = load_checkpoint()
        remaining = [p for p in packages if p not in checkpoint]

        self.call_from_thread(
            self._set_initial_state,
            len(packages),
            len(checkpoint),
            sum(checkpoint.values()),
            checkpoint,
        )

        if not remaining:
            self.call_from_thread(self._mark_done)
            return

        patterns = _compile_patterns(self._config)
        checkpoint_lock = threading.Lock()
        since_save = 0
        self._start_time = time.monotonic()

        self._executor = ThreadPoolExecutor(max_workers=self._fetch_workers)
        try:
            futures = {
                self._executor.submit(filtered_size_breakdown, name, self._config, patterns): name
                for name in remaining
            }
            for future in as_completed(futures):
                if self._stop.is_set():
                    break
                name = futures[future]
                bd = future.result()
                with self._pending_lock:
                    self._pending.append((name, bd))
                with checkpoint_lock:
                    checkpoint[name] = sum(bd.values())
                    since_save += 1
                    if since_save >= 1000:
                        save_checkpoint(checkpoint)
                        since_save = 0
        finally:
            self._executor.shutdown(wait=False, cancel_futures=True)
            self._executor = None

        save_checkpoint(checkpoint)
        if not self._stop.is_set():
            self.call_from_thread(self._mark_done)

    def _set_initial_state(self, total: int, completed: int, total_bytes: int, checkpoint: dict[str, int]) -> None:
        self._total_packages = total
        self._completed = completed
        self._total_bytes = total_bytes
        self.query_one("#main-bar", ProgressBar).update(total=total, progress=completed)
        if completed:
            self.query_one("#running-total", Static).update(
                f"Checkpoint: [bold]{fmt(total_bytes)}[/bold] ({completed:,} packages cached)"
            )
            # Seed leaderboard from checkpoint top-N by size
            top = heapq.nlargest(LEADERBOARD_SIZE, checkpoint.items(), key=lambda kv: kv[1])
            for size, name in ((v, k) for k, v in top):
                heapq.heappush(self._heap, (size, name))
            self._refresh_leaderboard()

    def _flush(self) -> None:
        with self._pending_lock:
            batch = self._pending[:]
            self._pending.clear()

        if not batch:
            return

        lb_changed = False
        for name, bd in batch:
            size = sum(bd.values())
            self._completed += 1
            self._this_run_completed += 1
            self._total_bytes += size
            self._cp_bytes += bd["cp"]
            self._abi3_bytes += bd["abi3"]
            self._any_bytes += bd["any"]

            if size > 0:
                if len(self._heap) < LEADERBOARD_SIZE:
                    heapq.heappush(self._heap, (size, name))
                    lb_changed = True
                elif size > self._heap[0][0]:
                    heapq.heapreplace(self._heap, (size, name))
                    lb_changed = True

        self.query_one("#main-bar", ProgressBar).update(progress=self._completed)

        elapsed = time.monotonic() - self._start_time if self._start_time else 0
        rate = self._this_run_completed / elapsed if elapsed > 0 else 0
        eta = (self._total_packages - self._completed) / rate if rate > 0 else float("inf")

        self.query_one("#stats", Static).update(
            f"{self._completed:,} / {self._total_packages:,}  •  "
            f"{rate:,.0f} pkg/s  •  ETA {_fmt_eta(eta)}"
        )
        self.query_one("#running-total", Static).update(
            f"Running total: [bold]{fmt(self._total_bytes)}[/bold]"
        )

        tb = max(self._total_bytes, 1)
        for attr, bar_id, stat_id in [
            ("_cp_bytes",   "#cp-bar",   "#cp-stat"),
            ("_abi3_bytes", "#abi3-bar", "#abi3-stat"),
            ("_any_bytes",  "#any-bar",  "#any-stat"),
        ]:
            val = getattr(self, attr)
            self.query_one(bar_id, ProgressBar).update(total=tb, progress=val)
            self.query_one(stat_id, Static).update(f"{fmt(val)}  {val / tb * 100:.0f}%")

        if lb_changed:
            self._refresh_leaderboard()

    def _refresh_leaderboard(self) -> None:
        table = self.query_one("#leaderboard", DataTable)
        for rank, (size, name) in enumerate(
            sorted(self._heap, key=lambda x: x[0], reverse=True), 1
        ):
            table.update_cell(str(rank), "package", name)
            table.update_cell(str(rank), "size", fmt(size))

    def _mark_done(self) -> None:
        self._flush()
        self._done = True
        self.query_one("#stats", Static).update(
            f"[bold green]Done![/bold green]  {self._total_packages:,} packages  •  "
            f"press [bold]S[/bold] to sync, [bold]Q[/bold] to quit"
        )
        self.query_one("#running-total", Static).update(
            f"Total: [bold green]{fmt(self._total_bytes)}[/bold green]"
        )
        self._bindings.bind("s", "go_sync", "Run sync now", show=True)
        self.refresh_bindings()

    def on_unmount(self) -> None:
        self._stop.set()
        if self._executor:
            self._executor.shutdown(wait=False, cancel_futures=True)

    def action_go_sync(self) -> None:
        if self._done:
            self.next_command = "sync"
            self.exit()

    def action_go_quit(self) -> None:
        self.exit()
