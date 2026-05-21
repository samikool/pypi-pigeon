# Changelog

## [0.1.0] — 2026-05-20

### Added
- Initial release of pypi-pigeon (formerly pymirror)
- `pigeon setup` — interactive TUI wizard to configure `pigeon.toml` and generate `bandersnatch.conf`
- `pigeon dry-run` — fetches PyPI metadata to estimate mirror size before committing; resumable via checkpoint file
- `pigeon sync` / `pigeon mirror` — runs bandersnatch then automatically fetches supplement packages with full transitive dependency resolution
- `pigeon merge` — folds `supplement/dist/` wheels into the mirror's `simple/` index; idempotent
- `pigeon add <pkg>` — appends packages to `requirements.txt` (deduped, case-insensitive)
- `--plain` flag on `dry-run`, `sync`/`mirror`, and `merge` for scripting and CI use
- `--config PATH` with git-style walk-up discovery — run commands from any subdirectory of your mirror workspace
- Support for Linux manylinux/musllinux, Windows, and macOS wheel targets
- Pure Python (`none-any`) wheels always included regardless of platform filter
