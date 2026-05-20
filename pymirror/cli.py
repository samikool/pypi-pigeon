#!/usr/bin/env python3
"""
pymirror — TUI toolkit for maintaining a PyPI mirror on an airgapped network.

Commands:
  setup     Wizard: configure mirror and generate bandersnatch.conf
  dry-run   Fetch PyPI metadata to preview mirror size (hits PyPI — needs internet)
  sync      Run bandersnatch mirror + fetch supplement packages (needs internet)
  mirror    Alias for sync (bandersnatch uses this term)
  merge     Fold supplement/dist/ into the served mirror (airgapped server)
  add       Add packages to the supplement list (fetched with full dep resolution during sync)
"""
import argparse
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="pymirror",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--config", type=Path, default=None,
        metavar="PATH",
        help="path to pymirror.toml (default: search up from current directory)",
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

    p_add = sub.add_parser("add", help="add packages to the supplement list")
    p_add.add_argument(
        "packages", nargs="+", metavar="PACKAGE",
        help="package names to track (e.g. requests 'numpy==1.26.0')",
    )

    args = parser.parse_args()
    _run(args, args.command)


def _load_config(config_path: Path | None):
    from pymirror.config import load, find_config
    if config_path is None:
        config_path = find_config()
        if config_path is None:
            print("No pymirror.toml found — run `pymirror setup` first.")
            sys.exit(1)
    try:
        return load(config_path)
    except FileNotFoundError:
        print(f"No config found at {config_path} — run `pymirror setup` first.")
        sys.exit(1)


def _run(args, command: str) -> None:
    """Run a command, then follow the chain if the app requests it."""
    next_cmd: str | None = command

    while next_cmd:
        cmd = next_cmd
        next_cmd = None

        if cmd == "setup":
            from pymirror.config import DEFAULT_CONFIG_PATH, find_config
            from pymirror.commands.setup import SetupApp
            config_path = args.config or find_config() or DEFAULT_CONFIG_PATH
            app = SetupApp(config_path=config_path)
            app.run(inline=True)
            next_cmd = app.next_command

        elif cmd == "dry-run":
            config = _load_config(args.config)
            workers = getattr(args, "workers", None) or config.supplement.fetch_workers
            reset = getattr(args, "reset", False)
            if getattr(args, "plain", False):
                from pymirror.commands.dry_run import run_headless
                run_headless(config, workers=workers, reset=reset)
            else:
                from pymirror.commands.dry_run import DryRunApp
                app = DryRunApp(config=config, workers=workers, reset=reset)
                app.run(inline=True)
                next_cmd = app.next_command

        elif cmd in ("sync", "mirror"):
            config = _load_config(args.config)
            if getattr(args, "plain", False):
                from pymirror.commands.sync import run_headless
                run_headless(config)
            else:
                from pymirror.commands.sync import SyncApp
                app = SyncApp(config=config)
                app.run(inline=True)
                next_cmd = app.next_command

        elif cmd == "merge":
            config = _load_config(args.config)
            if getattr(args, "plain", False):
                from pymirror.commands.merge import run_headless
                run_headless(config)
            else:
                from pymirror.commands.merge import MergeApp
                app = MergeApp(config=config)
                app.run(inline=True)
                next_cmd = app.next_command

        elif cmd == "add":
            config = _load_config(args.config)
            from pymirror.commands.add import add_packages
            add_packages(args.packages, config.resolve(config.supplement.packages_file))
            next_cmd = None


if __name__ == "__main__":
    main()
