#!/usr/bin/env python3
"""
pigeon-merge — fold supplement wheels into a PyPI mirror's simple/ index.

Standalone script with no dependencies beyond the Python standard library.
Works on Python 3.6+.

Usage:
    python3 pigeon-merge.py                          # auto-detect paths from pigeon.toml
    python3 pigeon-merge.py --mirror DIR --dist DIR  # explicit paths

Paths can be absolute or relative to the current directory.
If --mirror and --dist are omitted, the script walks up from the current
directory looking for pigeon.toml (the same way the pigeon CLI does).
"""
import argparse
import hashlib
import re
import shutil
import sys
from pathlib import Path


# ── pigeon.toml auto-detection ────────────────────────────────────────────────

def _find_config():
    here = Path.cwd().resolve()
    for directory in [here] + list(here.parents):
        candidate = directory / "pigeon.toml"
        if candidate.exists():
            return candidate
    return None


def _read_toml_str(text, key):
    m = re.search(r'^' + re.escape(key) + r'\s*=\s*"([^"]*)"', text, re.MULTILINE)
    return m.group(1) if m else None


def _paths_from_config(config_path):
    text = config_path.read_text()
    mirror_dir = _read_toml_str(text, "dir")
    dist_dir   = _read_toml_str(text, "dist_dir") or "supplement/dist"
    if not mirror_dir:
        return None, None
    base = config_path.parent
    mirror = Path(mirror_dir) if Path(mirror_dir).is_absolute() else (base / mirror_dir).resolve()
    dist   = Path(dist_dir)   if Path(dist_dir).is_absolute()   else (base / dist_dir).resolve()
    return mirror, dist


# ── Merge logic ───────────────────────────────────────────────────────────────

def _normalize(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_filename(filename):
    if filename.endswith(".whl"):
        m = re.match(r"^([A-Za-z0-9]([A-Za-z0-9._]*)?)-([0-9][^-]*)-", filename)
    else:
        m = re.match(r"^([A-Za-z0-9]([A-Za-z0-9._-]*)?)-([0-9][^-]+)\.(tar\.|zip)", filename)
    if m:
        return m.group(1), m.group(3)
    return None


def _update_simple_index(simple_dir, pkg_name, filename, digest):
    norm = _normalize(pkg_name)
    index_dir = simple_dir / norm
    index_dir.mkdir(parents=True, exist_ok=True)
    index_path = index_dir / "index.html"

    href = "/packages/supplement/{}#sha256={}".format(filename, digest)
    link = '    <a href="{}">{}</a>\n'.format(href, filename)

    if index_path.exists():
        content = index_path.read_text()
        if filename in content:
            return False
        index_path.write_text(content.replace("</body>", link + "</body>"))
    else:
        index_path.write_text(
            "<!DOCTYPE html>\n<html>\n"
            "  <head><title>Links for {}</title></head>\n"
            "  <body>\n    <h1>Links for {}</h1>\n"
            "{}"
            "  </body>\n</html>\n".format(pkg_name, pkg_name, link)
        )
    return True


def merge(mirror_dir, dist_dir):
    mirror_dir = Path(mirror_dir).resolve()
    dist_dir   = Path(dist_dir).resolve()

    packages_dir = mirror_dir / "web" / "packages" / "supplement"
    simple_dir   = mirror_dir / "web" / "simple"

    if not dist_dir.exists():
        print("Error: supplement dist dir not found: {}".format(dist_dir))
        print("Run `pigeon sync` on the internet side and DTA the dist folder over first.")
        sys.exit(1)

    files = [
        f for f in dist_dir.iterdir()
        if f.suffix in {".whl", ".gz", ".bz2", ".zip"} or f.name.endswith(".tar.gz")
    ]

    if not files:
        print("No packages found in {}".format(dist_dir))
        sys.exit(0)

    if not simple_dir.exists():
        print("Error: mirror simple/ dir not found at {}".format(simple_dir))
        print("Has bandersnatch run yet?")
        sys.exit(1)

    packages_dir.mkdir(parents=True, exist_ok=True)

    added = skipped = errors = 0
    total = len(files)

    for i, src in enumerate(sorted(files), 1):
        print("  [{}/{}] {}".format(i, total, src.name))
        result = _parse_filename(src.name)
        if not result:
            print("    SKIP (unparseable filename)")
            errors += 1
            continue

        pkg_name, _ = result
        dest = packages_dir / src.name
        if not dest.exists():
            shutil.copy2(src, dest)

        digest = _sha256(dest)
        is_new = _update_simple_index(simple_dir, pkg_name, src.name, digest)

        if is_new:
            print("    ADD")
            added += 1
        else:
            skipped += 1

    print("")
    if added:
        print("Done: {} added, {} already present, {} errors".format(added, skipped, errors))
        print("nginx will serve the new files immediately — no restart needed.")
    else:
        print("Done: {} already present, {} errors — nothing new to add.".format(skipped, errors))


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--mirror", metavar="DIR",
                        help="mirror root directory (contains web/simple/)")
    parser.add_argument("--dist", metavar="DIR",
                        help="supplement dist directory containing wheels")
    args = parser.parse_args()

    mirror_dir = args.mirror
    dist_dir   = args.dist

    if not mirror_dir or not dist_dir:
        config_path = _find_config()
        if config_path:
            detected_mirror, detected_dist = _paths_from_config(config_path)
            print("Using config: {}".format(config_path))
            mirror_dir = mirror_dir or detected_mirror
            dist_dir   = dist_dir   or detected_dist

    if not mirror_dir or not dist_dir:
        print("Error: could not determine paths. Pass --mirror and --dist explicitly,")
        print("or run from a directory containing pigeon.toml.")
        sys.exit(1)

    print("Mirror:  {}".format(mirror_dir))
    print("Dist:    {}".format(dist_dir))
    print("")
    merge(mirror_dir, dist_dir)


if __name__ == "__main__":
    main()
