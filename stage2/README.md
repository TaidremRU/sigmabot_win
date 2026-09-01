# SigmaSteamBot — стадия 2

Автозапуск и удалённое управление игрой **Sigma World Online** на Windows-VM (QEMU/KVM,
`192.168.0.106`) через Telegram-бота `@mysigmaworld_bot`.

## Что делает

- **При входе в систему** (автологон пользователя `alex`) задача планировщика
  `SigmaSteamBot` запускает `supervisor.py`.
- `supervisor.py` держит один процесс с двумя потоками:
  - **watchdog** — следит, что Steam и игра запущены; поднимает упавшее,
    шлёт события в Telegram, каждые 30 c пишет снапшот в `state.json`;
  - **bot** — long-polling Telegram Bot API **через SOCKS5-прокси
    `192.168.0.222:2080`** (напрямую с VM `api.telegram.org` недоступен).
- Игра запускается через `steam://rungameid/1690980`.

## Файлы

| Файл | Назначение |
|---|---|
| `config.json` | токен, allowlist, прокси, пути, параметры watchdog |
| `common.py` | конфиг, логи, `State`, клиент Telegram (обёртка над `curl.exe`) |
| `sysinfo.py` | сбор ресурсов / состояния Steam / игры / сессий |
| `gamectl.py` | запуск-останов Steam и игры, перезагрузка VM |
| `watchdog.py` | цикл поддержания игры |
| `bot.py` | команды и кнопки Telegram |
| `supervisor.py` | точка входа, single-instance lock |
| `install.ps1` | автологон + энергосбережение + регистрация задачи |
| `start.cmd` / `stop.cmd` | ручной запуск/останов |

## Установка (на VM)

```powershell
powershell -ExecutionPolicy Bypass -File C:\Users\alex\gamebot\stage2\install.ps1
Start-ScheduledTask -TaskName SigmaSteamBot
```

После этого бот пришлёт в Telegram «🟢 SigmaSteamBot запущен» с текущим статусом.

## Команды бота

| Команда | Действие |
|---|---|
| `/status` | CPU/RAM/диск, аптайм, Steam (работает + вошёл ли в аккаунт), игра (PID, время, RAM, окно, «не отвечает»/свёрнуто), сессия/RDP, счётчики перезапусков |
| `/shot` | скриншот экрана VM |
| `/startgame` `/stopgame` `/restartgame` | управление игрой |
| `/restartsteam` | перезапуск Steam |
| `/restartvm` | перезагрузка VM (с кнопкой подтверждения) |
| `/watchdog on\|off` | вкл/выкл авто-поддержание |
| `/stopbot` | остановить скрипт: `schtasks /Change /TN SigmaSteamBot /DISABLE` + выход процесса (с подтверждением). Игра/Steam не трогаются. Обратно — только с VM: `Enable-ScheduledTask -TaskName SigmaSteamBot; Start-ScheduledTask -TaskName SigmaSteamBot` |

Те же действия продублированы инлайн-кнопками под каждым ответом.
Доступ — только Telegram-ID из `allowed_user_ids`; остальным на `/start` бот
отвечает их ID и больше ничего не делает.

**Поднять после `/stopbot`** (задача отключена, Telegram недоступен):
двойной клик по ярлыку «Запустить SigmaSteamBot» на рабочем столе VM
(скрипт `start-bot.cmd`), либо по SSH с Linux — `../deploy/start-bot.sh`,
либо вручную `Enable-ScheduledTask -TaskName SigmaSteamBot; Start-ScheduledTask -TaskName SigmaSteamBot`.

## Логи и состояние

- `logs/supervisor.log` (ротация 5 МБ × 3)
- `state.json` — счётчики + последний снапшот
- `supervisor.lock` — PID работающего экземпляра

## Отключить

```powershell
Disable-ScheduledTask -TaskName SigmaSteamBot   # не стартовать при входе
Stop-ScheduledTask   -TaskName SigmaSteamBot    # остановить сейчас
```

Автологон снять: в `HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon`
установить `AutoAdminLogon=0` и удалить `DefaultPassword`.

## Известные ограничения

- Игра рендерится в той сессии, куда вошёл автологон (консоль). Если подключиться
  по RDP и **отключиться** (не выйти), сессия уезжает на RDP-станцию и Unity-игра
  может свернуться/перестать рендерить. Обходной путь (не входит в стадию 2):
  задача на событие отключения RDP, выполняющая `tscon <id> /dest:console`.
- `max_restarts_per_hour` (по умолчанию 8) защищает от «шторма» перезапусков —
  при достижении лимита watchdog приостанавливает авто-действия и пишет об этом.
- Прокси `192.168.0.222:2080` должен быть доступен; при его недоступности бот
  молча ретраит, а watchdog продолжает держать игру локально.
