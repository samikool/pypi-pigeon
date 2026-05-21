"""Tests for dry_run.py — formatting helpers and pattern matching."""
from __future__ import annotations

import re

import pytest

from pypi_pigeon.commands.dry_run import (
    _compile_patterns,
    _fmt_eta,
    _latest_versions,
    _matches_any,
    fmt,
)
from pypi_pigeon.config import Config, FilterConfig


# ── fmt ───────────────────────────────────────────────────────────────────────

def test_fmt_bytes():
    assert fmt(500) == "500 B"

def test_fmt_kilobytes():
    assert fmt(1_500) == "1.5 KB"

def test_fmt_megabytes():
    assert fmt(2_500_000) == "2.5 MB"

def test_fmt_gigabytes():
    assert fmt(1_500_000_000) == "1.5 GB"

def test_fmt_terabytes():
    assert fmt(1_500_000_000_000) == "1.5 TB"


# ── _fmt_eta ──────────────────────────────────────────────────────────────────

def test_fmt_eta_seconds():
    assert _fmt_eta(45) == "45s"

def test_fmt_eta_minutes():
    assert _fmt_eta(125) == "2m 5s"

def test_fmt_eta_hours():
    assert _fmt_eta(3700) == "1h 1m"

def test_fmt_eta_infinity():
    assert _fmt_eta(float("inf")) == "—"

def test_fmt_eta_very_large():
    assert _fmt_eta(999999) == "—"


# ── _latest_versions ──────────────────────────────────────────────────────────

def test_latest_versions_keeps_n(sample_releases):
    result = _latest_versions(sample_releases, keep=2)
    assert len(result) == 2

def test_latest_versions_returns_newest_first(sample_releases):
    result = _latest_versions(sample_releases, keep=2)
    assert result[0] == "1.3.0"

def test_latest_versions_keep_all(sample_releases):
    result = _latest_versions(sample_releases, keep=10)
    assert len(result) == 3

def test_latest_versions_empty():
    assert _latest_versions({}, keep=3) == []

@pytest.fixture
def sample_releases():
    return {
        "1.1.0": [{"upload_time": "2023-01-01T00:00:00"}],
        "1.2.0": [{"upload_time": "2023-06-01T00:00:00"}],
        "1.3.0": [{"upload_time": "2024-01-01T00:00:00"}],
    }


# ── _matches_any / _compile_patterns ─────────────────────────────────────────

def _make_config(versions=None, platforms=None, include_sdists=False):
    return Config(
        filter=FilterConfig(
            python_versions=versions or ["3.10"],
            platforms=platforms or ["linux-manylinux-x86_64"],
            include_sdists=include_sdists,
        )
    )

def test_matches_cp_wheel():
    config = _make_config()
    patterns = _compile_patterns(config)
    assert _matches_any("numpy-1.26.0-cp310-cp310-manylinux_2_17_x86_64.whl", patterns)

def test_matches_abi3_wheel():
    config = _make_config()
    patterns = _compile_patterns(config)
    assert _matches_any("cryptography-41.0.0-cp39-abi3-manylinux_2_17_x86_64.whl", patterns)

def test_matches_none_any_wheel():
    config = _make_config()
    patterns = _compile_patterns(config)
    assert _matches_any("requests-2.31.0-py3-none-any.whl", patterns)

def test_does_not_match_wrong_platform():
    config = _make_config()
    patterns = _compile_patterns(config)
    assert not _matches_any("numpy-1.26.0-cp310-cp310-win_amd64.whl", patterns)

def test_does_not_match_sdist_by_default():
    config = _make_config()
    patterns = _compile_patterns(config)
    assert not _matches_any("numpy-1.26.0.tar.gz", patterns)

def test_matches_sdist_when_enabled():
    config = _make_config(include_sdists=True)
    patterns = _compile_patterns(config)
    assert _matches_any("numpy-1.26.0.tar.gz", patterns)
