# TrafficLight — инструкция для Claude Code

Визуальный индикатор статуса. Запускай при старте сессии.

## Глобальные хуки

Добавь в `~/.claude/settings.json` в секцию `"hooks"`:

```json
"SessionStart": [
  {
    "hooks": [
      {
        "type": "command",
        "shell": "powershell",
        "command": "$j = [Console]::In.ReadToEnd() | ConvertFrom-Json; $sid = $j.session_id -replace '[^A-Za-z0-9-]', ''; $f = \"$env:USERPROFILE\\.claude\\traffic_$sid.txt\"; $mutex = [System.Threading.Mutex]::new($false, \"TrafficLight_$sid\"); try {   try { $mutex.WaitOne(5000) | Out-Null } catch {};   $skip = $false;   if (Test-Path $f) {     try { $old = [IO.File]::ReadAllText($f).Trim() } catch { $old = \"\" };     if ($old -and (Test-Path \"$env:USERPROFILE\\.trafficlight\\$old.json\")) { $skip = $true }   };   if (-not $skip) {     $id = python \"D:/TrafficLight/cli.py\" --create;     for ($i=0; $i -lt 20; $i++) { try { [IO.File]::WriteAllText($f, $id); break } catch { Start-Sleep -Milliseconds 50 } }   } } finally {   try { $mutex.ReleaseMutex() } catch {};   $mutex.Dispose() }",
        "statusMessage": "Starting TrafficLight..."
      }
    ]
  }
],
"UserPromptSubmit": [
  {
    "hooks": [
      {
        "type": "command",
        "shell": "powershell",
        "command": "$j = [Console]::In.ReadToEnd() | ConvertFrom-Json; $sid = $j.session_id -replace '[^A-Za-z0-9-]', ''; $f = \"$env:USERPROFILE\\.claude\\traffic_$sid.txt\"; if (Test-Path $f) { try { $id = [IO.File]::ReadAllText($f).Trim() } catch { $id = \"\" }; if ($id) { python \"D:/TrafficLight/cli.py\" --manage $id --set-color red } }",
        "async": true
      }
    ]
  }
],
"PreToolUse": [
  {
    "hooks": [
      {
        "type": "command",
        "shell": "powershell",
        "command": "$j = [Console]::In.ReadToEnd() | ConvertFrom-Json; $sid = $j.session_id -replace '[^A-Za-z0-9-]', ''; $f = \"$env:USERPROFILE\\.claude\\traffic_$sid.txt\"; if (Test-Path $f) { try { $id = [IO.File]::ReadAllText($f).Trim() } catch { $id = \"\" }; if ($id) { python \"D:/TrafficLight/cli.py\" --manage $id --set-color red } }",
        "async": true
      }
    ]
  }
],
"PostToolUse": [
  {
    "hooks": [
      {
        "type": "command",
        "shell": "powershell",
        "command": "$j = [Console]::In.ReadToEnd() | ConvertFrom-Json; $sid = $j.session_id -replace '[^A-Za-z0-9-]', ''; $f = \"$env:USERPROFILE\\.claude\\traffic_$sid.txt\"; if (Test-Path $f) { try { $id = [IO.File]::ReadAllText($f).Trim() } catch { $id = \"\" }; if ($id) { python \"D:/TrafficLight/cli.py\" --manage $id --set-color red } }",
        "async": true
      }
    ]
  }
],
"Stop": [
  {
    "hooks": [
      {
        "type": "command",
        "shell": "powershell",
        "command": "$j = [Console]::In.ReadToEnd() | ConvertFrom-Json; $sid = $j.session_id -replace '[^A-Za-z0-9-]', ''; $f = \"$env:USERPROFILE\\.claude\\traffic_$sid.txt\"; if (Test-Path $f) { try { $id = [IO.File]::ReadAllText($f).Trim() } catch { $id = \"\" }; if ($id) { python \"D:/TrafficLight/cli.py\" --manage $id --set-color yellow; Start-Sleep 1; python \"D:/TrafficLight/cli.py\" --manage $id --set-color green } }",
        "async": true
      }
    ]
  }
],
"Notification": [
  {
    "hooks": [
      {
        "type": "command",
        "shell": "powershell",
        "command": "$j = [Console]::In.ReadToEnd() | ConvertFrom-Json; $sid = $j.session_id -replace '[^A-Za-z0-9-]', ''; $f = \"$env:USERPROFILE\\.claude\\traffic_$sid.txt\"; if (Test-Path $f) { try { $id = [IO.File]::ReadAllText($f).Trim() } catch { $id = \"\" }; if ($id) { python \"D:/TrafficLight/cli.py\" --manage $id --set-color yellow; Start-Sleep 1; python \"D:/TrafficLight/cli.py\" --manage $id --set-color green } }",
        "async": true
      }
    ]
  }
]
```

> Замени `D:/TrafficLight/cli.py` на свой путь если установил в другое место.

ID светофора хранится в `~/.claude/traffic_<session_id>.txt`. Несколько сессий — несколько независимых светофоров.

## Цвета

| Цвет | Когда |
|------|-------|
| 🔴 Красный | Пользователь написал / инструмент работает |
| 🟡 Жёлтый | Переход к зелёному (анимация) |
| 🟢 Зелёный | Задача завершена / ожидание ввода |

## Окно (ПКМ → меню)

- **Прозрачность** — слайдер 20–100%
- **Инверсия** — красный↔зелёный (жёлтый не меняется)
- **Авто-фокус на зелёный** — при переходе на зелёный фокусирует терминал с Claude Code
- **График** — накопленное время красного/зелёного за сессию
- **Закрыть** — закрывает окно

Перетаскивание — ЛКМ.

## Установка

```powershell
python install.py https://github.com/Yarodash/TrafficLight D:/TrafficLight
```

Или вручную:

```powershell
git clone https://github.com/Yarodash/TrafficLight D:/TrafficLight
cd D:/TrafficLight
uv sync
```

Требуется [uv](https://docs.astral.sh/uv/).

## Заметки

- Закрытие окна = конец сессии (хук SessionStart создаст новый при следующем открытии)
- Окно всегда поверх всех, в правом верхнем углу
- Запускается через `.venv/Scripts/pythonw.exe` (без консоли)
