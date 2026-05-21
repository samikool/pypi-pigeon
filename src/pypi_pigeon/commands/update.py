"""pigeon update — check supplement packages against PyPI and/or run a full sync."""
from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path

from pypi_pigeon.config import Config


# ── Shared helpers (also used by status.py) ───────────────────────────────────

def read_packages(packages_file: Path) -> list[str]:
    """Return normalized package names from requirements.txt (no versions, no extras)."""
    if not packages_file.exists():
        return []
    names = []
    for line in packages_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name = re.split(r"[>=<!;\[]", line)[0].strip()
        if name:
            names.append(name)
    return names


def installed_versions(dist_dir: Path, package_names: set[str]) -> dict[str, str]:
    """Return {normalized_name: highest_version} for wheels present in dist_dir."""
    versions: dict[str, str] = {}
    if not dist_dir.exists():
        return versions
    for wheel in dist_dir.glob("*.whl"):
        parts = wheel.stem.split("-")
        if len(parts) >= 2:
            name = _normalize(parts[0])
            version = parts[1]
            if name in package_names:
                if name not in versions or _ver_gt(version, versions[name]):
                    versions[name] = version
    return versions


def latest_pypi_version(package: str) -> str | None:
    try:
        url = f"https://pypi.org/pypi/{package}/json"
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
        return data["info"]["version"]
    except Exception:
        return None


def _normalize(name: str) -> str:
    return name.lower().replace("_", "-").replace(".", "-")


def _ver_gt(a: str, b: str) -> bool:
    try:
        from packaging.version import Version
        return Version(a) > Version(b)
    except Exception:
        return a > b


# ── Check logic ───────────────────────────────────────────────────────────────

def run_check(config: Config) -> None:
    packages_file = config.resolve(config.supplement.packages_file)
    dist_dir = config.resolve(config.supplement.dist_dir)
    packages = read_packages(packages_file)

    if not packages:
        print("No packages in requirements.txt.")
        return

    print(f"Checking {len(packages)} package(s) against PyPI...")

    package_set = {_normalize(p) for p in packages}
    installed = installed_versions(dist_dir, package_set)

    outdated = []
    not_downloaded = []
    errors = []

    for pkg in packages:
        norm = _normalize(pkg)
        latest = latest_pypi_version(pkg)
        if latest is None:
            errors.append(pkg)
            continue
        current = installed.get(norm)
        if current is None:
            not_downloaded.append((pkg, latest))
        elif _ver_gt(latest, current):
            outdated.append((pkg, current, latest))

    if outdated:
        print()
        print(f"  {'package':<30} {'installed':<15} latest")
        print(f"  {'-'*30} {'-'*15} {'------'}")
        for pkg, current, latest in outdated:
            print(f"  {pkg:<30} {current:<15} {latest}")

    if not_downloaded:
        print()
        print("  Not yet downloaded:")
        for pkg, latest in not_downloaded:
            print(f"    {pkg}  ({latest} available on PyPI)")

    if errors:
        print()
        print(f"  Could not check: {', '.join(errors)}")

    if not outdated and not not_downloaded and not errors:
        print("All packages up to date.")
    elif outdated or not_downloaded:
        print()
        print("Run `pigeon update` to sync.")


# ── Update (full sync) ────────────────────────────────────────────────────────

def run_update(config: Config, plain: bool = False) -> None:
    if plain:
        from pypi_pigeon.commands.sync import run_headless
        run_headless(config)
    else:
        from pypi_pigeon.commands.sync import SyncApp
        app = SyncApp(config=config)
        app.run(inline=True)
