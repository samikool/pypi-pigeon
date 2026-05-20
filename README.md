# pymirror

A toolkit for maintaining a PyPI mirror on an airgapped network. Packages are brought over via sneakernet (DTA — physically moving drives between networks).

Uses [bandersnatch](https://bandersnatch.readthedocs.io/) for the base mirror and a supplement workflow for packages that need full dependency resolution. Features a Textual TUI for interactive use and `--plain` mode for scripting.

## Install

```bash
pip install pymirror
# or with uv:
uv tool install pymirror
```

## Workflow

### Internet-connected machine

```bash
pymirror setup      # one-time wizard: configure pymirror.toml + generate bandersnatch.conf
pymirror dry-run    # optional: estimate mirror size before committing (takes hours, resumable)
pymirror sync       # run bandersnatch + fetch supplement packages
```

DTA the following to your airgapped server:
- `<mirror-dir>/web/` — the base mirror
- `supplement/dist/` — supplement wheels (if you used `pymirror add`)

### Airgapped server

```bash
pymirror merge      # fold supplement wheels into the mirror's simple/ index
```

Re-run `pymirror merge` after every bandersnatch sync — bandersnatch overwrites `simple/<pkg>/index.html` for packages it manages, wiping supplement links for those packages. Merge is idempotent and fast.

## Commands

| Command | Description |
|---|---|
| `pymirror setup` | TUI wizard — configure `pymirror.toml` and generate `bandersnatch.conf` |
| `pymirror dry-run` | Fetch PyPI metadata to estimate mirror size before syncing |
| `pymirror sync` | Run bandersnatch + fetch supplement packages |
| `pymirror mirror` | Alias for `sync` (bandersnatch's own term) |
| `pymirror merge` | Fold `supplement/dist/` into the mirror's `simple/` index |
| `pymirror add <pkg>` | Append packages to the supplement list |

**`--plain` flag** — add to `dry-run`, `sync`/`mirror`, or `merge` to stream plain stdout instead of launching the TUI. Useful for scripting and CI.

**`--config PATH`** — available on all commands. By default pymirror searches up the directory tree for `pymirror.toml` (git-style), so you can run commands from any subdirectory of your mirror workspace.

## Config

`pymirror setup` creates `pymirror.toml`:

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
packages_file = "supplement/packages.txt"
```

Edit directly or re-run `pymirror setup` anytime to reconfigure.

## Supplement packages

The base mirror uses aggressive filtering (specific Python version, platform, latest N releases). For packages outside those filters — or pinned versions you need — use the supplement:

```bash
pymirror add requests numpy==1.26.0
# or edit supplement/packages.txt directly (standard requirements.txt format)
```

During `pymirror sync`, supplement packages are fetched via `pip download --only-binary :all:` with full transitive dependency resolution. The result is a self-contained closure of wheels — no missing dependencies on the airgapped side.

## Supported platforms

The setup wizard lets you pick any combination of:

- Linux manylinux x86_64 / aarch64 / i686
- Linux musllinux x86_64 / aarch64 (Alpine)
- Windows AMD64 / x86 / ARM64
- macOS x86_64 (Intel) / ARM64 (Apple Silicon)

## Bandersnatch gotchas

**Plugin names changed in 7.x** — `blocklist_release_files` and `keep_only_latest_releases` no longer exist and are silently ignored. pymirror generates the correct config automatically; don't hand-edit `bandersnatch.conf` for anything covered by `pymirror.toml`.

**Workers hard max = 10** — bandersnatch raises an exception above 10. The setup wizard enforces this.

**Test runs** — to verify filters before committing to a full sync, temporarily add an `[allowlist]` section to `bandersnatch.conf`. Expected results: numpy → only `cp310-manylinux-x86_64` wheels; cryptography → only `abi3-manylinux-x86_64`; requests → only `py3-none-any`. Zero `.tar.gz` files. Remove the allowlist before re-running `pymirror setup` — it regenerates `bandersnatch.conf` from scratch.
