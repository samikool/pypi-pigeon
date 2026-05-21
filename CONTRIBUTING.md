# Contributing to pypi-pigeon

## Setup

```bash
git clone https://github.com/samikool/pypi-pigeon
cd pymirror
uv sync --dev
```

## Branches

- `master` — release branch; only updated via the release process
- `dev` — active development; open PRs against this branch

## Commit convention

We use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add support for aarch64 supplement targeting
fix: resolve bandersnatch.conf path when running from subdirectory
chore: update bandersnatch to 7.2.0
docs: clarify merge idempotency in README
refactor: extract _merge_core to share logic between TUI and headless
```

- Present tense, lowercase after the colon
- Keep the subject line under 72 characters
- No period at the end

## Running tests

```bash
uv run pytest
```

Tests cover the pure functions in `config.py`, `merge.py`, `dry_run.py`, and `add.py`. The TUI apps themselves are not tested (they require a terminal).

## Linting

```bash
uv run ruff check src/
```

## Release process (maintainers only)

1. Ensure you're on `dev` and it's up to date
2. Update `CHANGELOG.md` with the new version and release notes
3. Bump the version in `pyproject.toml`
4. Commit: `bump version to X.Y.Z`
5. Tag: `git tag vX.Y.Z`
6. Push: `git push origin dev --tags`

The release workflow triggers automatically on the `v*` tag:
- Runs lint + tests + build
- Creates a GitHub Release with auto-generated notes
- Publishes to PyPI
- Backmerges `master → dev`

The `PYPI_TOKEN` secret must be set in the repo settings for publishing to work.
