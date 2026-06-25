#!/usr/bin/env python3
"""
TrafficLight installer.

Usage:
    python install.py https://github.com/Yarodash/TrafficLight D:/path/to/folder
    python install.py D:/path/to/folder          # if already cloned here
"""
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_URL = "https://github.com/Yarodash/TrafficLight"


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    print(f"  > {' '.join(cmd)}")
    return subprocess.run(cmd, check=True, **kw)


def main() -> None:
    args = sys.argv[1:]

    # resolve install_dir (and optional repo URL override)
    if not args:
        print(__doc__)
        sys.exit(1)

    if args[0].startswith("http"):
        repo_url   = args[0]
        install_dir = Path(args[1]) if len(args) > 1 else Path.cwd() / "TrafficLight"
    else:
        repo_url   = REPO_URL
        install_dir = Path(args[0])

    install_dir = install_dir.resolve()

    # ── 1. clone or verify ────────────────────────────────────────────────────
    if install_dir.exists():
        if (install_dir / "cli.py").exists():
            print(f"[1/3] Using existing repo at {install_dir}")
        else:
            print(f"Error: {install_dir} exists but doesn't look like TrafficLight.", file=sys.stderr)
            sys.exit(1)
    else:
        print(f"[1/3] Cloning {repo_url} → {install_dir}")
        run(["git", "clone", repo_url, str(install_dir)])

    # ── 2. install dependencies ───────────────────────────────────────────────
    print("[2/3] Installing dependencies with uv…")
    try:
        run(["uv", "sync"], cwd=install_dir)
    except subprocess.CalledProcessError:
        print("  Warning: uv sync failed (maybe .venv is locked). Run manually: uv sync")

    # ── 3. register global hooks ──────────────────────────────────────────────
    print("[3/3] Registering global Claude Code hooks…")

    settings_path = Path.home() / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    settings: dict = {}
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    cli = str(install_dir / "cli.py").replace("\\", "/")

    def _hook(cmd: str) -> dict:
        return {"type": "command", "shell": "powershell", "command": cmd}

    def _async_hook(cmd: str) -> dict:
        return {"type": "command", "shell": "powershell", "command": cmd, "async": True}

    sid_file   = '"$env:USERPROFILE\\.claude\\traffic_$sid.txt"'
    sid_prefix = f'$j = [Console]::In.ReadToEnd() | ConvertFrom-Json; $sid = $j.session_id -replace \'[^A-Za-z0-9-]\', \'\'; $f = {sid_file};'

    # File I/O via .NET to avoid PowerShell's lazy handle release (Get-Content) and
    # exclusive-write default (Out-File) that race against concurrent hooks.
    read_id  = 'try { $id = [IO.File]::ReadAllText($f).Trim() } catch { $id = "" }'
    write_id = 'for ($i=0; $i -lt 20; $i++) { try { [IO.File]::WriteAllText($f, $id); break } catch { Start-Sleep -Milliseconds 50 } }'

    # SessionStart can fire multiple times per Claude session (startup + resume/clear),
    # potentially concurrently. Serialize with a named mutex, and skip create if a
    # live light already exists (state file ~/.trafficlight/<id>.json exists until
    # the window deletes it on close).
    session_start_cmd = (
        f'{sid_prefix}'
        f' $mutex = [System.Threading.Mutex]::new($false, "TrafficLight_$sid");'
        f' try {{'
        f'   try {{ $mutex.WaitOne(5000) | Out-Null }} catch {{}};'
        f'   $skip = $false;'
        f'   if (Test-Path $f) {{'
        f'     try {{ $old = [IO.File]::ReadAllText($f).Trim() }} catch {{ $old = "" }};'
        f'     if ($old -and (Test-Path "$env:USERPROFILE\\.trafficlight\\$old.json")) {{ $skip = $true }}'
        f'   }};'
        f'   if (-not $skip) {{'
        f'     $id = python "{cli}" --create;'
        f'     {write_id}'
        f'   }}'
        f' }} finally {{'
        f'   try {{ $mutex.ReleaseMutex() }} catch {{}};'
        f'   $mutex.Dispose()'
        f' }}'
    )

    def _group(hook_dict: dict) -> dict:
        return {"hooks": [hook_dict]}

    new_hooks: dict[str, list] = {
        "SessionStart": [_group(
            _hook(session_start_cmd) | {"statusMessage": "Starting TrafficLight..."}
        )],
        "UserPromptSubmit": [_group(
            _async_hook(f'{sid_prefix} if (Test-Path $f) {{ {read_id}; if ($id) {{ python "{cli}" --manage $id --set-color red }} }}')
        )],
        "PreToolUse": [_group(
            _async_hook(f'{sid_prefix} if (Test-Path $f) {{ {read_id}; if ($id) {{ python "{cli}" --manage $id --set-color red }} }}')
        )],
        "PostToolUse": [_group(
            _async_hook(f'{sid_prefix} if (Test-Path $f) {{ {read_id}; if ($id) {{ python "{cli}" --manage $id --set-color red }} }}')
        )],
        "Stop": [_group(
            _async_hook(f'{sid_prefix} if (Test-Path $f) {{ {read_id}; if ($id) {{ python "{cli}" --manage $id --set-color yellow; Start-Sleep 1; python "{cli}" --manage $id --set-color green }} }}')
        )],
        "Notification": [_group(
            _async_hook(f'{sid_prefix} if (Test-Path $f) {{ {read_id}; if ($id) {{ python "{cli}" --manage $id --set-color yellow; Start-Sleep 1; python "{cli}" --manage $id --set-color green }} }}')
        )],
    }

    def _is_ours(group) -> bool:
        if isinstance(group, dict):
            entries = group.get("hooks") or []
        elif isinstance(group, list):
            entries = group
        else:
            return False
        return any(isinstance(h, dict) and cli in h.get("command", "") for h in entries)

    hooks = settings.setdefault("hooks", {})
    for event, new_groups in new_hooks.items():
        existing = hooks.get(event, [])
        cleaned = [g for g in existing if not _is_ours(g)]
        hooks[event] = cleaned + new_groups

    settings_path.write_text(
        json.dumps(settings, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print()
    print("Done!")
    print(f"  Repo:     {install_dir}")
    print(f"  Settings: {settings_path}")
    print()
    print("Restart Claude Code to activate the hooks.")


if __name__ == "__main__":
    main()
