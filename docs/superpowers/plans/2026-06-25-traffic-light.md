# TrafficLight CLI Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers-extended-cc:subagent-driven-development (if subagents available) or superpowers-extended-cc:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python CLI (`cli.py`) that creates and manages traffic light windows (`window.py`) as visual status indicators for Claude Code sessions.

**Architecture:** `cli.py` handles all commands and spawns `window.py` as a detached subprocess. State is shared via `~/.trafficlight/<id>.json` files with atomic writes. The window polls its state file every 100ms and updates display accordingly.

**Tech Stack:** Python 3 stdlib only — `tkinter`, `argparse`, `subprocess`, `pathlib`, `secrets`, `tempfile`, `json`

---

## File Map

| File | Responsibility |
|---|---|
| `cli.py` | CLI entry point: --create, --manage, help |
| `window.py` | tkinter window: display, polling, glow effect |
| `CLAUDE_README.md` | Instructions for Claude Code |
| `tests/test_cli.py` | CLI command tests (subprocess-based) |

---

### Task 1: State file utilities

**Files:**
- Create: `cli.py` (foundation only — state helpers)
- Create: `tests/test_cli.py`

- [ ] **Step 1: Write failing tests for state utilities**

Create `tests/test_cli.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd D:/TrafficLight && python -m pytest tests/test_cli.py -v
```

Expected: `ModuleNotFoundError` or `ImportError` (cli.py doesn't exist yet)

- [ ] **Step 3: Implement state utilities in cli.py**

Create `cli.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```
cd D:/TrafficLight && python -m pytest tests/test_cli.py -v
```

Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add cli.py tests/test_cli.py
git commit -m "feat: add state file utilities with atomic writes"
```

---

### Task 2: `cli.py --create`

**Files:**
- Modify: `cli.py` — add `cmd_create()` and `main()` stub (no help handler yet)
- Modify: `tests/test_cli.py` — add create tests

- [ ] **Step 1: Write failing tests for --create**

Add to `tests/test_cli.py`:

```python
import subprocess as _subprocess

PROJECT_ROOT = str(Path(__file__).parent.parent)

def _home_env(tmp_path):
    return {**os.environ, "HOME": str(tmp_path), "USERPROFILE": str(tmp_path)}

def run_cli(*args, env=None):
    result = _subprocess.run(
        [sys.executable, "cli.py", *args],
        capture_output=True, text=True, cwd=PROJECT_ROOT, env=env
    )
    return result

def test_create_prints_id(tmp_path):
    result = run_cli("--create", env=_home_env(tmp_path))
    assert result.returncode == 0
    id = result.stdout.strip()
    assert len(id) == 4
    assert all(c in "0123456789abcdef" for c in id)

def test_create_creates_state_file(tmp_path):
    result = run_cli("--create", env=_home_env(tmp_path))
    id = result.stdout.strip()
    state_file = tmp_path / ".trafficlight" / f"{id}.json"
    assert state_file.exists()
    state = json.loads(state_file.read_text())
    assert state == {"color": "green", "command": None}

def test_create_id_collision_retry(tmp_path):
    """Two creates both succeed."""
    r1 = run_cli("--create", env=_home_env(tmp_path))
    r2 = run_cli("--create", env=_home_env(tmp_path))
    assert r1.returncode == 0
    assert r2.returncode == 0
    assert len(r1.stdout.strip()) == 4
    assert len(r2.stdout.strip()) == 4
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd D:/TrafficLight && python -m pytest tests/test_cli.py::test_create_prints_id -v
```

Expected: FAIL — `main` not defined

- [ ] **Step 3: Implement --create in cli.py**

Add after the state utilities (no HELP_TEXT yet — that comes in Task 5):

```python
def cmd_create() -> None:
    while True:
        id = secrets.token_hex(2)
        if not state_path(id).exists():
            break
    write_state(id, {"color": "green", "command": None})
    window_path = Path(__file__).parent / "window.py"
    if sys.platform == "win32":
        subprocess.Popen(
            [sys.executable, str(window_path), id],
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
            close_fds=True,
        )
    else:
        subprocess.Popen(
            [sys.executable, str(window_path), id],
            start_new_session=True,
        )
    print(id)


def main() -> int:
    # 'help' positional handled in Task 5
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="Traffic light status indicator for Claude Code",
        add_help=True,
    )
    subgroup = parser.add_mutually_exclusive_group(required=True)
    subgroup.add_argument("--create", action="store_true")
    subgroup.add_argument("--manage", metavar="ID")

    color_exit = parser.add_mutually_exclusive_group()
    color_exit.add_argument("--set-color", choices=["red", "yellow", "green"])
    color_exit.add_argument("--exit", action="store_true", dest="do_exit")

    args = parser.parse_args()

    if args.create:
        cmd_create()
        return 0

    # --manage branch added in Task 3 & 4
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

```
cd D:/TrafficLight && python -m pytest tests/test_cli.py::test_create_prints_id tests/test_cli.py::test_create_creates_state_file tests/test_cli.py::test_create_id_collision_retry -v
```

Expected: 3 PASSED (window.py missing is OK — detached launch fails silently)

- [ ] **Step 5: Commit**

```bash
git add cli.py tests/test_cli.py
git commit -m "feat: implement --create command"
```

---

### Task 3: `cli.py --manage --set-color`

**Files:**
- Modify: `cli.py` — wire `--manage` with `--set-color` only (not `--exit` yet)
- Modify: `tests/test_cli.py` — add set-color tests

- [ ] **Step 1: Write failing tests**

Add to `tests/test_cli.py`:

```python
def test_set_color_updates_state(tmp_path):
    r = run_cli("--create", env=_home_env(tmp_path))
    id = r.stdout.strip()
    result = run_cli("--manage", id, "--set-color", "red", env=_home_env(tmp_path))
    assert result.returncode == 0
    state = json.loads((tmp_path / ".trafficlight" / f"{id}.json").read_text())
    assert state["color"] == "red"

def test_set_color_preserves_command(tmp_path):
    r = run_cli("--create", env=_home_env(tmp_path))
    id = r.stdout.strip()
    run_cli("--manage", id, "--set-color", "yellow", env=_home_env(tmp_path))
    state = json.loads((tmp_path / ".trafficlight" / f"{id}.json").read_text())
    assert state["command"] is None

def test_set_color_unknown_id(tmp_path):
    result = run_cli("--manage", "0000", "--set-color", "green", env=_home_env(tmp_path))
    assert result.returncode == 1
    assert "not found" in result.stdout or "not found" in result.stderr
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd D:/TrafficLight && python -m pytest tests/test_cli.py::test_set_color_updates_state -v
```

Expected: FAIL — --manage branch returns 0 without doing anything

- [ ] **Step 3: Implement --manage --set-color only in cli.py**

Replace the `# --manage branch added in Task 3 & 4` comment in `main()`:

```python
    if args.manage:
        id = args.manage
        state = read_state(id)
        if state is None:
            print(f"Error: Traffic light '{id}' not found or already closed.", file=sys.stderr)
            print("To create a new traffic light: cli.py --create", file=sys.stderr)
            return 1

        if args.set_color:
            state["color"] = args.set_color
            write_state(id, state)
            return 0

        # --exit wired in Task 4
        parser.error("--manage requires --set-color or --exit")
```

- [ ] **Step 4: Run tests to verify they pass**

```
cd D:/TrafficLight && python -m pytest tests/test_cli.py -v -k "set_color"
```

Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add cli.py tests/test_cli.py
git commit -m "feat: implement --manage --set-color command"
```

---

### Task 4: `cli.py --manage --exit`

**Files:**
- Modify: `cli.py` — wire `--exit` branch
- Modify: `tests/test_cli.py` — add exit tests

- [ ] **Step 1: Write failing tests**

Add to `tests/test_cli.py`:

```python
def test_exit_writes_command(tmp_path):
    r = run_cli("--create", env=_home_env(tmp_path))
    id = r.stdout.strip()
    result = run_cli("--manage", id, "--exit", env=_home_env(tmp_path))
    assert result.returncode == 0
    state = json.loads((tmp_path / ".trafficlight" / f"{id}.json").read_text())
    assert state["command"] == "exit"

def test_exit_preserves_color(tmp_path):
    r = run_cli("--create", env=_home_env(tmp_path))
    id = r.stdout.strip()
    run_cli("--manage", id, "--set-color", "yellow", env=_home_env(tmp_path))
    run_cli("--manage", id, "--exit", env=_home_env(tmp_path))
    state = json.loads((tmp_path / ".trafficlight" / f"{id}.json").read_text())
    assert state["color"] == "yellow"
    assert state["command"] == "exit"

def test_exit_unknown_id(tmp_path):
    result = run_cli("--manage", "0000", "--exit", env=_home_env(tmp_path))
    assert result.returncode == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd D:/TrafficLight && python -m pytest tests/test_cli.py -v -k "exit"
```

Expected: FAIL — `--exit` hits `parser.error(...)` which exits with code 2, not 0

- [ ] **Step 3: Wire --exit branch in cli.py**

Replace `# --exit wired in Task 4` in `main()`:

```python
        if args.do_exit:
            state["command"] = "exit"
            write_state(id, state)
            return 0
```

- [ ] **Step 4: Run tests to verify they pass**

```
cd D:/TrafficLight && python -m pytest tests/test_cli.py -v -k "exit"
```

Expected: 3 PASSED

- [ ] **Step 5: Run full test suite**

```
cd D:/TrafficLight && python -m pytest tests/test_cli.py -v
```

Expected: all PASSED

- [ ] **Step 6: Commit**

```bash
git add cli.py tests/test_cli.py
git commit -m "feat: implement --manage --exit command"
```

---

### Task 5: `cli.py help`

**Files:**
- Modify: `cli.py` — add HELP_TEXT and `help` positional handler
- Modify: `tests/test_cli.py` — add help tests

- [ ] **Step 1: Write failing tests**

Add to `tests/test_cli.py`:

```python
def test_help_exits_zero():
    result = run_cli("help")
    assert result.returncode == 0

def test_help_shows_commands():
    result = run_cli("help")
    assert "--create" in result.stdout
    assert "--set-color" in result.stdout
    assert "--exit" in result.stdout

def test_help_shows_color_meanings():
    result = run_cli("help")
    assert "red" in result.stdout
    assert "yellow" in result.stdout
    assert "green" in result.stdout
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd D:/TrafficLight && python -m pytest tests/test_cli.py -v -k "help"
```

Expected: FAIL — `help` positional is passed to argparse which exits with code 2 (unrecognized argument)

- [ ] **Step 3: Add HELP_TEXT and help handler to cli.py**

Add `HELP_TEXT` constant before `main()`:

```python
HELP_TEXT = """\
TrafficLight CLI — visual status indicator for Claude Code

Commands:
  cli.py --create                        Create new traffic light, print its ID
  cli.py --manage <id> --set-color red|yellow|green
                                         Change light color
  cli.py --manage <id> --exit            Close the traffic light window
  cli.py help                            Show this help

Colors:
  red     Agent is thinking hard — user should wait
  yellow  Agent is working — may need to ask something
  green   Ready for user input, or task complete
"""
```

Add at the very top of `main()`, before the parser:

```python
    if len(sys.argv) > 1 and sys.argv[1] == "help":
        print(HELP_TEXT)
        return 0
```

- [ ] **Step 4: Run tests to verify they pass**

```
cd D:/TrafficLight && python -m pytest tests/test_cli.py -v -k "help"
```

Expected: 3 PASSED

- [ ] **Step 5: Run full test suite**

```
cd D:/TrafficLight && python -m pytest tests/test_cli.py -v
```

Expected: all PASSED

- [ ] **Step 6: Commit**

```bash
git add cli.py tests/test_cli.py
git commit -m "feat: add help command"
```

---

### Task 6: `window.py`

**Files:**
- Create: `window.py`

No unit tests — tkinter requires a display. Tested manually.

**Note:** tkinter's `stipple` parameter (used for the glow rings) is an X11 bitmap feature. On Windows it is silently ignored — the glow will not render, but the active light will still be visually distinct from inactive ones via color. This is a tkinter platform limitation, not a bug.

- [ ] **Step 1: Create window.py**

```python
import json
import sys
import tkinter as tk
from pathlib import Path


def state_path(id: str) -> Path:
    return Path.home() / ".trafficlight" / f"{id}.json"


COLORS = {
    "red":    "#e53935",
    "yellow": "#f5c518",
    "green":  "#28c93f",
}
INACTIVE = "#2d2d2d"
BG = "#1a1a2e"
RADIUS = 20
GAP = 14
PADDING = 30  # 30*2 + 20*2 = 100px wide — matches spec ~100px
CANVAS_W = RADIUS * 2 + PADDING * 2
CANVAS_H = RADIUS * 6 + GAP * 2 + PADDING * 2


def draw_light(canvas: tk.Canvas, cx: int, cy: int, color: str) -> None:
    if color != INACTIVE:
        # glow rings (visible on Linux/macOS; stipple silently ignored on Windows)
        canvas.create_oval(
            cx - RADIUS - 6, cy - RADIUS - 6,
            cx + RADIUS + 6, cy + RADIUS + 6,
            fill=color, outline="", stipple="gray25",
        )
        canvas.create_oval(
            cx - RADIUS - 3, cy - RADIUS - 3,
            cx + RADIUS + 3, cy + RADIUS + 3,
            fill=color, outline="", stipple="gray50",
        )
    canvas.create_oval(
        cx - RADIUS, cy - RADIUS,
        cx + RADIUS, cy + RADIUS,
        fill=color, outline="#111111", width=2,
    )


class TrafficLight:
    def __init__(self, root: tk.Tk, id: str) -> None:
        self.root = root
        self.id = id
        self.current_color = "green"

        root.title(f"🚦 {id}")
        root.configure(bg=BG)
        root.resizable(False, False)
        root.wm_attributes("-topmost", True)

        self.canvas = tk.Canvas(
            root, width=CANVAS_W, height=CANVAS_H,
            bg=BG, highlightthickness=0,
        )
        self.canvas.pack()

        root.update_idletasks()
        sw = root.winfo_screenwidth()
        root.geometry(f"{CANVAS_W}x{CANVAS_H}+{sw - CANVAS_W - 10}+10")

        root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._render("green")
        self._poll()

    def _render(self, color: str) -> None:
        self.canvas.delete("all")
        cx = CANVAS_W // 2
        for i, name in enumerate(["red", "yellow", "green"]):
            cy = PADDING + RADIUS + i * (RADIUS * 2 + GAP)
            active = COLORS[name] if color == name else INACTIVE
            draw_light(self.canvas, cx, cy, active)
        self.current_color = color

    def _poll(self) -> None:
        try:
            p = state_path(self.id)
            if p.exists():
                data = json.loads(p.read_text())
                if data.get("command") == "exit":
                    self._cleanup()
                    return
                color = data.get("color", self.current_color)
                if color != self.current_color:
                    self._render(color)
        except Exception:
            pass
        self.root.after(100, self._poll)

    def _cleanup(self) -> None:
        try:
            state_path(self.id).unlink(missing_ok=True)
        except OSError:
            pass
        self.root.destroy()

    def _on_close(self) -> None:
        self._cleanup()


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: window.py <id>", file=sys.stderr)
        sys.exit(1)

    id = sys.argv[1]

    try:
        root = tk.Tk()
    except tk.TclError as e:
        print(f"Error: tkinter unavailable — {e}", file=sys.stderr)
        sys.exit(1)

    TrafficLight(root, id)
    root.mainloop()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke test — run window manually**

```
cd D:/TrafficLight && python cli.py --create
```

Expected: prints a 4-char ID, window appears top-right corner, green light active (no glow on Windows — that's expected).

Test color changes (replace `<id>` with the printed ID):
```
python cli.py --manage <id> --set-color red
python cli.py --manage <id> --set-color yellow
python cli.py --manage <id> --set-color green
python cli.py --manage <id> --exit
```

Expected: window updates within 100ms on each command, then closes on `--exit`.

- [ ] **Step 3: Commit**

```bash
git add window.py
git commit -m "feat: implement tkinter traffic light window"
```

---

### Task 7: `CLAUDE_README.md`

**Files:**
- Create: `CLAUDE_README.md`

- [ ] **Step 1: Create CLAUDE_README.md**

```markdown
# TrafficLight — Claude Code Integration Guide

This tool provides a persistent visual status indicator to show the user what Claude Code is doing.

## Setup

At the start of each session, create a traffic light and save the ID.

**Bash / Git Bash:**
```bash
TRAFFIC_ID=$(python D:/TrafficLight/cli.py --create)
```

**PowerShell:**
```powershell
$env:TRAFFIC_ID = python D:/TrafficLight/cli.py --create
```

## Color Protocol

Set the color to match your current activity:

| Color | When to use | Command |
|-------|-------------|---------|
| 🔴 Red | Immediately when a user message is received — agent is reading and thinking hard | `python D:/TrafficLight/cli.py --manage $TRAFFIC_ID --set-color red` |
| 🟡 Yellow | Agent is actively working on a task — may need to ask the user something | `python D:/TrafficLight/cli.py --manage $TRAFFIC_ID --set-color yellow` |
| 🟢 Green | Task fully complete, or waiting for user input / decision | `python D:/TrafficLight/cli.py --manage $TRAFFIC_ID --set-color green` |

## Session End

When the session ends, close the window:

**Bash:**
```bash
python D:/TrafficLight/cli.py --manage $TRAFFIC_ID --exit
```

**PowerShell:**
```powershell
python D:/TrafficLight/cli.py --manage $env:TRAFFIC_ID --exit
```

## Notes

- Closing the window manually also ends the session — run `--create` again to get a new ID
- If `--manage` fails with "not found", the window was closed; run `--create` again
- The window is always-on-top and appears in the top-right corner of the screen
- No pip packages required — Python stdlib only
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE_README.md
git commit -m "docs: add CLAUDE_README.md with Claude Code integration guide"
```

---

### Task 8: Git init + final check

**Files:** none

- [ ] **Step 1: Initialize git if not already done**

```bash
cd D:/TrafficLight && git init && git add . && git commit -m "chore: initial project structure"
```

(Skip if already initialized)

- [ ] **Step 2: Run full test suite one last time**

```
cd D:/TrafficLight && python -m pytest tests/test_cli.py -v
```

Expected: all PASSED

- [ ] **Step 3: Test help command**

```
cd D:/TrafficLight && python cli.py help
```

Expected: full help text printed, exit code 0

- [ ] **Step 4: End-to-end smoke test**

```bash
id=$(python cli.py --create)
echo "Created: $id"
sleep 1 && python cli.py --manage $id --set-color red
sleep 1 && python cli.py --manage $id --set-color yellow
sleep 1 && python cli.py --manage $id --set-color green
sleep 1 && python cli.py --manage $id --exit
```

Expected: window opens green, cycles through red→yellow→green, then closes.

- [ ] **Step 5: Test error case**

```
cd D:/TrafficLight && python cli.py --manage 0000 --set-color red
```

Expected: exit code 1, error message mentioning "not found" with hint to run `--create`
