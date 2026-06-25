# TrafficLight CLI — Design Spec
Date: 2026-06-25

## Overview

A Python CLI tool that creates and manages traffic light windows for use with Claude Code. The traffic light provides a visual status indicator: red = agent is thinking hard, yellow = agent is working (may ask a question), green = user action needed or task complete.

## Architecture

Two files + a state directory:

- **`cli.py`** — CLI entry point, handles all commands
- **`window.py`** — tkinter window, runs as a separate subprocess
- **`~/.trafficlight/<id>.json`** — state file per active session

State file schema:
```json
{"color": "green", "command": null}
```

`command` can be `null` or `"exit"`.

## Commands

### `cli.py --create`
- Generates a short 4-character hex ID using `secrets.token_hex(2)` (e.g. `a1b2`)
- If `~/.trafficlight/<id>.json` already exists (collision), retry until a free ID is found
- Creates `~/.trafficlight/` directory if it doesn't exist
- Creates `~/.trafficlight/<id>.json` with `{"color": "green", "command": null}` via atomic write — temp file in `~/.trafficlight/` (same directory), then `os.replace`
- Resolves `window.py` path as `Path(__file__).parent / "window.py"` (absolute, relative to `cli.py` location) to work regardless of current working directory
- Launches `window.py` as detached subprocess using `sys.executable` (the current Python interpreter):
  - On Windows: `subprocess.Popen([sys.executable, str(window_path), id], creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP, close_fds=True)`
  - On other platforms: `subprocess.Popen([sys.executable, str(window_path), id], start_new_session=True)`
- Prints only the ID to stdout (e.g. `a1b2`)
- Exit code 0

### `cli.py --manage <id> --set-color red|yellow|green`
- `--manage` requires exactly one of `--set-color` or `--exit` (mutually exclusive, enforced by argparse)
- If `--manage` is given without `--set-color` or `--exit`: argparse prints usage error, exit code 2
- Validates that `~/.trafficlight/<id>.json` exists
- If not found: prints error + help hint, exits with code 1
- If found: updates `color` field via atomic write — temp file created in `~/.trafficlight/` (same directory as target, using `tempfile.NamedTemporaryFile(dir=state_dir, delete=False)`) then `os.replace` to prevent cross-device errors and concurrent corruption
- Exit code 0

### `cli.py --manage <id> --exit`
- Validates that `~/.trafficlight/<id>.json` exists
- If not found: prints error + help hint, exits with code 1
- If found: writes `{"color": <current_color>, "command": "exit"}` via atomic write (temp file in `~/.trafficlight/`, then `os.replace`)
- This is fire-and-forget: `cli.py` exits immediately without waiting for the window to close
- The window detects `"command": "exit"` on its next poll (within 100ms) and exits
- If the window process has crashed without deleting the state file, `--exit` will succeed (exit 0) and write to the file, but no window will respond. The stale file will remain. This is acceptable — the next `--create` will generate a different ID.
- Exit code 0

### `cli.py help`
- Positional `help` argument (not `--help`), as specified by the user
- Prints full usage instructions including all commands and color meanings
- Does not conflict with argparse's built-in `-h`: argparse is configured with `add_help=True` so `-h`/`--help` still works; `help` is handled as a special case before argparse parsing
- Exit code 0

## Error Handling

When `--manage` is called with an unknown or closed ID:
```
Error: Traffic light 'a1b2' not found or already closed.
To create a new traffic light: cli.py --create
```

## Window (`window.py`)

- **Library**: tkinter (stdlib, no extra dependencies)
- **Invocation**: `python window.py <id>` via `sys.executable` from `cli.py`
- **Size**: ~100×200px
- **Style**: compact — dark background (`#1a1a2e`), three circles vertically stacked
- **Active light visual**: filled with the color, surrounded by two concentric slightly larger circles at decreasing opacity to simulate a glow (pure tkinter, no external libs)
- **Colors**:
  - Active red: `#e53935`
  - Active yellow: `#f5c518`
  - Active green: `#28c93f`
  - Inactive: `#2d2d2d`
- **Position**: top-right corner — calculated as `screen_width - window_width - 10` for x, `10` for y
- **Always-on-top**: `root.wm_attributes('-topmost', True)`
- **Polling**: reads state JSON every 100ms via `root.after(100, poll)`
- **On window close (X button)**: deletes `~/.trafficlight/<id>.json`, calls `root.destroy()`
- **On `"command": "exit"` detected in poll**: deletes state file, calls `root.destroy()`
- If tkinter is unavailable (e.g. minimal Python install without tk): `window.py` prints an error to stderr and exits with code 1. `cli.py --create` will succeed (prints ID) but the window won't appear — the state file will exist.

## CLAUDE_README.md

Purpose: instructions for Claude Code on how to use the traffic light as a visual session indicator.

Content:
1. **Setup**: run `cli.py --create` at the start of a session, save the returned ID
2. **Color protocol**:
   - Set **red** immediately when a user message is received: `cli.py --manage <id> --set-color red`
   - Set **yellow** when starting a task that might need user input: `cli.py --manage <id> --set-color yellow`
   - Set **green** when ready for user input or task is fully complete: `cli.py --manage <id> --set-color green`
3. **Session end**: run `cli.py --manage <id> --exit` when the session ends
4. **Window behavior**: closing the window ends the session; a new `--create` is needed after that

## File Structure

```
D:/TrafficLight/
├── cli.py
├── window.py
└── CLAUDE_README.md
```

State (outside project, in user home):
```
~/.trafficlight/
├── a1b2.json
└── c3d4.json
```

## Dependencies

- Python 3.x (stdlib only: `tkinter`, `json`, `os`, `sys`, `subprocess`, `pathlib`, `secrets`, `tempfile`)
- No pip packages required
