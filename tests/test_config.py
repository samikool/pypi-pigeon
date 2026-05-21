"""Tests for config.py — pure functions and path logic."""
from __future__ import annotations

from pathlib import Path

import pytest

from pypi_pigeon.config import (
    Config,
    FilterConfig,
    MirrorConfig,
    SupplementConfig,
    allowlist_patterns,
    cp_tag,
    find_config,
)


# ── cp_tag ────────────────────────────────────────────────────────────────────

def test_cp_tag_basic():
    assert cp_tag("3.10") == "cp310"

def test_cp_tag_single_digit():
    assert cp_tag("3.9") == "cp39"

def test_cp_tag_newer():
    assert cp_tag("3.13") == "cp313"


# ── find_config ───────────────────────────────────────────────────────────────

def test_find_config_finds_in_current_dir(tmp_path):
    config = tmp_path / "pigeon.toml"
    config.write_text("")
    assert find_config(tmp_path) == config

def test_find_config_walks_up(tmp_path):
    config = tmp_path / "pigeon.toml"
    config.write_text("")
    subdir = tmp_path / "a" / "b" / "c"
    subdir.mkdir(parents=True)
    assert find_config(subdir) == config

def test_find_config_returns_none_when_missing(tmp_path):
    assert find_config(tmp_path) is None

def test_find_config_prefers_closer_config(tmp_path):
    parent_config = tmp_path / "pigeon.toml"
    parent_config.write_text("")
    subdir = tmp_path / "sub"
    subdir.mkdir()
    child_config = subdir / "pigeon.toml"
    child_config.write_text("")
    assert find_config(subdir) == child_config


# ── Config.resolve ────────────────────────────────────────────────────────────

def test_resolve_absolute_passthrough():
    c = Config(config_dir=Path("/some/dir"))
    assert c.resolve("/etc/foo") == Path("/etc/foo")

def test_resolve_relative_anchors_to_config_dir():
    c = Config(config_dir=Path("/mirror-work"))
    assert c.resolve("supplement/dist") == Path("/mirror-work/supplement/dist")

def test_resolve_relative_normalizes():
    c = Config(config_dir=Path("/mirror-work"))
    assert c.resolve("./supplement/../supplement/dist") == Path("/mirror-work/supplement/dist")


# ── allowlist_patterns ────────────────────────────────────────────────────────

def test_allowlist_patterns_always_includes_none_any():
    patterns = allowlist_patterns(["3.10"], ["linux-manylinux-x86_64"])
    assert any("none-any" in p for p in patterns)

def test_allowlist_patterns_includes_cp_wheel():
    patterns = allowlist_patterns(["3.10"], ["linux-manylinux-x86_64"])
    assert any("cp310" in p for p in patterns)

def test_allowlist_patterns_includes_abi3():
    patterns = allowlist_patterns(["3.10"], ["linux-manylinux-x86_64"])
    assert any("abi3" in p for p in patterns)

def test_allowlist_patterns_no_sdists_by_default():
    patterns = allowlist_patterns(["3.10"], ["linux-manylinux-x86_64"])
    assert not any("tar.gz" in p for p in patterns)

def test_allowlist_patterns_includes_sdists_when_requested():
    patterns = allowlist_patterns(["3.10"], ["linux-manylinux-x86_64"], include_sdists=True)
    assert any(r"\.tar\.gz" in p for p in patterns)

def test_allowlist_patterns_multiple_versions():
    patterns = allowlist_patterns(["3.10", "3.12"], ["linux-manylinux-x86_64"])
    assert any("cp310" in p for p in patterns)
    assert any("cp312" in p for p in patterns)

def test_allowlist_patterns_multiple_platforms():
    patterns = allowlist_patterns(["3.10"], ["linux-manylinux-x86_64", "linux-manylinux-aarch64"])
    assert any("x86_64" in p for p in patterns)
    assert any("aarch64" in p for p in patterns)

def test_allowlist_patterns_are_valid_regex():
    import re
    patterns = allowlist_patterns(["3.10"], ["linux-manylinux-x86_64"], include_sdists=True)
    for p in patterns:
        re.compile(p)  # should not raise

def test_allowlist_patterns_match_expected_wheels():
    import re
    patterns = [re.compile(p) for p in allowlist_patterns(["3.10"], ["linux-manylinux-x86_64"])]

    def matches(filename):
        return any(p.match(filename) for p in patterns)

    assert matches("numpy-1.26.0-cp310-cp310-manylinux_2_17_x86_64.manylinux2014_x86_64.whl")
    assert matches("cryptography-41.0.0-cp39-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64.whl")
    assert matches("requests-2.31.0-py3-none-any.whl")
    assert not matches("numpy-1.26.0-cp310-cp310-win_amd64.whl")
    assert not matches("numpy-1.26.0.tar.gz")
