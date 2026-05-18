#!/usr/bin/env python3
"""
Generates bandersnatch.conf from config.py.
Run: uv run generate_conf.py
"""
from pathlib import Path
from config import PYTHON_VERSION, PLATFORM, MIRROR_DIR, MIRROR_WORKERS, KEEP_RELEASES, PYPI_MASTER


def cp_tag(version: str) -> str:
    return "cp" + version.replace(".", "")


def allowlist_patterns(python_version: str) -> list[str]:
    target = cp_tag(python_version)
    # bandersnatch 7.x uses regex_release_file_metadata as an allowlist:
    # files matching ANY pattern are kept; everything else (sdists, wrong
    # platforms, wrong Python versions) is dropped automatically.
    return [
        # Compiled wheels for the target CPython version on manylinux x86_64
        rf".*-{target}-.*-manylinux.*x86_64.*\.whl$",
        rf".*-{target}-.*-linux_x86_64\.whl$",
        # Stable ABI wheels (abi3) — compatible with target and earlier minima
        r".*-abi3-manylinux.*x86_64.*\.whl$",
        r".*-abi3-linux_x86_64\.whl$",
        # Pure Python / universal wheels (py3-none-any, py2.py3-none-any, etc.)
        r".*-none-any\.whl$",
        # Uncomment to add Alpine/musl Linux support:
        # rf".*-{target}-.*-musllinux.*x86_64.*\.whl$",
        # r".*-abi3-musllinux.*x86_64.*\.whl$",
    ]


def generate() -> str:
    patterns = allowlist_patterns(PYTHON_VERSION)
    patterns_str = "\n    ".join(patterns)

    return f"""\
[mirror]
directory = {MIRROR_DIR}
json = false
master = {PYPI_MASTER}
timeout = 10
workers = {MIRROR_WORKERS}
hash-index = false
storage-backend = filesystem
verifiers = 3
keep_index_versions = 0
release-files = true
compare-mirrors = false

[plugins]
enabled =
    regex_release_file_metadata
    latest_release

[regex_release_file_metadata]
any:release_file.filename =
    {patterns_str}

[latest_release]
keep = {KEEP_RELEASES}
"""


if __name__ == "__main__":
    conf = generate()
    out = Path("bandersnatch.conf")
    out.write_text(conf)
    print(f"Written: {out}")
    print(f"Target:  Python {PYTHON_VERSION} ({cp_tag(PYTHON_VERSION)}) on {PLATFORM}")
    print(f"Mirror:  {MIRROR_DIR}")
    print(f"Keeping: {KEEP_RELEASES} releases per package")
