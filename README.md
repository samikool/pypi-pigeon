# pymirror

Toolkit for maintaining a PyPI mirror on an airgapped network. Packages are brought over via sneakernet (DTA — physically moving drives between networks).

## Target environment

- **Airgapped host**: Linux x86_64, Python 3.10.12
- **Mirror server**: ~11 TB disk mounted at `/12-tb/`
- **Serving**: nginx serving bandersnatch's `web/` directory statically

## How it works

### Part 1 — bandersnatch base mirror

Bandersnatch mirrors PyPI with aggressive filtering. Full PyPI is ~20 TB; with filters it lands around 150–400 GB.

Filters applied:
- Linux x86_64 only (no Windows, macOS, ARM, 32-bit)
- `cp310` wheels + `abi3` wheels + universal `none-any` wheels only
- No sdists (~95% of popular packages have manylinux wheels)
- Latest 3 releases per package

### Part 2 — supplement

For packages not covered by the base mirror, or specific versions needed. List packages in `supplement/packages.txt`, run `supplement/download.py` to fetch them **plus all transitive dependencies** as wheels, DTA `supplement/dist/` to the server, then run `merge.py` to fold them into the served mirror.

`merge.py` is idempotent. Re-run it after every bandersnatch sync — bandersnatch overwrites `web/simple/<pkg>/index.html` for packages it knows about, which wipes supplement links for those packages.

## File layout

```
config.py              ← single source of truth; change Python version/platform here
generate_conf.py       ← generates bandersnatch.conf from config.py
bandersnatch.conf      ← generated output; feed to bandersnatch
merge.py               ← fold supplement into mirror; re-run after each bandersnatch sync
main.py                ← thin CLI wrapper
status.py              ← check mirror progress (packages done, rate, ETA)
size_estimate.py       ← estimate mirror size before committing to a full run
supplement/
  packages.txt         ← packages to supplement
  download.py          ← downloads packages + deps as cp310/manylinux wheels
  dist/                ← wheel output; DTA this to the server (not committed)
pyproject.toml         ← uv project; bandersnatch is the only dependency
```

## Setup

```bash
uv sync
```

## Commands

```bash
# (Re)generate bandersnatch.conf after changing config.py
uv run generate_conf.py

# Run the base mirror
bandersnatch mirror -c bandersnatch.conf

# Clean up unreferenced files after a mirror run
bandersnatch verify --delete -c bandersnatch.conf

# Check mirror progress
python status.py

# Estimate mirror size before running
python size_estimate.py

# Download supplement packages (run on internet-connected machine)
uv run supplement/download.py

# Merge supplement into mirror (run on server; re-run after each bandersnatch sync)
python merge.py
```

## Changing the target Python version or platform

Edit `config.py`, then re-run `generate_conf.py`. Do not edit `bandersnatch.conf` directly for anything that `config.py` controls.

## Test runs

To mirror just a few packages and verify filters are working, temporarily add to `bandersnatch.conf`:

```ini
[plugins]
enabled =
    allowlist_project
    regex_release_file_metadata
    latest_release

[allowlist]
packages =
    requests
    numpy
    cryptography
```

Expected result: numpy → only `cp310-manylinux-x86_64` wheels; cryptography → only `abi3-manylinux-x86_64`; requests → only `py3-none-any`. Zero `.tar.gz` files.

Remove the allowlist before re-running `generate_conf.py` — the generator rewrites the file from scratch.

## Gotchas

**Bandersnatch 7.x plugin names** — old-style `blocklist_release_files` and `keep_only_latest_releases` plugins do not exist in 7.x and are silently ignored. Correct plugins:
- `regex_release_file_metadata` — allowlist by filename regex
- `latest_release` — keep N most recent releases
- `allowlist_project` — restrict to specific packages (for test runs)

**10 workers is the hard maximum** — bandersnatch raises an exception above 10.

**musllinux wheels are excluded** by default. Commented-out lines in `generate_conf.py` re-enable them if Alpine Linux support is needed.
