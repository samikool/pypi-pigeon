"""
Single source of truth for pymirror configuration.

Reads/writes pymirror.toml. Also owns bandersnatch.conf generation so the
allowlist patterns are defined in exactly one place.

The split between Config (user intent) and generate_bandersnatch_conf()
(translation to bandersnatch plugin syntax + regexes) is intentional — the
user never sees regex strings, only meaningful choices like python_versions
and platforms.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_CONFIG_PATH = Path("pymirror.toml")
PYPI_MASTER = "https://pypi.org"


def find_config(start: Path | None = None) -> Path | None:
    """Walk up from start (default: cwd) looking for pymirror.toml, git-style."""
    here = (start or Path.cwd()).resolve()
    for directory in [here, *here.parents]:
        candidate = directory / "pymirror.toml"
        if candidate.exists():
            return candidate
    return None

# Maps platform slug → wheel platform-tag regexes.
# Each regex is used in:  .*-{cp_tag}-.*-{regex}\.whl$
#                    and  .*-abi3-.*-{regex}\.whl$
# Multiple regexes per slug cover both modern and legacy tag spellings
# (e.g. manylinux_2_17_x86_64 vs manylinux2014_x86_64).
PLATFORM_WHEEL_TAGS: dict[str, list[str]] = {
    "linux-manylinux-x86_64":  [r"manylinux.*x86_64.*", r"linux_x86_64"],
    "linux-manylinux-aarch64": [r"manylinux.*aarch64.*", r"linux_aarch64"],
    "linux-manylinux-i686":    [r"manylinux.*i686.*",    r"linux_i686"],
    "linux-musllinux-x86_64":  [r"musllinux.*x86_64.*"],
    "linux-musllinux-aarch64": [r"musllinux.*aarch64.*"],
    "windows-amd64":           [r"win_amd64"],
    "windows-x86":             [r"win32"],
    "windows-arm64":           [r"win_arm64"],
    "macos-x86_64":            [r"macosx.*x86_64.*"],
    "macos-arm64":             [r"macosx.*arm64.*"],
}

# All CPython versions we know about. Add new entries here as Python releases.
# Format: (version_string, human_label)
KNOWN_PYTHON_VERSIONS: list[tuple[str, str]] = [
    ("3.8",  "3.8  (EOL)"),
    ("3.9",  "3.9  (EOL)"),
    ("3.10", "3.10"),
    ("3.11", "3.11"),
    ("3.12", "3.12"),
    ("3.13", "3.13  (current)"),
    ("3.14", "3.14  (pre-release)"),
]

# All known platforms. Add new entries here as new targets appear.
# Format: (slug, human_label)
KNOWN_PLATFORMS: list[tuple[str, str]] = [
    ("linux-manylinux-x86_64",  "Linux / manylinux / x86_64   (standard 64-bit)"),
    ("linux-manylinux-aarch64", "Linux / manylinux / aarch64  (ARM64)"),
    ("linux-manylinux-i686",    "Linux / manylinux / i686     (32-bit)"),
    ("linux-musllinux-x86_64",  "Linux / musllinux / x86_64   (Alpine)"),
    ("linux-musllinux-aarch64", "Linux / musllinux / aarch64  (Alpine ARM64)"),
    ("windows-amd64",           "Windows / AMD64"),
    ("windows-x86",             "Windows / x86  (32-bit)"),
    ("windows-arm64",           "Windows / ARM64"),
    ("macos-x86_64",            "macOS / x86_64  (Intel)"),
    ("macos-arm64",             "macOS / ARM64  (Apple Silicon)"),
]


@dataclass
class MirrorConfig:
    dir: str = "/tmp/pypimirror"
    workers: int = 10
    keep_releases: int = 3
    diff_file: str = ""        # path to write changed-file list each sync; "" = disabled


@dataclass
class FilterConfig:
    python_versions: list[str] = field(default_factory=lambda: ["3.10"])
    platforms: list[str] = field(default_factory=lambda: ["linux-manylinux-x86_64"])
    include_sdists: bool = False
    include_prereleases: bool = False
    allowlist_packages: list[str] = field(default_factory=list)
    blocklist_packages: list[str] = field(default_factory=list)


@dataclass
class SupplementConfig:
    dist_dir: str = "supplement/dist"
    packages_file: str = "supplement/packages.txt"
    fetch_workers: int = 50


@dataclass
class Config:
    mirror: MirrorConfig = field(default_factory=MirrorConfig)
    filter: FilterConfig = field(default_factory=FilterConfig)
    supplement: SupplementConfig = field(default_factory=SupplementConfig)
    config_dir: Path = field(default_factory=Path.cwd, repr=False, compare=False)

    def resolve(self, path_str: str) -> Path:
        """Resolve a path relative to the config file's directory (absolute paths pass through)."""
        p = Path(path_str)
        return p if p.is_absolute() else (self.config_dir / p).resolve()


# ── Serialisation ─────────────────────────────────────────────────────────────

def _str_list(items: list[str]) -> str:
    return "[" + ", ".join(f'"{x}"' for x in items) + "]"


def load(path: Path = DEFAULT_CONFIG_PATH) -> Config:
    with open(path, "rb") as f:
        data = tomllib.load(f)
    c = Config(config_dir=Path(path).resolve().parent)
    if m := data.get("mirror"):
        c.mirror = MirrorConfig(**{k: v for k, v in m.items() if hasattr(c.mirror, k)})
    if raw := data.get("filter"):
        kwargs: dict = {}
        for k, v in raw.items():
            if hasattr(c.filter, k):
                kwargs[k] = v
        c.filter = FilterConfig(**kwargs)
    if s := data.get("supplement"):
        c.supplement = SupplementConfig(**{k: v for k, v in s.items() if hasattr(c.supplement, k)})
    return c


def save(config: Config, path: Path = DEFAULT_CONFIG_PATH) -> None:
    m, f, s = config.mirror, config.filter, config.supplement
    lines = [
        "[mirror]",
        f'dir = "{m.dir}"',
        f"workers = {m.workers}",
        f"keep_releases = {m.keep_releases}",
    ]
    if m.diff_file:
        lines.append(f'diff_file = "{m.diff_file}"')
    lines += [
        "",
        "[filter]",
        f"python_versions = {_str_list(f.python_versions)}",
        f"platforms = {_str_list(f.platforms)}",
        f"include_sdists = {str(f.include_sdists).lower()}",
        f"include_prereleases = {str(f.include_prereleases).lower()}",
        f"allowlist_packages = {_str_list(f.allowlist_packages)}",
        f"blocklist_packages = {_str_list(f.blocklist_packages)}",
        "",
        "[supplement]",
        f'dist_dir = "{s.dist_dir}"',
        f'packages_file = "{s.packages_file}"',
        f"fetch_workers = {s.fetch_workers}",
        "",
    ]
    path.write_text("\n".join(lines))


# Maps platform slug → pip --platform tag used with `pip download`.
PLATFORM_PIP_TAGS: dict[str, str] = {
    "linux-manylinux-x86_64":  "manylinux2014_x86_64",
    "linux-manylinux-aarch64": "manylinux2014_aarch64",
    "linux-manylinux-i686":    "manylinux2014_i686",
    "linux-musllinux-x86_64":  "musllinux_1_1_x86_64",
    "linux-musllinux-aarch64": "musllinux_1_1_aarch64",
    "windows-amd64":           "win_amd64",
    "windows-x86":             "win32",
    "windows-arm64":           "win_arm64",
    "macos-x86_64":            "macosx_10_9_x86_64",
    "macos-arm64":             "macosx_11_0_arm64",
}


def pip_download_cmd(config: Config) -> list[str]:
    """Build a `pip download` command targeting the first configured python version + platform."""
    version = config.filter.python_versions[0]
    platform = config.filter.platforms[0]
    py_nodot = version.replace(".", "")
    pip_tag = PLATFORM_PIP_TAGS.get(platform, platform)
    return [
        "pip", "download",
        "--python-version", py_nodot,
        "--platform", pip_tag,
        "--abi", f"cp{py_nodot}",
        "--only-binary", ":all:",
        "-d", str(config.resolve(config.supplement.dist_dir)),
        "-r", str(config.resolve(config.supplement.packages_file)),
    ]


# ── Pattern translation ───────────────────────────────────────────────────────

def cp_tag(version: str) -> str:
    return "cp" + version.replace(".", "")


def allowlist_patterns(
    python_versions: list[str],
    platforms: list[str],
    include_sdists: bool = False,
) -> list[str]:
    """
    Translate user intent into bandersnatch regex_release_file_metadata patterns.

    Patterns are ORed — a file is kept if it matches any one of them.
    """
    patterns: list[str] = []

    for version in python_versions:
        tag = cp_tag(version)
        for platform in platforms:
            for pt in PLATFORM_WHEEL_TAGS.get(platform, []):
                patterns.append(rf".*-{tag}-.*-{pt}\.whl$")

    # abi3 (stable ABI) — platform tag follows abi3 directly, no abi field between them
    for platform in platforms:
        for pt in PLATFORM_WHEEL_TAGS.get(platform, []):
            patterns.append(rf".*-abi3-{pt}\.whl$")

    # Pure Python / universal wheels
    patterns.append(r".*-none-any\.whl$")

    if include_sdists:
        patterns.append(r".*\.tar\.gz$")
        patterns.append(r".*\.zip$")

    return patterns


# ── bandersnatch.conf generation ──────────────────────────────────────────────

def generate_bandersnatch_conf(config: Config) -> str:
    f = config.filter
    patterns = allowlist_patterns(f.python_versions, f.platforms, f.include_sdists)
    patterns_str = "\n    ".join(patterns)

    plugins = ["regex_release_file_metadata", "latest_release"]
    if not f.include_prereleases:
        plugins.append("prerelease_release")
    if f.allowlist_packages:
        plugins.append("allowlist_project")
    if f.blocklist_packages:
        plugins.append("blocklist_project")
    plugins_str = "\n    ".join(plugins)

    diff_line = (
        f"diff-file = {config.mirror.diff_file}\ndiff-append-epoch = true\n"
        if config.mirror.diff_file else ""
    )

    allowlist_section = ""
    if f.allowlist_packages:
        pkgs = "\n    ".join(f.allowlist_packages)
        allowlist_section = f"\n[allowlist]\npackages =\n    {pkgs}\n"

    blocklist_section = ""
    if f.blocklist_packages:
        pkgs = "\n    ".join(f.blocklist_packages)
        blocklist_section = f"\n[blocklist]\npackages =\n    {pkgs}\n"

    return f"""\
[mirror]
directory = {config.mirror.dir}
json = false
master = {PYPI_MASTER}
timeout = 10
workers = {config.mirror.workers}
hash-index = false
storage-backend = filesystem
verifiers = 3
keep_index_versions = 0
release-files = true
compare-mirrors = false
{diff_line}
[plugins]
enabled =
    {plugins_str}

[regex_release_file_metadata]
any:release_file.filename =
    {patterns_str}

[latest_release]
keep = {config.mirror.keep_releases}
{allowlist_section}{blocklist_section}"""
