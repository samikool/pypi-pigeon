"""pigeon sync — run bandersnatch mirror with a live TUI."""
from __future__ import annotations

import asyncio
import os
import re
import sys
import time

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Label, ProgressBar, RichLog, Static

from pypi_pigeon.config import Config, pip_download_cmd
from pypi_pigeon.commands.dry_run import CHECKPOINT_FILE, fmt, load_checkpoint

def _bandersnatch_cmd(config: Config) -> list[str]:
    conf = config.config_dir / "bandersnatch.conf"
    return ["bandersnatch", "-c", str(conf), "mirror"]

_RE_TOTAL    = re.compile(r'(\d+) packages to sync')
_RE_FETCHING = re.compile(r'Fetching metadata for package: (\S+)')
_RE_STORED   = re.compile(r'Storing index page\(s\): (\S+)')

CSS = """
Screen { height: 100vh; }

#reminder {
    align: center middle;
}

#reminder-panel {
    width: 64;
    height: auto;
    border: round $warning;
    padding: 1 2;
}

#reminder-body {
    color: $text-muted;
}

#log { height: 1fr; border: solid $primary-darken-2; margin: 0 1; }

#progress-footer {
    height: auto;
    padding: 0 1;
    background: $surface-darken-1;
}

.progress-row {
    height: 3;
    align: left middle;
}

#scan-row {
    height: auto;
    padding: 0 1;
    display: none;
}

#scan-text {
    color: $text-muted;
}

.progress-label {
    width: 10;
    color: $text-muted;
}

.progress-bar { width: 1fr; }

.progress-text {
    width: 26;
    text-align: right;
    color: $text-muted;
}

DoneScreen {
    align: center middle;
}

#done-panel {
    width: 60;
    height: auto;
    border: round $success;
    padding: 1 2;
}
"""


# ── Headless mode ────────────────────────────────────────────────────────────

def run_headless(config: Config) -> None:
    """Run sync without a TUI, streaming bandersnatch and pip output to stdout."""
    asyncio.run(_headless_sync(config))


async def _headless_sync(config: Config) -> None:
    cmd = _bandersnatch_cmd(config)
    print(f"$ {' '.join(cmd)}")
    proc = await asyncio.create_subprocess_exec(*cmd)
    await proc.wait()
    if proc.returncode != 0:
        print(f"bandersnatch exited with code {proc.returncode}.", file=sys.stderr)
        sys.exit(proc.returncode)
    print("bandersnatch finished successfully.")
    await _headless_supplement(config)


async def _headless_supplement(config: Config) -> None:
    packages_file = config.resolve(config.supplement.packages_file)
    if not packages_file.exists():
        return
    pkgs = [
        line.strip()
        for line in packages_file.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]
    if not pkgs:
        return
    cmd = pip_download_cmd(config)
    print(f"\nFetching {len(pkgs)} supplement package(s) + all dependencies…")
    print(f"$ {' '.join(cmd)}")
    proc = await asyncio.create_subprocess_exec(*cmd)
    await proc.wait()
    if proc.returncode == 0:
        print("Supplement download complete.")
    else:
        print("Some supplement packages failed — check output above.", file=sys.stderr)
        sys.exit(proc.returncode)


# ── Dry-run reminder ──────────────────────────────────────────────────────────

class DryRunReminderScreen(Screen):
    """Shown once when no dry-run checkpoint exists."""

    BINDINGS = [
        Binding("s", "proceed", "Sync anyway"),
        Binding("d", "dry_run", "Run dry-run first"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="reminder"):
            with Vertical(id="reminder-panel"):
                yield Static(
                    "No dry-run data found.\n\n"
                    "Tip: [bold]pigeon dry-run[/bold] fetches mirror metadata to give you a size estimate "
                    "before committing. Takes hours — but mirroring takes days.\n\n"
                    "Press [bold]S[/bold] to sync now, or [bold]D[/bold] to dry-run first.",
                    id="reminder-body",
                )
        yield Footer()

    def action_proceed(self) -> None:
        self.app.push_screen(MirrorScreen(self.app._config))

    def action_dry_run(self) -> None:
        self.app.next_command = "dry-run"
        self.app.exit()


# ── Mirror screen ─────────────────────────────────────────────────────────────

class MirrorScreen(Screen):

    def __init__(self, config: Config) -> None:
        super().__init__()
        self._config = config
        self._simple_dir = config.resolve(config.mirror.dir) / "web" / "simple"
        self._checkpoint: dict[str, int] = {}
        self._total_checkpoint_bytes: int = 0
        self._already_synced: int | None = None   # pkg count mirrored before this run
        self._already_synced_bytes: int = 0        # bytes for those packages
        self._initial_pkg_count: int | None = None
        self._done_count: int = 0
        self._done_bytes: int = 0
        self._current_package: str = ""
        self._log_buffer: list[str] = []
        self._scan_start: float = 0.0
        self._scan_count: int = 0                  # live count written by scan thread

    def compose(self) -> ComposeResult:
        yield RichLog(id="log", highlight=True, markup=True, wrap=False)
        with Vertical(id="progress-footer"):
            with Horizontal(id="scan-row"):
                yield Static("", id="scan-text")
            with Horizontal(classes="progress-row"):
                yield Label("Packages", classes="progress-label")
                yield ProgressBar(show_eta=False, id="pkg-bar", classes="progress-bar")
                yield Static("", id="pkg-text", classes="progress-text")
            with Horizontal(classes="progress-row", id="gb-row"):
                yield Label("Data", classes="progress-label")
                yield ProgressBar(show_eta=False, id="gb-bar", classes="progress-bar")
                yield Static("", id="gb-text", classes="progress-text")

    def on_mount(self) -> None:
        raw = load_checkpoint()
        # bandersnatch normalizes names to lowercase+hyphens; match that here
        self._checkpoint = {k.lower().replace("_", "-"): v for k, v in raw.items()}
        self._total_checkpoint_bytes = sum(self._checkpoint.values())
        if not self._checkpoint:
            self.query_one("#gb-row", Horizontal).display = False
        self._scan_start = time.monotonic()
        self.query_one("#scan-row", Horizontal).display = True
        self.query_one("#scan-text", Static).update("Counting existing packages…  0s")
        self.set_interval(1, self._tick_scan)
        self.run_worker(self._run_sync(), exclusive=True)

    def _tick_scan(self) -> None:
        if self._already_synced is not None:
            return
        elapsed = int(time.monotonic() - self._scan_start)
        self.query_one("#scan-text", Static).update(
            f"Counting existing packages…  {self._scan_count:,}  ({elapsed}s)"
        )

    async def _run_sync(self) -> None:
        await self._count_existing()
        await self._stream_bandersnatch()

    async def _count_existing(self) -> None:
        """Scan web/simple/ before bandersnatch starts — counts packages and sums their checkpoint bytes."""
        log = self.query_one("#log", RichLog)
        checkpoint = self._checkpoint
        simple_dir = self._simple_dir

        def scan() -> tuple[int, int]:
            count = 0
            byte_sum = 0
            try:
                for e in os.scandir(simple_dir):
                    if e.is_dir(follow_symlinks=False):
                        count += 1
                        byte_sum += checkpoint.get(e.name, 0)
                        if count % 1000 == 0:
                            self._scan_count = count
            except OSError:
                pass
            return count, byte_sum

        loop = asyncio.get_event_loop()
        count, byte_sum = await loop.run_in_executor(None, scan)

        elapsed = int(time.monotonic() - self._scan_start)
        self._already_synced = count
        self._already_synced_bytes = byte_sum
        self._done_bytes = byte_sum  # start the GB bar at the already-synced baseline
        self.query_one("#scan-row", Horizontal).display = False
        log.write(f"[dim]Found {count:,} existing packages, {fmt(byte_sum)} ({elapsed}s)[/dim]")
        if self._initial_pkg_count is not None:
            self._update_progress()

    async def _stream_bandersnatch(self) -> None:
        log = self.query_one("#log", RichLog)
        cmd = _bandersnatch_cmd(self._config)
        log.write(f"[bold]$ {' '.join(cmd)}[/bold]")
        self.query_one("#scan-row", Horizontal).display = True
        self.query_one("#scan-text", Static).update("Starting bandersnatch…")
        render_timer = self.set_interval(1 / 60, self._render_progress)

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        assert proc.stdout is not None
        async for raw in proc.stdout:
            line = raw.decode(errors="replace").rstrip()
            self._log_buffer.append(line)
            self._parse_progress(line)

        await proc.wait()
        render_timer.stop()
        self._render_progress()  # final update
        self.query_one("#scan-row", Horizontal).display = False
        if proc.returncode == 0:
            log.write("[bold green]bandersnatch finished successfully.[/bold green]")
            await self._fetch_supplement()
        else:
            log.write(f"[bold red]bandersnatch exited with code {proc.returncode}.[/bold red]")

    async def _fetch_supplement(self) -> None:
        packages_file = self._config.resolve(self._config.supplement.packages_file)
        log = self.query_one("#log", RichLog)

        if not packages_file.exists():
            self.app.push_screen(SyncDoneScreen())
            return

        pkgs = [
            line.strip()
            for line in packages_file.read_text().splitlines()
            if line.strip() and not line.startswith("#")
        ]
        if not pkgs:
            self.app.push_screen(SyncDoneScreen())
            return

        log.write("")
        log.write(f"[bold]Fetching {len(pkgs)} supplement package(s) + all dependencies…[/bold]")
        cmd = pip_download_cmd(self._config)
        log.write(f"[bold]$ {' '.join(cmd)}[/bold]")

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        assert proc.stdout is not None
        async for raw in proc.stdout:
            log.write(raw.decode(errors="replace").rstrip())

        await proc.wait()
        if proc.returncode == 0:
            log.write("[bold green]Supplement download complete.[/bold green]")
        else:
            log.write("[bold yellow]Some supplement packages failed — check output above.[/bold yellow]")

        self.app.push_screen(SyncDoneScreen())

    def _parse_progress(self, line: str) -> None:
        if 'packages to sync' in line:
            m = _RE_TOTAL.search(line)
            if m:
                self._initial_pkg_count = int(m.group(1))
        elif 'Fetching metadata' in line:
            m = _RE_FETCHING.search(line)
            if m:
                self._current_package = m.group(1)
        elif 'Storing index' in line:
            m = _RE_STORED.search(line)
            if m:
                self._done_count += 1
                self._done_bytes += self._checkpoint.get(m.group(1), 0)
        elif 'no longer exists on PyPI' in line:
            self._done_count += 1

    def _render_progress(self) -> None:
        if self._log_buffer:
            log = self.query_one("#log", RichLog)
            for line in self._log_buffer:
                log.write(line)
            self._log_buffer.clear()
        if self._current_package:
            self.query_one("#scan-text", Static).update(f"[dim]Syncing:[/dim] {self._current_package}")
        self._update_progress()

    def _update_progress(self) -> None:
        already = self._already_synced or 0
        total_pkgs = already + (self._initial_pkg_count or 0)
        pkg_done = already + self._done_count

        self.query_one("#pkg-bar", ProgressBar).update(total=total_pkgs or 1, progress=pkg_done)
        if total_pkgs:
            pct = pkg_done / total_pkgs * 100
            self.query_one("#pkg-text", Static).update(
                f"{pkg_done:,} / {total_pkgs:,}  {pct:.1f}%"
            )

        if self._total_checkpoint_bytes:
            pct = self._done_bytes / self._total_checkpoint_bytes * 100
            self.query_one("#gb-bar", ProgressBar).update(
                total=self._total_checkpoint_bytes, progress=self._done_bytes,
            )
            self.query_one("#gb-text", Static).update(
                f"{fmt(self._done_bytes)} / {fmt(self._total_checkpoint_bytes)}  {pct:.1f}%"
            )
        elif self._done_bytes:
            self.query_one("#gb-text", Static).update(fmt(self._done_bytes))


# ── Done screen ───────────────────────────────────────────────────────────────

class SyncDoneScreen(Screen):
    BINDINGS = [Binding("q", "go_quit", "Quit")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="done-panel"):
            yield Static(
                "[bold green]Sync complete![/bold green]\n\n"
                "DTA to the airgapped server:\n"
                "  [bold]<mirror-dir>/web/[/bold]        — base mirror\n"
                "  [bold]supplement/dist/[/bold]         — supplement wheels (if any)\n\n"
                "Then run [bold]pigeon merge[/bold] on the server to fold the supplement wheels into the mirror.\n\n"
                "Press [bold]Q[/bold] to quit.",
                id="done-text",
            )
        yield Footer()

    def action_go_quit(self) -> None:
        self.app.exit()


# ── App ───────────────────────────────────────────────────────────────────────

class SyncApp(App):
    CSS = CSS
    TITLE = "pigeon — sync"
    BINDINGS = [Binding("ctrl+c", "quit", "Quit")]

    def __init__(self, config: Config) -> None:
        super().__init__()
        self._config = config
        self.next_command: str | None = None

    def on_mount(self) -> None:
        if CHECKPOINT_FILE.exists():
            self.push_screen(MirrorScreen(self._config))
        else:
            self.push_screen(DryRunReminderScreen())
