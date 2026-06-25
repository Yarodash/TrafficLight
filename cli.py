import json
import os
import sys
import tempfile
import subprocess
import secrets
import argparse
from pathlib import Path

try:
    import psutil as _psutil
except ImportError:
    _psutil = None


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


def _find_claude_pid() -> int | None:
    """Walk the process tree upward looking for a Claude Code process."""
    if _psutil is None:
        return None
    try:
        proc = _psutil.Process(os.getpid())
        for _ in range(12):
            proc = proc.parent()
            if proc is None or proc.pid <= 4:
                break
            if "claude" in proc.name().lower():
                return proc.pid
    except (_psutil.NoSuchProcess, _psutil.AccessDenied, OSError):
        pass
    # Fallback: scan all processes
    try:
        for p in _psutil.process_iter(["pid", "name"]):
            name = (p.info["name"] or "").lower()
            if "claude" in name and p.pid != os.getpid():
                return p.pid
    except Exception:
        pass
    return None


def cmd_create() -> None:
    while True:
        id = secrets.token_hex(2)
        if not state_path(id).exists():
            break
    write_state(id, {"color": "green", "command": None})
    proj_dir = Path(__file__).parent
    window_path = proj_dir / "window.py"
    uv = proj_dir / ".venv" / "Scripts" / "pythonw.exe"
    if not uv.exists():
        uv = proj_dir / ".venv" / "bin" / "pythonw"
    if not uv.exists():
        uv = Path(sys.executable)

    cmd = [str(uv), str(window_path), id]
    claude_pid = _find_claude_pid()
    if claude_pid:
        cmd += ["--watch-pid", str(claude_pid)]

    if sys.platform == "win32":
        subprocess.Popen(
            cmd,
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
            close_fds=True,
        )
    else:
        subprocess.Popen(cmd, start_new_session=True)
    print(id)


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "help":
        print(HELP_TEXT)
        return 0

    parser = argparse.ArgumentParser(prog="cli.py", add_help=True)
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

        if args.do_exit:
            state["command"] = "exit"
            write_state(id, state)
            return 0

        parser.error("--manage requires --set-color or --exit")

    return 0


if __name__ == "__main__":
    sys.exit(main())
