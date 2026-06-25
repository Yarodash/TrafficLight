import json
import os
import sys
import tempfile
import subprocess
import secrets
import argparse
from pathlib import Path


def _state_dir() -> Path:
    return Path.home() / ".trafficlight"


def state_path(id: str) -> Path:
    return _state_dir() / f"{id}.json"


def read_state(id: str) -> dict | None:
    p = state_path(id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def write_state(id: str, state: dict) -> None:
    d = _state_dir()
    d.mkdir(parents=True, exist_ok=True)
    target = d / f"{id}.json"
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(state, f)
        os.replace(tmp, target)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
