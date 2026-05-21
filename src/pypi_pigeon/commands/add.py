"""pigeon add — append packages to the supplement list."""
from __future__ import annotations

from pathlib import Path


def add_packages(packages: list[str], packages_file: Path) -> None:
    packages_file.parent.mkdir(parents=True, exist_ok=True)

    existing: set[str] = set()
    if packages_file.exists():
        for line in packages_file.read_text().splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                existing.add(stripped.lower())

    to_add = [p for p in packages if p.lower() not in existing]
    already = [p for p in packages if p.lower() in existing]

    if to_add:
        with packages_file.open("a") as f:
            for p in to_add:
                f.write(p + "\n")

    for p in already:
        print(f"  already  {p}")
    for p in to_add:
        print(f"  added    {p}")

    print()
    if to_add:
        print(f"{len(to_add)} package(s) added to {packages_file}")
        print("These will be fetched with full dependency resolution during `pigeon sync`.")
        print("Every transitive dependency is resolved and downloaded as a wheel — no surprises on the airgapped side.")
    else:
        print(f"Nothing new — all packages already in {packages_file}")
