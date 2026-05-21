"""pigeon status — mirror health at a glance."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pypi_pigeon.config import Config
from pypi_pigeon.commands.update import run_check


def _fmt_mtime(path: Path) -> str:
    if not path.exists():
        return "never"
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")


def _count_packages(web_simple: Path) -> int:
    if not web_simple.exists():
        return 0
    return sum(1 for p in web_simple.iterdir() if p.is_dir())


def run_status(config: Config) -> None:
    mirror_dir = config.resolve(config.mirror.dir)
    web_simple = mirror_dir / "web" / "simple"
    packages_file = config.resolve(config.supplement.packages_file)
    dist_dir = config.resolve(config.supplement.dist_dir)

    print()
    print("Mirror")
    print(f"  directory   {mirror_dir}")
    print(f"  packages    {_count_packages(web_simple):,}")
    print(f"  last sync   {_fmt_mtime(web_simple)}")

    print()
    print("Supplement")
    pkg_count = sum(
        1 for line in (packages_file.read_text().splitlines() if packages_file.exists() else [])
        if line.strip() and not line.startswith("#")
    )
    wheel_count = len(list(dist_dir.glob("*.whl"))) if dist_dir.exists() else 0
    print(f"  tracked     {pkg_count} package{'s' if pkg_count != 1 else ''}")
    print(f"  cached      {wheel_count:,} wheels in {dist_dir}")

    print()
    run_check(config)
