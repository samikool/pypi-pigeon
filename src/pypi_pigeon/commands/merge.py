"""pigeon merge — fold supplement/dist/ into the mirror with a live TUI."""
from __future__ import annotations

import hashlib
import re
import shutil
from collections.abc import Callable
from pathlib import Path

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, RichLog, Static

from pypi_pigeon.config import Config

CSS = """
Screen { height: 100vh; }

#log {
    height: 1fr;
    border: solid $primary-darken-2;
    margin: 0 1;
}

#status {
    height: 3;
    content-align: left middle;
    padding: 0 1;
    color: $text-muted;
}
"""


# ── Merge logic ───────────────────────────────────────────────────────────────

def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_filename(filename: str) -> tuple[str, str] | None:
    if filename.endswith(".whl"):
        m = re.match(r"^([A-Za-z0-9]([A-Za-z0-9._]*)?)-([0-9][^-]*)-", filename)
    else:
        m = re.match(r"^([A-Za-z0-9]([A-Za-z0-9._-]*)?)-([0-9][^-]+)\.(tar\.|zip)", filename)
    if m:
        return m.group(1), m.group(3)
    return None


def _update_simple_index(simple_dir: Path, pkg_name: str, filename: str, digest: str) -> bool:
    norm = _normalize(pkg_name)
    index_dir = simple_dir / norm
    index_dir.mkdir(parents=True, exist_ok=True)
    index_path = index_dir / "index.html"

    href = f"/packages/supplement/{filename}#sha256={digest}"
    link = f'    <a href="{href}">{filename}</a>\n'

    if index_path.exists():
        content = index_path.read_text()
        if filename in content:
            return False
        index_path.write_text(content.replace("</body>", f"{link}</body>"))
    else:
        index_path.write_text(
            f"<!DOCTYPE html>\n<html>\n"
            f"  <head><title>Links for {pkg_name}</title></head>\n"
            f"  <body>\n    <h1>Links for {pkg_name}</h1>\n"
            f"{link}"
            f"  </body>\n</html>\n"
        )
    return True


# ── Core logic (used by both TUI and headless) ────────────────────────────────

_MARKUP_RE = re.compile(r'\[/?[^\]]*\]')


def _strip_markup(s: str) -> str:
    return _MARKUP_RE.sub('', s)


def _merge_core(
    config: Config,
    log: Callable[[str], None],
    status: Callable[[str], None],
) -> None:
    mirror_dir = config.resolve(config.mirror.dir)
    dist_dir = config.resolve(config.supplement.dist_dir)
    packages_dir = mirror_dir / "web" / "packages" / "supplement"
    simple_dir = mirror_dir / "web" / "simple"

    if not dist_dir.exists():
        log(f"[bold red]Error:[/bold red] supplement dist dir not found: {dist_dir}")
        log("Run [bold]pigeon sync[/bold] (internet side) and DTA the dist folder over first.")
        status("[red]Failed — dist dir not found.[/red]")
        return

    files = [
        f for f in dist_dir.iterdir()
        if f.suffix in {".whl", ".gz", ".bz2", ".zip"} or f.name.endswith(".tar.gz")
    ]

    if not files:
        log(f"No packages found in [bold]{dist_dir}[/bold]")
        status("Nothing to merge.")
        return

    if not simple_dir.exists():
        log(f"[bold red]Error:[/bold red] mirror simple/ dir not found at {simple_dir}")
        log("Has bandersnatch run yet?")
        status("[red]Failed — mirror not initialized.[/red]")
        return

    packages_dir.mkdir(parents=True, exist_ok=True)

    added = skipped = errors = 0
    total = len(files)

    for i, src in enumerate(sorted(files), 1):
        status(f"Processing {i} / {total}…")
        result = _parse_filename(src.name)
        if not result:
            log(f"  [yellow]SKIP[/yellow]  (unparseable): {src.name}")
            errors += 1
            continue

        pkg_name, _ = result
        dest = packages_dir / src.name
        if not dest.exists():
            shutil.copy2(src, dest)

        digest = _sha256(dest)
        is_new = _update_simple_index(simple_dir, pkg_name, src.name, digest)

        if is_new:
            log(f"  [green]ADD[/green]   {src.name}")
            added += 1
        else:
            skipped += 1

    log("")
    if added:
        log(f"[bold green]Done:[/bold green] {added} added, {skipped} already present, {errors} errors")
        log("nginx will serve the new files immediately — no restart needed.")
    else:
        log(f"[bold]Done:[/bold] {skipped} already present, {errors} errors — nothing new to add.")

    status(
        f"[bold]Merge complete[/bold]  •  "
        f"{added} added  •  {skipped} already present  •  {errors} errors  •  "
        f"press [bold]Q[/bold] to quit"
    )


def run_headless(config: Config) -> None:
    """Run merge without a TUI, streaming output to stdout."""
    _merge_core(
        config,
        log=lambda msg: print(_strip_markup(msg)),
        status=lambda msg: None,
    )


# ── App ───────────────────────────────────────────────────────────────────────

class MergeApp(App):
    CSS = CSS
    TITLE = "pigeon — merge"
    BINDINGS = [Binding("q", "go_quit", "Quit")]

    def __init__(self, config: Config) -> None:
        super().__init__()
        self._config = config
        self.next_command: str | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield RichLog(id="log", highlight=False, markup=True, wrap=False)
        yield Static("Starting…", id="status")
        yield Footer()

    def on_mount(self) -> None:
        self._run_merge()

    @work(thread=True)
    def _run_merge(self) -> None:
        def log(msg: str) -> None:
            self.call_from_thread(self.query_one("#log", RichLog).write, msg)

        def status(msg: str) -> None:
            self.call_from_thread(self.query_one("#status", Static).update, msg)

        _merge_core(self._config, log, status)

    def action_go_quit(self) -> None:
        self.exit()
