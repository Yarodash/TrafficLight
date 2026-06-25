# TrafficLight — инструкция для Claude Code

Визуальный индикатор статуса. Запускай при старте сессии.

## Старт сессии

**Bash:**
```bash
TRAFFIC_ID=$(python D:/TrafficLight/cli.py --create)
```

**PowerShell:**
```powershell
$env:TRAFFIC_ID = python D:/TrafficLight/cli.py --create
```

## Цвета

| Цвет | Когда ставить |
|------|---------------|
| 🔴 Красный | Сразу как пользователь что-то написал / дал задачу — первое действие в ответе |
| 🟡 Жёлтый | Всегда перед зелёным — анимация перехода |
| 🟢 Зелёный | Работа завершена ИЛИ нужен ввод пользователя |

### Паттерны использования

**Получил сообщение:**
```bash
python D:/TrafficLight/cli.py --manage $TRAFFIC_ID --set-color red
```

**Завершил задачу / жду ввода (всегда через жёлтый):**
```bash
python D:/TrafficLight/cli.py --manage $TRAFFIC_ID --set-color yellow && sleep 2 && python D:/TrafficLight/cli.py --manage $TRAFFIC_ID --set-color green
```

## Конец сессии

```bash
python D:/TrafficLight/cli.py --manage $TRAFFIC_ID --exit
```

## Заметки

- Закрытие окна = конец сессии, нужен новый `--create`
- Если `--manage` говорит "not found" — окно закрыто, запусти `--create` заново
- Окно всегда поверх всех окон, в правом верхнем углу
- Без pip-зависимостей
