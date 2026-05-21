# pypi-pigeon

A toolkit for maintaining a PyPI mirror on an airgapped network. Packages are brought over via sneakernet (DTA — physically moving drives between networks).

Uses [bandersnatch](https://bandersnatch.readthedocs.io/) for the base mirror and a supplement workflow for packages that need full dependency resolution. Features a Textual TUI for interactive use and `--plain` mode for scripting.

## Install

```bash
pip install pypi-pigeon
# or with uv:
uv tool install pypi-pigeon
```

## Workflow

### Internet-connected machine

```bash
pigeon setup      # one-time wizard: configure pigeon.toml + generate bandersnatch.conf
pigeon dry-run    # optional: estimate mirror size before committing (takes hours, resumable)
pigeon sync       # run bandersnatch + fetch supplement packages
```

DTA the following to your airgapped server:
- `<mirror-dir>/web/` — the base mirror
- `supplement/dist/` — supplement wheels (if you used `pigeon add`)

### Airgapped server

```bash
pigeon merge      # fold supplement wheels into the mirror's simple/ index
```

Re-run `pigeon merge` after every bandersnatch sync — bandersnatch overwrites `simple/<pkg>/index.html` for packages it manages, wiping supplement links for those packages. Merge is idempotent and fast.

## Commands

| Command | Description |
|---|---|
| `pigeon setup` | TUI wizard — configure `pigeon.toml` and generate `bandersnatch.conf` |
| `pigeon dry-run` | Fetch PyPI metadata to estimate mirror size before syncing |
| `pigeon sync` | Run bandersnatch + fetch supplement packages |
| `pigeon mirror` | Alias for `sync` (bandersnatch's own term) |
| `pigeon merge` | Fold `supplement/dist/` into the mirror's `simple/` index |
| `pigeon add <pkg>` | Append packages to the supplement list |

**`--plain` flag** — add to `dry-run`, `sync`/`mirror`, or `merge` to stream plain stdout instead of launching the TUI. Useful for scripting and CI.

**`--config PATH`** — available on all commands. By default pigeon searches up the directory tree for `pigeon.toml` (git-style), so you can run commands from any subdirectory of your mirror workspace.

## Config

`pigeon setup` creates `pigeon.toml`:

```toml
[mirror]
dir = "/path/to/mirror"   # where bandersnatch writes; nginx serves web/ from here
workers = 10              # hard max 10 (bandersnatch limit)
keep_releases = 3
diff_file = ""            # path to write a changed-file list each sync; "" = disabled

[filter]
python_versions = ["3.10"]
platforms = ["linux-manylinux-x86_64"]
include_sdists = false
include_prereleases = false
allowlist_packages = []   # mirror only these packages; empty = mirror everything
blocklist_packages = []

[supplement]
dist_dir = "supplement/dist"
packages_file = "requirements.txt"
```

Edit directly or re-run `pigeon setup` anytime to reconfigure.

## Supplement packages

The base mirror uses aggressive filtering (specific Python version, platform, latest N releases). For packages outside those filters — or pinned versions you need — use the supplement:

```bash
pigeon add requests numpy==1.26.0
# or edit supplement/packages.txt directly (standard requirements.txt format)
```

During `pigeon sync`, supplement packages are fetched via `pip download --only-binary :all:` with full transitive dependency resolution. The result is a self-contained closure of wheels — no missing dependencies on the airgapped side.

## Supported platforms

The setup wizard lets you pick any combination of:

- Linux manylinux x86_64 / aarch64 / i686
- Linux musllinux x86_64 / aarch64 (Alpine)
- Windows AMD64 / x86 / ARM64
- macOS x86_64 (Intel) / ARM64 (Apple Silicon)

## Bandersnatch gotchas

**Plugin names changed in 7.x** — `blocklist_release_files` and `keep_only_latest_releases` no longer exist and are silently ignored. pigeon generates the correct config automatically; don't hand-edit `bandersnatch.conf` for anything covered by `pigeon.toml`.

**Workers hard max = 10** — bandersnatch raises an exception above 10. The setup wizard enforces this.

**Test runs** — to verify filters before committing to a full sync, temporarily add an `[allowlist]` section to `bandersnatch.conf`. Expected results: numpy → only `cp310-manylinux-x86_64` wheels; cryptography → only `abi3-manylinux-x86_64`; requests → only `py3-none-any`. Zero `.tar.gz` files. Remove the allowlist before re-running `pigeon setup` — it regenerates `bandersnatch.conf` from scratch.
