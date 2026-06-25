import json
import os
import sys
import time
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
  cli.py --cleanup                       Kill orphan lights whose Claude is gone
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


def _find_existing_light(claude_pid: int) -> str | None:
    """Return the ID of a live light already watching this claude_pid, else None."""
    if _psutil is None:
        return None
    d = _state_dir()
    if not d.exists():
        return None
    for state_file in d.glob("*.json"):
        try:
            data = json.loads(state_file.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if data.get("watch_pid") != claude_pid:
            continue
        window_pid = data.get("window_pid")
        if window_pid and _psutil.pid_exists(window_pid):
            return state_file.stem
        # Stale entry — window died without cleanup. Remove so we recreate.
        try:
            state_file.unlink()
        except OSError:
            pass
    return None


def _acquire_create_lock(timeout_s: float = 10.0):
    """Atomic file lock so two concurrent --create calls don't both spawn a window."""
    d = _state_dir()
    d.mkdir(parents=True, exist_ok=True)
    lock_path = d / ".create.lock"
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            return fd, lock_path
        except FileExistsError:
            try:
                if time.time() - lock_path.stat().st_mtime > 30:
                    lock_path.unlink()
                    continue
            except OSError:
                pass
            if time.monotonic() > deadline:
                return None, lock_path
            time.sleep(0.05)


def _release_create_lock(fd, lock_path: Path) -> None:
    if fd is not None:
        try:
            os.close(fd)
        except OSError:
            pass
    try:
        lock_path.unlink()
    except OSError:
        pass


def cmd_cleanup() -> int:
    """Kill orphan window.py processes (Claude is gone) and prune stale state files.

    Returns the number of orphans killed.
    """
    if _psutil is None:
        return 0
    killed = 0
    for p in _psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            name = (p.info["name"] or "").lower()
            if name not in ("pythonw.exe", "pythonw", "python.exe", "python"):
                continue
            cmdline = p.info["cmdline"] or []
            if not any("window.py" in arg for arg in cmdline):
                continue
            watch_pid = None
            for i, arg in enumerate(cmdline):
                if arg == "--watch-pid" and i + 1 < len(cmdline):
                    try:
                        watch_pid = int(cmdline[i + 1])
                    except ValueError:
                        pass
                    break
            if watch_pid is None or _psutil.pid_exists(watch_pid):
                continue
            try:
                p.kill()
                killed += 1
            except (_psutil.NoSuchProcess, _psutil.AccessDenied):
                pass
        except (_psutil.NoSuchProcess, _psutil.AccessDenied):
            continue

    d = _state_dir()
    if d.exists():
        for state_file in d.glob("*.json"):
            try:
                data = json.loads(state_file.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            window_pid = data.get("window_pid")
            watch_pid  = data.get("watch_pid")
            stale = (window_pid and not _psutil.pid_exists(window_pid)) or \
                    (watch_pid  and not _psutil.pid_exists(watch_pid))
            if stale:
                try:
                    state_file.unlink()
                except OSError:
                    pass
    return killed


def cmd_create() -> None:
    lock_fd, lock_path = _acquire_create_lock()
    try:
        cmd_cleanup()

        claude_pid = _find_claude_pid()

        if claude_pid:
            existing = _find_existing_light(claude_pid)
            if existing:
                print(existing)
                return

        while True:
            id = secrets.token_hex(2)
            if not state_path(id).exists():
                break

        proj_dir = Path(__file__).parent
        window_path = proj_dir / "window.py"
        uv = proj_dir / ".venv" / "Scripts" / "pythonw.exe"
        if not uv.exists():
            uv = proj_dir / ".venv" / "bin" / "pythonw"
        if not uv.exists():
            uv = Path(sys.executable)

        cmd = [str(uv), str(window_path), id]
        if claude_pid:
            cmd += ["--watch-pid", str(claude_pid)]

        write_state(id, {
            "color": "green",
            "command": None,
            "watch_pid": claude_pid,
        })

        if sys.platform == "win32":
            proc = subprocess.Popen(
                cmd,
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                close_fds=True,
            )
        else:
            proc = subprocess.Popen(cmd, start_new_session=True)

        state = read_state(id) or {}
        state["window_pid"] = proc.pid
        write_state(id, state)

        print(id)
    finally:
        _release_create_lock(lock_fd, lock_path)


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "help":
        print(HELP_TEXT)
        return 0

    parser = argparse.ArgumentParser(prog="cli.py", add_help=True)
    subgroup = parser.add_mutually_exclusive_group(required=True)
    subgroup.add_argument("--create", action="store_true")
    subgroup.add_argument("--manage", metavar="ID")
    subgroup.add_argument("--cleanup", action="store_true")

    color_exit = parser.add_mutually_exclusive_group()
    color_exit.add_argument("--set-color", choices=["red", "yellow", "green"])
    color_exit.add_argument("--exit", action="store_true", dest="do_exit")

    args = parser.parse_args()

    if args.create:
        cmd_create()
        return 0

    if args.cleanup:
        n = cmd_cleanup()
        print(f"Killed {n} orphan light(s)")
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
