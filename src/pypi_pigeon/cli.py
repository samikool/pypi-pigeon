#!/usr/bin/env python3
"""
pigeon — TUI toolkit for maintaining a PyPI mirror on an airgapped network.

Commands:
  setup     Wizard: configure mirror and generate bandersnatch.conf
  dry-run   Fetch PyPI metadata to preview mirror size (hits PyPI — needs internet)
  sync      Run bandersnatch mirror + fetch supplement packages (needs internet)
  mirror    Alias for sync (bandersnatch uses this term)
  update    Sync mirror and supplement packages (alias for sync with update framing)
  merge     Fold supplement/dist/ into the served mirror (airgapped server)
  add       Add packages to the supplement list (fetched with full dep resolution during sync)
  status    Show mirror health and check supplement packages for updates
"""
import argparse
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="pigeon",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--config", type=Path, default=None,
        metavar="PATH",
        help="path to pigeon.toml (default: search up from current directory)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("setup", help="wizard: configure and generate bandersnatch.conf")

    p_dr = sub.add_parser("dry-run", help="fetch PyPI metadata to preview mirror size before syncing")
    p_dr.add_argument("--workers", type=int, default=None,
                      help="parallel HTTP workers (overrides config)")
    p_dr.add_argument("--reset", action="store_true",
                      help="clear checkpoint and start from scratch")
    p_dr.add_argument("--plain", action="store_true",
                      help="stream output to stdout without TUI")

    for _name in ("sync", "mirror"):
        _p = sub.add_parser(_name, help="run bandersnatch mirror with live TUI" if _name == "sync" else "alias for sync")
        _p.add_argument("--plain", action="store_true",
                        help="stream output to stdout without TUI")

    p_merge = sub.add_parser("merge", help="fold supplement/dist/ into the mirror")
    p_merge.add_argument("--plain", action="store_true",
                         help="stream output to stdout without TUI")

    p_update = sub.add_parser("update", help="sync mirror and supplement packages")
    p_update.add_argument("--check", action="store_true",
                          help="check for outdated supplement packages without syncing")
    p_update.add_argument("--plain", action="store_true",
                          help="stream output to stdout without TUI")

    p_add = sub.add_parser("add", help="add packages to the supplement list")
    p_add.add_argument(
        "packages", nargs="+", metavar="PACKAGE",
        help="package names to track (e.g. requests 'numpy==1.26.0')",
    )

    sub.add_parser("status", help="show mirror health and check supplement packages for updates")

    args = parser.parse_args()
    _run(args, args.command)


def _load_config(config_path: Path | None):
    from pypi_pigeon.config import load, find_config
    if config_path is None:
        config_path = find_config()
        if config_path is None:
            print("No pigeon.toml found — run `pigeon setup` first.")
            sys.exit(1)
    try:
        return load(config_path)
    except FileNotFoundError:
        print(f"No config found at {config_path} — run `pigeon setup` first.")
        sys.exit(1)


def _run(args, command: str) -> None:
    """Run a command, then follow the chain if the app requests it."""
    next_cmd: str | None = command

    while next_cmd:
        cmd = next_cmd
        next_cmd = None

        if cmd == "setup":
            from pypi_pigeon.config import DEFAULT_CONFIG_PATH, find_config
            from pypi_pigeon.commands.setup import SetupApp
            config_path = args.config or find_config() or DEFAULT_CONFIG_PATH
            app = SetupApp(config_path=config_path)
            app.run(inline=True)
            next_cmd = app.next_command

        elif cmd == "dry-run":
            config = _load_config(args.config)
            workers = getattr(args, "workers", None)
            reset = getattr(args, "reset", False)
            if getattr(args, "plain", False):
                from pypi_pigeon.commands.dry_run import run_headless
                run_headless(config, workers=workers, reset=reset)
            else:
                from pypi_pigeon.commands.dry_run import DryRunApp
                app = DryRunApp(config=config, workers=workers, reset=reset)
                app.run(inline=True)
                next_cmd = app.next_command

        elif cmd in ("sync", "mirror"):
            config = _load_config(args.config)
            if getattr(args, "plain", False):
                from pypi_pigeon.commands.sync import run_headless
                run_headless(config)
            else:
                from pypi_pigeon.commands.sync import SyncApp
                app = SyncApp(config=config)
                app.run(inline=True)
                next_cmd = app.next_command

        elif cmd == "merge":
            config = _load_config(args.config)
            if getattr(args, "plain", False):
                from pypi_pigeon.commands.merge import run_headless
                run_headless(config)
            else:
                from pypi_pigeon.commands.merge import MergeApp
                app = MergeApp(config=config)
                app.run(inline=True)
                next_cmd = app.next_command

        elif cmd == "update":
            config = _load_config(args.config)
            if getattr(args, "check", False):
                from pypi_pigeon.commands.update import run_check
                run_check(config)
            else:
                from pypi_pigeon.commands.update import run_update
                run_update(config, plain=getattr(args, "plain", False))

        elif cmd == "add":
            config = _load_config(args.config)
            from pypi_pigeon.commands.add import add_packages
            add_packages(args.packages, config.resolve(config.supplement.packages_file))
            next_cmd = None

        elif cmd == "status":
            config = _load_config(args.config)
            from pypi_pigeon.commands.status import run_status
            run_status(config)


if __name__ == "__main__":
    main()
