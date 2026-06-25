import json
import sys
import os
import pytest
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from cli import state_path, read_state, write_state

def _home_env(tmp_path):
    """Return env dict that redirects Path.home() to tmp_path on Windows and POSIX."""
    return {**os.environ, "HOME": str(tmp_path), "USERPROFILE": str(tmp_path)}

def test_state_path_format(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    p = state_path("ab12")
    assert p == tmp_path / ".trafficlight" / "ab12.json"

def test_write_and_read_state(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    write_state("ab12", {"color": "green", "command": None})
    result = read_state("ab12")
    assert result == {"color": "green", "command": None}

def test_write_state_atomic(tmp_path, monkeypatch):
    """State dir is created automatically."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    write_state("cd34", {"color": "red", "command": None})
    assert (tmp_path / ".trafficlight" / "cd34.json").exists()

def test_read_state_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert read_state("0000") is None
