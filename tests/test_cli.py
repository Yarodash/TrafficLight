import json
import sys
import os
import pytest
from pathlib import Path
from unittest import mock

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import cli
from cli import state_path, read_state, write_state, _find_existing_light, _acquire_create_lock, _release_create_lock

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

def test_write_state_creates_missing_dir(tmp_path, monkeypatch):
    """State dir is created automatically."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    write_state("cd34", {"color": "red", "command": None})
    assert (tmp_path / ".trafficlight" / "cd34.json").exists()

def test_read_state_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert read_state("0000") is None


def test_find_existing_light_returns_id_when_window_alive(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    write_state("aa11", {"color": "green", "watch_pid": 1234, "window_pid": 5678})
    fake_psutil = mock.Mock()
    fake_psutil.pid_exists = lambda pid: pid == 5678
    monkeypatch.setattr(cli, "_psutil", fake_psutil)
    assert _find_existing_light(1234) == "aa11"


def test_find_existing_light_returns_none_when_window_dead(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    write_state("bb22", {"color": "green", "watch_pid": 1234, "window_pid": 5678})
    fake_psutil = mock.Mock()
    fake_psutil.pid_exists = lambda pid: False  # window dead
    monkeypatch.setattr(cli, "_psutil", fake_psutil)
    assert _find_existing_light(1234) is None
    # Stale file should be cleaned up
    assert not state_path("bb22").exists()


def test_find_existing_light_ignores_other_claude_pids(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    write_state("cc33", {"color": "green", "watch_pid": 9999, "window_pid": 5678})
    fake_psutil = mock.Mock()
    fake_psutil.pid_exists = lambda pid: True
    monkeypatch.setattr(cli, "_psutil", fake_psutil)
    assert _find_existing_light(1234) is None
    # Other-pid light untouched
    assert state_path("cc33").exists()


def test_create_lock_serializes(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    fd1, p1 = _acquire_create_lock(timeout_s=1.0)
    assert fd1 is not None
    # Second acquire should time out while first is held
    fd2, p2 = _acquire_create_lock(timeout_s=0.5)
    assert fd2 is None
    _release_create_lock(fd1, p1)
    # Now acquirable again
    fd3, p3 = _acquire_create_lock(timeout_s=1.0)
    assert fd3 is not None
    _release_create_lock(fd3, p3)


def test_cmd_create_dedup_returns_existing_id(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    # Pre-existing state for claude_pid=1234
    write_state("dd44", {"color": "green", "watch_pid": 1234, "window_pid": 5678})
    fake_psutil = mock.Mock()
    fake_psutil.pid_exists = lambda pid: pid == 5678
    monkeypatch.setattr(cli, "_psutil", fake_psutil)
    monkeypatch.setattr(cli, "_find_claude_pid", lambda: 1234)
    # Popen should NOT be called when dedup hits
    with mock.patch("subprocess.Popen") as popen:
        cli.cmd_create()
        popen.assert_not_called()
    out = capsys.readouterr().out.strip()
    assert out == "dd44"
