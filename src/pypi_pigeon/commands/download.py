"""pigeon download — fetch supplement packages without running a full sync."""
from __future__ import annotations

import asyncio
import sys

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.containers import Vertical
from textual.widgets import Footer, Header, RichLog, Static

from pypi_pigeon.config import Config, pip_download_cmd

CSS = """
Screen { height: 100vh; }
#log { height: 1fr; border: solid $primary-darken-2; margin: 0 1; }

DownloadDoneScreen { align: center middle; }
#done-panel {
    width: 60;
    height: auto;
    border: round $success;
    padding: 1 2;
}
"""


# ── Headless mode ─────────────────────────────────────────────────────────────

def run_headless(config: Config) -> None:
    asyncio.run(_headless_download(config))


async def _headless_download(config: Config) -> None:
    packages_file = config.resolve(config.supplement.packages_file)
    if not packages_file.exists():
        print("No requirements.txt found — nothing to download.")
        return
    pkgs = [
        line.strip()
        for line in packages_file.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]
    if not pkgs:
        print("requirements.txt is empty — nothing to download.")
        return

    cmd = pip_download_cmd(config)
    print(f"Fetching {len(pkgs)} supplement package(s) + all dependencies…")
    print(f"$ {' '.join(cmd)}")
    proc = await asyncio.create_subprocess_exec(*cmd)
    await proc.wait()
    if proc.returncode == 0:
        print("Supplement download complete.")
    else:
        print("Some packages failed — check output above.", file=sys.stderr)
        sys.exit(proc.returncode)


# ── TUI ───────────────────────────────────────────────────────────────────────

class DownloadScreen(Screen):

    def __init__(self, config: Config) -> None:
        super().__init__()
        self._config = config

    def compose(self) -> ComposeResult:
        yield RichLog(id="log", highlight=True, markup=True, wrap=False)

    def on_mount(self) -> None:
        self.run_worker(self._run(), exclusive=True)

    async def _run(self) -> None:
        log = self.query_one("#log", RichLog)
        packages_file = self._config.resolve(self._config.supplement.packages_file)

        if not packages_file.exists():
            log.write("[yellow]No requirements.txt found — nothing to download.[/yellow]")
            self.app.push_screen(DownloadDoneScreen(skipped=True))
            return

        pkgs = [
            line.strip()
            for line in packages_file.read_text().splitlines()
            if line.strip() and not line.startswith("#")
        ]
        if not pkgs:
            log.write("[yellow]requirements.txt is empty — nothing to download.[/yellow]")
            self.app.push_screen(DownloadDoneScreen(skipped=True))
            return

        cmd = pip_download_cmd(self._config)
        log.write(f"[bold]Fetching {len(pkgs)} supplement package(s) + all dependencies…[/bold]")
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
            self.app.push_screen(DownloadDoneScreen(skipped=False))
        else:
            log.write("[bold red]Some packages failed — check output above.[/bold red]")


class DownloadDoneScreen(Screen):
    BINDINGS = [Binding("q", "go_quit", "Quit")]

    def __init__(self, skipped: bool) -> None:
        super().__init__()
        self._skipped = skipped

    def compose(self) -> ComposeResult:
        yield Header()
        if self._skipped:
            msg = "[bold yellow]Nothing to download.[/bold yellow]\n\nAdd packages with [bold]pigeon add <pkg>[/bold] first."
        else:
            msg = (
                "[bold green]Download complete![/bold green]\n\n"
                "DTA [bold]supplement/dist/[/bold] to the airgapped server,\n"
                "then run [bold]pigeon merge[/bold] to fold wheels into the mirror.\n\n"
                "Press [bold]Q[/bold] to quit."
            )
        with Vertical(id="done-panel"):
            yield Static(msg, id="done-text")
        yield Footer()

    def action_go_quit(self) -> None:
        self.app.exit()


class DownloadApp(App):
    CSS = CSS
    TITLE = "pigeon — download"
    BINDINGS = [Binding("ctrl+c", "quit", "Quit")]

    def __init__(self, config: Config) -> None:
        super().__init__()
        self._config = config
        self.next_command: str | None = None

    def on_mount(self) -> None:
        self.push_screen(DownloadScreen(self._config))
