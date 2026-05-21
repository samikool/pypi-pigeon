"""Tests for add.py — package list management."""
from __future__ import annotations

from pathlib import Path

import pytest

from pypi_pigeon.commands.add import add_packages


def test_add_creates_file(tmp_path):
    f = tmp_path / "requirements.txt"
    add_packages(["requests"], f)
    assert f.exists()
    assert "requests" in f.read_text()

def test_add_creates_parent_dirs(tmp_path):
    f = tmp_path / "sub" / "dir" / "requirements.txt"
    add_packages(["requests"], f)
    assert f.exists()

def test_add_deduplicates(tmp_path):
    f = tmp_path / "requirements.txt"
    add_packages(["requests"], f)
    add_packages(["requests"], f)
    lines = [l for l in f.read_text().splitlines() if l.strip()]
    assert lines.count("requests") == 1

def test_add_case_insensitive_dedup(tmp_path):
    f = tmp_path / "requirements.txt"
    add_packages(["Requests"], f)
    add_packages(["requests"], f)
    lines = [l for l in f.read_text().splitlines() if l.strip()]
    assert len(lines) == 1

def test_add_multiple_packages(tmp_path):
    f = tmp_path / "requirements.txt"
    add_packages(["requests", "numpy", "pandas"], f)
    content = f.read_text()
    assert "requests" in content
    assert "numpy" in content
    assert "pandas" in content

def test_add_preserves_existing(tmp_path):
    f = tmp_path / "requirements.txt"
    f.write_text("requests\n")
    add_packages(["numpy"], f)
    content = f.read_text()
    assert "requests" in content
    assert "numpy" in content

def test_add_ignores_comments_in_existing(tmp_path):
    f = tmp_path / "requirements.txt"
    f.write_text("# this is a comment\nrequests\n")
    add_packages(["requests"], f)
    lines = [l for l in f.read_text().splitlines() if l.strip() and not l.startswith("#")]
    assert lines.count("requests") == 1
