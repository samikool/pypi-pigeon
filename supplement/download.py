#!/usr/bin/env python3
"""
Downloads packages listed in packages.txt (plus all their dependencies)
as binary wheels for the target Python version and platform.

Run: uv run supplement/download.py

Output lands in supplement/dist/ — DTA that directory to the airgapped server,
then run merge.py to fold it into the served mirror.
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import PYTHON_VERSION, PLATFORM

DIST_DIR = Path(__file__).parent / "dist"
PACKAGES_FILE = Path(__file__).parent / "packages.txt"


def main():
    if not PACKAGES_FILE.exists():
        print(f"Missing {PACKAGES_FILE}")
        sys.exit(1)

    pkgs = [
        line.strip()
        for line in PACKAGES_FILE.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]

    if not pkgs:
        print(f"No packages listed in {PACKAGES_FILE} — add some and re-run.")
        return

    DIST_DIR.mkdir(exist_ok=True)

    py_nodot = PYTHON_VERSION.replace(".", "")   # "3.10" -> "310"
    abi = f"cp{py_nodot}"                        # "cp310"

    cmd = [
        "uv", "run", "pip", "download",
        "--python-version", py_nodot,
        "--platform", PLATFORM,
        "--abi", abi,
        "--only-binary", ":all:",
        "-d", str(DIST_DIR),
        "-r", str(PACKAGES_FILE),
    ]

    print(f"Target:  Python {PYTHON_VERSION} ({abi}) on {PLATFORM}")
    print(f"Output:  {DIST_DIR}")
    print(f"Packages: {len(pkgs)}\n")

    result = subprocess.run(cmd)

    wheels = list(DIST_DIR.glob("*.whl"))
    print(f"\nTotal wheels in dist/: {len(wheels)}")

    if result.returncode != 0:
        print(
            "\nOne or more packages failed. If a package has no binary wheel for this "
            "platform, you can add its sdist manually to supplement/dist/ and the "
            "merge script will pick it up."
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
