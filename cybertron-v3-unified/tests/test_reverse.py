"""Tests for reverse engineering."""
import pytest
import tempfile
from pathlib import Path
from cybertron.reverse_engineering.analyzer import ReverseEngineer


def test_detect_pe():
    with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
        f.write(b"MZ" + b"\x00" * 100)
        path = f.name
    re = ReverseEngineer(target=path)
    re._load()
    re._detect_type()
    assert re.analysis.file_type == "PE"
    Path(path).unlink()


def test_detect_elf():
    with tempfile.NamedTemporaryFile(suffix=".elf", delete=False) as f:
        f.write(b"\x7fELF" + b"\x00" * 100)
        path = f.name
    re = ReverseEngineer(target=path)
    re._load()
    re._detect_type()
    assert re.analysis.file_type == "ELF"
    Path(path).unlink()
