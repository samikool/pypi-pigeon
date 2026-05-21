"""Tests for merge.py — filename parsing, normalization, and index updating."""
from __future__ import annotations

from pathlib import Path

import pytest

from pypi_pigeon.commands.merge import (
    _normalize,
    _parse_filename,
    _sha256,
    _update_simple_index,
)


# ── _normalize ────────────────────────────────────────────────────────────────

def test_normalize_hyphens():
    assert _normalize("my-package") == "my-package"

def test_normalize_underscores():
    assert _normalize("my_package") == "my-package"

def test_normalize_dots():
    assert _normalize("my.package") == "my-package"

def test_normalize_mixed():
    assert _normalize("My_Package.Name") == "my-package-name"

def test_normalize_runs_of_separators():
    assert _normalize("my--package") == "my-package"


# ── _parse_filename ───────────────────────────────────────────────────────────

def test_parse_filename_wheel():
    result = _parse_filename("numpy-1.26.0-cp310-cp310-manylinux_2_17_x86_64.whl")
    assert result == ("numpy", "1.26.0")

def test_parse_filename_wheel_complex_version():
    result = _parse_filename("cryptography-41.0.0-cp39-abi3-manylinux_2_17_x86_64.whl")
    assert result == ("cryptography", "41.0.0")

def test_parse_filename_none_any_wheel():
    result = _parse_filename("requests-2.31.0-py3-none-any.whl")
    assert result == ("requests", "2.31.0")

def test_parse_filename_sdist_tar_gz():
    result = _parse_filename("requests-2.31.0.tar.gz")
    assert result == ("requests", "2.31.0")

def test_parse_filename_sdist_zip():
    result = _parse_filename("mypackage-1.0.0.zip")
    assert result == ("mypackage", "1.0.0")

def test_parse_filename_invalid():
    assert _parse_filename("not-a-valid-file.txt") is None

def test_parse_filename_garbage():
    assert _parse_filename("garbage") is None


# ── _sha256 ───────────────────────────────────────────────────────────────────

def test_sha256_known_content(tmp_path):
    import hashlib
    content = b"hello world"
    f = tmp_path / "test.txt"
    f.write_bytes(content)
    expected = hashlib.sha256(content).hexdigest()
    assert _sha256(f) == expected

def test_sha256_empty_file(tmp_path):
    import hashlib
    f = tmp_path / "empty.txt"
    f.write_bytes(b"")
    assert _sha256(f) == hashlib.sha256(b"").hexdigest()


# ── _update_simple_index ──────────────────────────────────────────────────────

def test_update_simple_index_creates_new(tmp_path):
    simple_dir = tmp_path / "simple"
    simple_dir.mkdir()
    is_new = _update_simple_index(simple_dir, "requests", "requests-2.31.0-py3-none-any.whl", "abc123")
    assert is_new is True
    index = simple_dir / "requests" / "index.html"
    assert index.exists()
    content = index.read_text()
    assert "requests-2.31.0-py3-none-any.whl" in content
    assert "sha256=abc123" in content

def test_update_simple_index_appends_to_existing(tmp_path):
    simple_dir = tmp_path / "simple"
    simple_dir.mkdir()
    _update_simple_index(simple_dir, "requests", "requests-2.31.0-py3-none-any.whl", "abc123")
    is_new = _update_simple_index(simple_dir, "requests", "requests-2.32.0-py3-none-any.whl", "def456")
    assert is_new is True
    content = (simple_dir / "requests" / "index.html").read_text()
    assert "requests-2.31.0" in content
    assert "requests-2.32.0" in content

def test_update_simple_index_idempotent(tmp_path):
    simple_dir = tmp_path / "simple"
    simple_dir.mkdir()
    _update_simple_index(simple_dir, "requests", "requests-2.31.0-py3-none-any.whl", "abc123")
    is_new = _update_simple_index(simple_dir, "requests", "requests-2.31.0-py3-none-any.whl", "abc123")
    assert is_new is False

def test_update_simple_index_normalizes_package_name(tmp_path):
    simple_dir = tmp_path / "simple"
    simple_dir.mkdir()
    _update_simple_index(simple_dir, "My_Package", "My_Package-1.0.0-py3-none-any.whl", "abc123")
    assert (simple_dir / "my-package" / "index.html").exists()
