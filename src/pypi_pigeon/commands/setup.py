"""pigeon setup — step-by-step wizard."""
from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, ContentSwitcher, Footer, Header, Input, Label, Select, SelectionList, Static

from pypi_pigeon.config import (
    Config,
    DEFAULT_CONFIG_PATH,
    KNOWN_PLATFORMS,
    KNOWN_PYTHON_VERSIONS,
    generate_bandersnatch_conf,
    save,
)

# (step_id, title, description, config_attr, widget_type)
# widget_type: "welcome" | "text" | "int" | "int_max10" | "select" | "platforms" | "bool" | "confirm"
STEPS = [
    (
        "welcome",
        "Welcome to pigeon",
        "This wizard configures your PyPI mirror and generates [bold]bandersnatch.conf[/bold].\n\n"
        "Press [bold]Next →[/bold] to begin.",
        None,
        "welcome",
    ),
    (
        "mirror_dir",
        "Mirror directory",
        "Where bandersnatch stores the mirror on disk.\n"
        "Needs roughly 150–400 GB free.",
        "mirror.dir",
        "text",
    ),
    (
        "python_versions",
        "Python versions",
        "Which CPython versions to mirror wheels for.\n"
        "abi3 and pure-Python wheels are always included regardless of this setting.",
        "filter.python_versions",
        "multiselect",
    ),
    (
        "platforms",
        "Platforms",
        "Which platform wheels to mirror.\n"
        "Most users only need manylinux. Add musllinux for Alpine Linux support.",
        "filter.platforms",
        "multiselect",
    ),
    (
        "include_sdists",
        "Include sdists?",
        "Source distributions (.tar.gz / .zip).\n"
        "Most packages have binary wheels — sdists add significant size for little gain.",
        "filter.include_sdists",
        "bool",
    ),
    (
        "include_prereleases",
        "Include pre-releases?",
        "Mirror alpha, beta, and release candidate versions.\n"
        "Recommended: No — pre-releases are rarely needed on airgapped machines.",
        "filter.include_prereleases",
        "bool",
    ),
    (
        "allowlist_packages",
        "Package allowlist  (optional)",
        "Mirror only these packages. Leave blank to mirror everything matching your filters.\n"
        "Comma-separated, e.g:  requests, numpy, cryptography",
        "filter.allowlist_packages",
        "csv_packages",
    ),
    (
        "blocklist_packages",
        "Package blocklist  (optional)",
        "Always exclude these packages regardless of other filters.\n"
        "Comma-separated, or leave blank.",
        "filter.blocklist_packages",
        "csv_packages",
    ),
    (
        "keep_releases",
        "Keep N releases",
        "Latest N releases per package to mirror.\n"
        "3 is a good default — older releases are rarely needed.",
        "mirror.keep_releases",
        "int",
    ),
    (
        "workers",
        "Mirror workers",
        "Parallel bandersnatch download workers. Hard maximum: 10.",
        "mirror.workers",
        "int_max10",
    ),
    (
        "diff_file",
        "Diff file  (optional)",
        "Path to write the list of files changed each sync.\n"
        "Lets you DTA only the delta instead of the full mirror. Leave blank to disable.\n"
        "e.g:  /srv/pypi/sync-diff",
        "mirror.diff_file",
        "text_optional",
    ),
    (
        "dist_dir",
        "Supplement dist directory",
        "Where DTA'd supplement wheels are placed on the server\n"
        "before running [bold]pigeon merge[/bold].",
        "supplement.dist_dir",
        "text",
    ),
    (
        "confirm",
        "Review & confirm",
        "Press [bold]Finish ✓[/bold] to write [bold]pigeon.toml[/bold] and [bold]bandersnatch.conf[/bold].",
        None,
        "confirm",
    ),
]

CSS = """
Screen { height: 100vh; }

WizardScreen {
    align: center middle;
}

#panel {
    width: 74;
    height: auto;
    min-height: 22;
    border: round $primary;
    padding: 1 2;
}

#step-indicator {
    color: $text-muted;
    margin-bottom: 1;
}

#step-title {
    text-style: bold;
    margin-bottom: 0;
}

#step-desc {
    color: $text-muted;
    margin-bottom: 1;
}

.step-widget {
    width: 100%;
    margin-top: 1;
}

#error {
    color: $error;
    height: 1;
    margin-top: 1;
}

#nav {
    height: auto;
    margin-top: 1;
    align: right middle;
}

#nav Button {
    margin-left: 1;
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


class WizardScreen(Screen):
    BINDINGS = [
        Binding("escape", "prev_step", "Back", show=True),
    ]

    def __init__(self, config: Config) -> None:
        super().__init__()
        self._config = config
        self._step = 0

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="panel"):
            yield Static("", id="step-indicator")
            yield Static("", id="step-title")
            yield Static("", id="step-desc")
            with ContentSwitcher(initial="welcome"):
                yield Static("", id="welcome", classes="step-widget")
                yield Input(id="mirror_dir", classes="step-widget")
                yield SelectionList(
                    *[(label, slug) for slug, label in KNOWN_PYTHON_VERSIONS],
                    id="python_versions",
                    classes="step-widget",
                )
                yield SelectionList(
                    *[(label, slug) for slug, label in KNOWN_PLATFORMS],
                    id="platforms",
                    classes="step-widget",
                )
                yield Select(
                    [("No", "false"), ("Yes", "true")],
                    id="include_sdists",
                    classes="step-widget",
                )
                yield Select(
                    [("No", "false"), ("Yes", "true")],
                    id="include_prereleases",
                    classes="step-widget",
                )
                yield Input(id="allowlist_packages", classes="step-widget")
                yield Input(id="blocklist_packages", classes="step-widget")
                yield Input(id="keep_releases", classes="step-widget")
                yield Input(id="workers", classes="step-widget")
                yield Input(id="diff_file", classes="step-widget")
                yield Input(id="dist_dir", classes="step-widget")
                yield Static("", id="confirm", classes="step-widget")
            yield Static("", id="error")
            with Horizontal(id="nav"):
                yield Button("Back", id="btn-back", variant="default")
                yield Button("Next →", id="btn-next", variant="primary")
        yield Footer()

    def on_mount(self) -> None:
        self._render_step()

    def _render_step(self) -> None:
        step_id, title, desc, attr, wtype = STEPS[self._step]
        n = len(STEPS)

        self.query_one("#step-indicator", Static).update(f"Step {self._step + 1} / {n}")
        self.query_one("#step-title", Static).update(title)
        self.query_one("#step-desc", Static).update(desc)
        self.query_one("#error", Static).update("")
        self.query_one(ContentSwitcher).current = step_id

        if attr:
            section, key = attr.split(".", 1)
            val = getattr(getattr(self._config, section), key)

            if wtype in ("text", "int", "int_max10", "text_optional"):
                w = self.query_one(f"#{step_id}", Input)
                w.value = str(val)
                self.set_timer(0.05, w.focus)
            elif wtype == "csv_packages":
                w = self.query_one(f"#{step_id}", Input)
                w.value = ", ".join(val) if isinstance(val, list) else str(val)
                self.set_timer(0.05, w.focus)
            elif wtype == "multiselect":
                w = self.query_one(f"#{step_id}", SelectionList)
                w.deselect_all()
                for v in (val if isinstance(val, list) else [val]):
                    w.select(v)
                self.set_timer(0.05, w.focus)
            elif wtype == "bool":
                w = self.query_one(f"#{step_id}", Select)
                w.value = "true" if val else "false"
                self.set_timer(0.05, w.focus)

        is_last = self._step == len(STEPS) - 1
        self.query_one("#btn-next", Button).label = "Finish ✓" if is_last else "Next →"
        self.query_one("#btn-back", Button).disabled = self._step == 0

        if wtype == "confirm":
            self._render_summary()

    def _render_summary(self) -> None:
        c = self._config
        f = c.filter
        allowlist = ", ".join(f.allowlist_packages) if f.allowlist_packages else "none"
        blocklist = ", ".join(f.blocklist_packages) if f.blocklist_packages else "none"
        diff = c.mirror.diff_file or "disabled"
        self.query_one("#confirm", Static).update(
            f"[bold]Mirror directory[/bold]      {c.mirror.dir}\n"
            f"[bold]Python versions[/bold]       {', '.join(f.python_versions)}\n"
            f"[bold]Platforms[/bold]             {', '.join(f.platforms)}\n"
            f"[bold]Include sdists[/bold]        {'Yes' if f.include_sdists else 'No'}\n"
            f"[bold]Include pre-releases[/bold]  {'Yes' if f.include_prereleases else 'No'}\n"
            f"[bold]Allowlist[/bold]             {allowlist}\n"
            f"[bold]Blocklist[/bold]             {blocklist}\n"
            f"[bold]Keep N releases[/bold]       {c.mirror.keep_releases}\n"
            f"[bold]Workers[/bold]               {c.mirror.workers}\n"
            f"[bold]Diff file[/bold]             {diff}\n"
            f"[bold]Supplement dist dir[/bold]   {c.supplement.dist_dir}\n"
        )

    def _collect(self) -> str | None:
        """Read the current step's widget, update config. Returns error string or None."""
        step_id, _, _, attr, wtype = STEPS[self._step]
        if not attr:
            return None

        section, key = attr.split(".", 1)
        target = getattr(self._config, section)

        if wtype == "text":
            val = self.query_one(f"#{step_id}", Input).value.strip()
            if not val:
                return "This field is required."
            setattr(target, key, val)

        elif wtype == "text_optional":
            val = self.query_one(f"#{step_id}", Input).value.strip()
            setattr(target, key, val)

        elif wtype == "csv_packages":
            raw = self.query_one(f"#{step_id}", Input).value.strip()
            packages = [p.strip() for p in raw.split(",") if p.strip()] if raw else []
            setattr(target, key, packages)

        elif wtype in ("int", "int_max10"):
            raw = self.query_one(f"#{step_id}", Input).value.strip()
            try:
                val = int(raw)
            except ValueError:
                return "Please enter a whole number."
            if val < 1:
                return "Must be at least 1."
            if wtype == "int_max10" and val > 10:
                return "Maximum is 10 (bandersnatch hard limit)."
            setattr(target, key, val)

        elif wtype == "multiselect":
            selected = list(self.query_one(f"#{step_id}", SelectionList).selected)
            if not selected:
                return "Please select at least one option."
            setattr(target, key, selected)

        elif wtype == "bool":
            val = self.query_one(f"#{step_id}", Select).value
            if val is Select.BLANK:
                return "Please make a selection."
            setattr(target, key, val == "true")

        return None

    def action_next_step(self) -> None:
        err = self._collect()
        if err:
            self.query_one("#error", Static).update(err)
            return

        if self._step == len(STEPS) - 1:
            self.app.push_screen(WritingScreen(self._config))
            return

        self._step += 1
        self._render_step()

    def action_prev_step(self) -> None:
        if self._step > 0:
            self._step -= 1
            self._render_step()

    def on_input_submitted(self) -> None:
        self.action_next_step()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-next":
            self.action_next_step()
        elif event.button.id == "btn-back":
            self.action_prev_step()


class WritingScreen(Screen):
    """Writes config files, then shows completion."""

    def __init__(self, config: Config) -> None:
        super().__init__()
        self._config = config

    def on_mount(self) -> None:
        self.set_timer(0.1, self._write)

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="done-panel"):
            yield Static("Writing configuration…", id="done-text")
        yield Footer()

    def _write(self) -> None:
        config_path: Path = self.app.config_path
        conf_path = Path("bandersnatch.conf")
        try:
            save(self._config, config_path)
            conf_path.write_text(generate_bandersnatch_conf(self._config))
        except Exception as e:
            self.query_one("#done-text", Static).update(f"[bold red]Error:[/bold red] {e}")
            return

        self.app.push_screen(DoneScreen(config_path, conf_path))


class DoneScreen(Screen):
    BINDINGS = [
        Binding("e", "go_estimate", "Run dry-run now"),
        Binding("q", "go_quit", "Quit"),
    ]

    def __init__(self, config_path: Path, conf_path: Path) -> None:
        super().__init__()
        self._config_path = config_path
        self._conf_path = conf_path

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="done-panel"):
            yield Static(
                "[bold green]Setup complete![/bold green]\n\n"
                f"  [bold]{self._config_path}[/bold]   — pigeon config\n"
                f"  [bold]{self._conf_path}[/bold]  — bandersnatch config\n\n"
                "Run [bold]pigeon dry-run[/bold] to preview mirror size before syncing.\n\n"
                "[bold]Need specific packages?[/bold]\n"
                "Run [bold]pigeon add <pkg>[/bold] or edit [bold]supplement/packages.txt[/bold] directly.\n"
                "Unlike the base mirror, these are fetched with full dependency resolution —\n"
                "every transitive dependency is resolved and downloaded as a wheel,\n"
                "so you are guaranteed a self-contained closure on the airgapped side.\n"
                "They are fetched automatically as part of [bold]pigeon sync[/bold].\n\n"
                "Press [bold]E[/bold] to dry-run now, [bold]Q[/bold] to quit.",
                id="done-text",
            )
        yield Footer()

    def action_go_estimate(self) -> None:
        self.app.next_command = "dry-run"
        self.app.exit()

    def action_go_quit(self) -> None:
        self.app.exit()


class SetupApp(App):
    CSS = CSS
    TITLE = "pigeon — setup"

    def __init__(self, config_path: Path = DEFAULT_CONFIG_PATH) -> None:
        super().__init__()
        self.config_path = config_path
        self.next_command: str | None = None
        try:
            from pypi_pigeon.config import load
            config = load(config_path)
        except FileNotFoundError:
            config = Config()
        self._config = config

    def on_mount(self) -> None:
        self.push_screen(WizardScreen(self._config))
