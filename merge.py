#!/usr/bin/env python3
"""
Merges supplement/dist/ wheels into the bandersnatch mirror.

Run this on the airgapped server after dropping new wheels into supplement/dist/:
    python merge.py

What it does:
  1. Copies each wheel to <mirror>/web/packages/supplement/
  2. Creates or updates <mirror>/web/simple/<package>/index.html

Re-run after every bandersnatch sync — bandersnatch overwrites simple indexes
for packages it knows about, so supplement links need to be re-applied.
The script is fully idempotent.
"""
import hashlib
import re
import shutil
import sys
from pathlib import Path

from config import MIRROR_DIR

MIRROR = Path(MIRROR_DIR)
SUPPLEMENT_DIST = Path(__file__).parent / "supplement" / "dist"
PACKAGES_DIR = MIRROR / "web" / "packages" / "supplement"
SIMPLE_DIR = MIRROR / "web" / "simple"


def normalize(name: str) -> str:
    """PEP 503 package name normalization."""
    return re.sub(r"[-_.]+", "-", name).lower()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_filename(filename: str) -> tuple[str, str] | None:
    """
    Extract (package_name, version) from a wheel or sdist filename.
    Returns None if the filename can't be parsed.
    """
    if filename.endswith(".whl"):
        # Wheel: {name}-{version}-{python}-{abi}-{platform}.whl
        m = re.match(r"^([A-Za-z0-9]([A-Za-z0-9._]*)?)-([0-9][^-]*)-", filename)
    else:
        # Sdist: {name}-{version}.tar.gz / .zip / etc.
        m = re.match(r"^([A-Za-z0-9]([A-Za-z0-9._-]*)?)-([0-9][^-]+)\.(tar\.|zip)", filename)

    if m:
        return m.group(1), m.group(3)
    return None


def update_simple_index(pkg_name: str, filename: str, digest: str) -> bool:
    """
    Add a file link to the package's simple index.
    Returns True if the entry was newly added, False if it was already present.
    """
    norm = normalize(pkg_name)
    index_dir = SIMPLE_DIR / norm
    index_dir.mkdir(parents=True, exist_ok=True)
    index_path = index_dir / "index.html"

    href = f"/packages/supplement/{filename}#sha256={digest}"
    link = f'    <a href="{href}">{filename}</a>\n'

    if index_path.exists():
        content = index_path.read_text()
        if filename in content:
            return False
        # Bandersnatch-generated indexes end with </body>\n</html>\n
        # Append our link just before </body>
        index_path.write_text(content.replace("</body>", f"{link}</body>"))
    else:
        # New package not in bandersnatch mirror — create index from scratch
        index_path.write_text(
            f"<!DOCTYPE html>\n<html>\n"
            f"  <head><title>Links for {pkg_name}</title></head>\n"
            f"  <body>\n    <h1>Links for {pkg_name}</h1>\n"
            f"{link}"
            f"  </body>\n</html>\n"
        )

    return True


def merge():
    if not SUPPLEMENT_DIST.exists():
        print(f"supplement/dist/ not found — run supplement/download.py first.")
        sys.exit(1)

    files = [
        f for f in SUPPLEMENT_DIST.iterdir()
        if f.suffix in {".whl", ".gz", ".bz2", ".zip"} or f.name.endswith(".tar.gz")
    ]

    if not files:
        print("No packages found in supplement/dist/")
        return

    if not SIMPLE_DIR.exists():
        print(f"Mirror simple/ dir not found at {SIMPLE_DIR}")
        print("Has bandersnatch run yet? Set MIRROR_DIR in config.py and run bandersnatch.")
        sys.exit(1)

    PACKAGES_DIR.mkdir(parents=True, exist_ok=True)

    added = skipped = errors = 0

    for src in sorted(files):
        result = parse_filename(src.name)
        if not result:
            print(f"  SKIP  (unparseable): {src.name}")
            errors += 1
            continue

        pkg_name, version = result
        dest = PACKAGES_DIR / src.name

        if not dest.exists():
            shutil.copy2(src, dest)

        digest = sha256(dest)
        is_new = update_simple_index(pkg_name, src.name, digest)

        if is_new:
            print(f"  ADD   {src.name}")
            added += 1
        else:
            skipped += 1

    print(f"\nDone: {added} added, {skipped} already present, {errors} errors")
    if added:
        print("nginx will serve the new files immediately — no restart needed.")


if __name__ == "__main__":
    merge()
