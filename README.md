# TrafficLight

Visual status indicator for [Claude Code](https://claude.ai/code). A small always-on-top window showing a traffic light that reflects what Claude is doing.

![preview](image.png)

## What it does

| Color | Meaning |
|-------|---------|
| 🔴 Red | Claude is working (received a prompt or using a tool) |
| 🟡 Yellow | Transitioning to green |
| 🟢 Green | Done / waiting for input |

Right-click the window for settings: opacity slider, red↔green inversion toggle, auto-focus (switches to the Claude terminal on green), session stats chart.

## Requirements

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)

## Install

```powershell
python install.py https://github.com/Yarodash/TrafficLight D:/TrafficLight
```

Or manually:

```powershell
git clone https://github.com/Yarodash/TrafficLight D:/TrafficLight
cd D:/TrafficLight
uv sync
```

## Claude Code integration

Add hooks to `~/.claude/settings.json` — see [`CLAUDE_README.md`](CLAUDE_README.md) for the full config.

With hooks in place the light starts automatically on session open, turns red on every prompt/tool call, and green when Claude stops.
