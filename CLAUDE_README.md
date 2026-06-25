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

| Цвет | Когда ставить | Команда |
|------|---------------|---------|
| 🔴 Красный | Сразу как получил сообщение от юзера — агент думает | `python D:/TrafficLight/cli.py --manage $TRAFFIC_ID --set-color red` |
| 🟡 Жёлтый | Агент работает над задачей, может понадобиться спросить | `python D:/TrafficLight/cli.py --manage $TRAFFIC_ID --set-color yellow` |
| 🟢 Зелёный | Задача выполнена или нужен ввод пользователя | `python D:/TrafficLight/cli.py --manage $TRAFFIC_ID --set-color green` |

## Конец сессии

```bash
python D:/TrafficLight/cli.py --manage $TRAFFIC_ID --exit
```

## Заметки

- Закрытие окна = конец сессии, нужен новый `--create`
- Если `--manage` говорит "not found" — окно закрыто, запусти `--create` заново
- Окно всегда поверх всех окон, в правом верхнем углу
- Без pip-зависимостей
