<!-- SPDX note: private project — TaidremRU/sigmabot_win -->

# SigmaSteamBot

**RU:** Автозапуск, авто-вход и Telegram-управление игрой **Sigma World Online** (Steam AppID `1690980`) на выделенной Windows-VM. Держит Steam и игру запущенными, сам проходит вход в мир, отдаёт статус/скриншоты и список публичных серверов в Telegram, следит за присутствием нужного сервера в списке Steam-лобби.

**EN:** Auto-start, auto-login and Telegram control for the game **Sigma World Online** (Steam AppID `1690980`) on a dedicated Windows VM. Keeps Steam and the game running, walks the in-game login itself, serves status / screenshots / the public server list over Telegram, and watches whether a specific server stays present in the Steam lobby list.

**Языки / Languages:** [Русский](#русский) · [English](#english)

---

## Русский

### Что это

Один процесс (`supervisor.py`), запускаемый задачей планировщика `SigmaSteamBot` при входе в систему (автологон `alex`). Внутри — два потока:

| Поток | Задача |
|---|---|
| **watchdog** | следит, что Steam и игра запущены; поднимает упавшее; после старта игры сам проходит вход в мир; каждые ~30 c пишет снапшот в `state.json` |
| **bot** | Telegram long-polling **через SOCKS5-прокси** (с VM `api.telegram.org` напрямую недоступен); команды, кнопки, алерты |
| *(+ поток `srvmonitor`)* | раз в 5 минут проверяет, есть ли сервер `AstralSigma` в списке публичных Steam-лобби |

Вход в игру (`Game → Local → ✔ Show server in the public Steam list → Play → окно Login → Ok`) прогоняется отдельной задачей `SigmaNav` — фоновому потоку не даёт фокус окна `SetForegroundWindow`. Игра рендерится и принимает ввод только в **активной консольной сессии**; задача `SigmaConsoleGuard` возвращает сессию на консоль при отключении RDP.

### Архитектура

```
Задача SigmaSteamBot (AtLogon, Interactive/Highest, авто-рестарт каждые 2 мин)
  └─ venv\pythonw.exe supervisor.py                     (single-instance по supervisor.lock)
       ├─ watchdog   держит Steam+игру → авто-вход → state.json
       ├─ bot        Telegram long-poll через SOCKS5 (обёртка над curl.exe)
       │              ├─ поток-отправитель (сеть не блокирует опрос)
       │              └─ srvmonitor: раз в 5 мин serverlist.fetch → есть ли AstralSigma
       └─ вход в игру → runner.run_nav("seq login")
              └─ Start-ScheduledTask SigmaNav → nav.py (detect состояния экрана → клики)

Задача SigmaConsoleGuard (SYSTEM, по событию отключения RDP)
  └─ console_guard.ps1 → tscon <сессия> /dest:console

Кнопка «Серверы» / монитор:
  serverlist.fetch → serverlist_steam.py (отдельный процесс)
       └─ ctypes + steam_api64.dll игры → RequestLobbyList → список Steam-лобби
       └─ запасной слой: Steam Web API GetServerList (нужен ключ)
```

### Компоненты

| Файл | Назначение |
|---|---|
| `supervisor.py` | точка входа, lock, запуск watchdog + bot |
| `watchdog.py` | цикл поддержания Steam/игры, авто-вход, алерты |
| `bot.py` | команды и inline-кнопки Telegram, роли, аудит, фоновый монитор сервера |
| `common.py` | конфиг, логи, `State` (в `state.json`), клиент Telegram поверх `curl.exe` + SOCKS5 |
| `i18n.py` | двуязычные строки (`ru`/`en`) + `t()`; паритет ключей проверяет `selftest.py` |
| `gamectl.py` | старт/стоп/рестарт Steam и игры, перезагрузка VM, отключение задачи бота |
| `sysinfo.py` | сбор ресурсов, состояния Steam/игры/сессий |
| `nav.py` / `detect.py` / `runner.py` | последовательность входа в мир (по пикселям экрана) |
| `serverlist.py` | `fetch(cfg) → (ok, servers, source)`: сначала Steam-лобби, при ошибке — Web API |
| `serverlist_steam.py` | перечисление Steam-лобби через `steam_api64.dll` игры (`ctypes`), отдельный процесс |
| `screenshot.py` | снимок окна игры через `PrintWindow` (работает в простаивающей сессии) |
| `console_guard.ps1` | возврат сессии на консоль при отключении RDP |
| `install.ps1` | автологон + отключение сна + регистрация 3 задач + ярлык на рабочем столе |
| `selftest.py` | быстрая проверка модулей/конфига/i18n/Telegram без входа в бесконечный цикл |

### Роли

- **admin** — ID из `telegram.allowed_user_ids`: полный доступ.
- **moderator** — ID из `telegram.moderator_user_ids`: только `/status`, `/shot`, `/restartgame`, `/login`, `/lang`. Кнопки админ-действий не показываются; `/servers`, watchdog, Steam, VM, `/stopbot` недоступны. ID из обоих списков считается админом.
- **главный админ** — `telegram.super_admin_id` (по умолчанию первый из `allowed_user_ids`): получает строку `👤 Имя (роль) → действие` на каждое действие другого админа/модератора, **меняющее состояние** (start/stop/restart игры и Steam, `/login`, `/watchdog on|off`, подтверждённый ребут VM, `/stopbot`). `/status`, `/shot`, `/lang`, `/servers` не логируются.

Язык — на пользователя (`/lang ru|en` или кнопка «🌐 Язык»), хранится в `state.json`; по умолчанию `telegram.default_lang`.

### Команды бота

| Команда / кнопка | Роль | Действие |
|---|---|---|
| `/status` | админ, модератор | CPU/RAM/диск, аптайм; Steam (+вход в аккаунт); игра (PID, RAM, окно, «в меню / вход выполняется / в игре»); сессия/RDP; счётчики перезапусков |
| `/shot` | админ, модератор | скриншот окна игры |
| `/servers` | **админ** | список публичных серверов (Steam-лобби): имя, игроки, карта, версия. **AstralSigma** подсвечивается 👑 и поднимается наверх |
| `/restartgame` | админ, модератор | перезапуск игры **+ сразу авто-вход в мир**, в конце скриншот |
| `/login` | админ, модератор | пройти вход в игру вручную |
| `/lang ru\|en` | админ, модератор | язык интерфейса |
| `/startgame` `/stopgame` | админ | запуск / останов игры без входа |
| `/restartsteam` | админ | перезапуск Steam |
| `/restartvm` | админ | перезагрузка VM (с подтверждением) |
| `/watchdog on\|off` | админ | авто-поддержание игры |
| `/stopbot` | админ | отключить задачу `SigmaSteamBot` и завершить процесс (с подтверждением). Игра и Steam не трогаются. Обратно — только с VM |

Те же действия продублированы inline-кнопками. Неизвестным ID на `/start` бот отвечает их numeric ID и больше ничего.

### Список серверов

Sigma World Online **не регистрирует game-серверы** в мастер-листе Valve — каждый публичный хост создаёт **Steam-лобби** (`ISteamMatchmaking::CreateLobby`). Поэтому:

- **Основной путь** — `serverlist_steam.py` отдельным коротким процессом грузит `steam_api64.dll` **самой игры** через `ctypes`, вызывает `SteamAPI_InitFlat` → `RequestLobbyList` → читает `GetLobbyData` (`server_name`, `world_name`, `players`, `max_players`, `build`). Требует **консольную сессию** (там Steam) — супервизор в ней и работает, поэтому обычного `subprocess` достаточно.
- **Запасной слой** — Steam Web API `IGameServersService/GetServerList` (нужен ключ `steam_web_api_key`, https://steamcommunity.com/dev/apikey). Пусто, пока игра не публикует настоящие серверы — оставлено на будущее.

### Фоновый монитор сервера

Поток `srvmonitor` в супервизоре. Первая проверка через ~90 c после старта, дальше каждые `monitor.interval_seconds` (по умолчанию 300):

- нет `monitor.server_name` в списке **`misses_before_alert`** проверок подряд (2 ≈ 10 мин) → рассылка **всем админам И модераторам** `⚠️ <name> пропал из публичного списка серверов Steam`;
- пока отсутствует — тишина, но раз в `repeat_alert_seconds` (3600, `0` = один раз) — напоминание;
- вернулся → `✅ <name> снова в публичном списке` (один раз), счётчик сбрасывается;
- запрос списка не удался → тик пропускается (не считается «пропажей»), только запись в лог.

Состояние (`monitor_astral` в `state.json`) переживает перезапуск бота — повторных ложных тревог после рестарта нет.

### Установка

Подробный гайд — [`deploy/README.md`](deploy/README.md). Кратко: скопировать `deploy\` на VM → `setup.bat [BASE] [/autologon USER PASS]` → заполнить `%BASE%\config.json` → `selftest.py` → `Start-ScheduledTask -TaskName SigmaSteamBot`. Шаблон конфига — [`deploy/app/config.example.json`](deploy/app/config.example.json).

### Ключевые поля `config.json`

| Поле | Назначение |
|---|---|
| `game_appid` | `1690980` |
| `base_dir` | папка установки (с `\\`) |
| `steam_api_dll` | путь к `steam_api64.dll` **игры** (для `/servers` и монитора) |
| `steam_web_api_key` | ключ Steam Web API — запасной путь списка серверов |
| `python_exe` | python для дочерних скриптов; пусто → авто (`sys.executable`, `pythonw`→`python`) |
| `monitor` | `{ enabled, server_name, interval_seconds, misses_before_alert, repeat_alert_seconds }` |
| `telegram.token` | токен @BotFather |
| `telegram.allowed_user_ids` / `moderator_user_ids` / `super_admin_id` | роли |
| `telegram.default_lang` | `ru` \| `en` |
| `telegram.proxy` | `socks5h://HOST:PORT` — клиент всегда идёт через SOCKS5 |
| `game_window_size` / `login_flow` | координаты кликов входа (жёстко под 1024×768) |
| `watchdog.*` | авто-поддержание, лимит перезапусков, тайминги авто-входа |

`config.json` и `key.txt` — в `.gitignore` (секреты). Шаблон — `deploy/app/config.example.json`.

### Эксплуатация

```powershell
Start-ScheduledTask   -TaskName SigmaSteamBot   # запустить
Stop-ScheduledTask    -TaskName SigmaSteamBot   # остановить сейчас
Disable-ScheduledTask -TaskName SigmaSteamBot   # не стартовать при входе
Get-Content <BASE>\logs\supervisor.log -Tail 40 -Wait
<BASE>\venv\Scripts\python.exe <BASE>\selftest.py
```

После `/stopbot` (задача отключена, Telegram не поможет): ярлык **«Запустить SigmaSteamBot»** на рабочем столе VM, либо по SSH — `deploy/start-bot.sh`, либо вручную `Enable-ScheduledTask` + `Start-ScheduledTask`.

### Ограничения

- Координаты `login_flow` рассчитаны под окно **1024×768**; другое разрешение → пересобрать координаты (`deploy/README.md`, §5).
- Всё UI-взаимодействие требует **активной консольной сессии**; при заходе по RDP и отключении сессию возвращает `SigmaConsoleGuard`.
- SOCKS5-прокси должен быть доступен; при недоступности бот молча ретраит, watchdog продолжает держать игру локально.
- В публичном списке лобби обычно 1 запись (нишевая игра) — мультисписок в `/servers` протестирован на синтетике.
- Язык игры иногда самопроизвольно переключается на Polski (клик по стрелке языка) — на координаты не влияет.

---

## English

### What it is

A single process (`supervisor.py`) launched by the `SigmaSteamBot` scheduled task at logon (auto-logon as `alex`). It runs two threads:

| Thread | Job |
|---|---|
| **watchdog** | keeps Steam and the game running; relaunches whatever died; after the game starts, walks the in-game login itself; writes a `state.json` snapshot every ~30 s |
| **bot** | Telegram long-polling **through a SOCKS5 proxy** (`api.telegram.org` is unreachable directly from the VM); commands, buttons, alerts |
| *(+ `srvmonitor` thread)* | every 5 minutes checks whether the `AstralSigma` server is present in the public Steam lobby list |

The in-game login (`Game → Local → ✔ Show server in the public Steam list → Play → Login window → Ok`) runs in a dedicated `SigmaNav` task — a background thread can't take window focus (`SetForegroundWindow`). The game renders and accepts input only in an **active console session**; the `SigmaConsoleGuard` task redirects the session back to the console when RDP disconnects.

### Architecture

```
SigmaSteamBot task (AtLogon, Interactive/Highest, auto-restart every 2 min)
  └─ venv\pythonw.exe supervisor.py                     (single instance via supervisor.lock)
       ├─ watchdog    keeps Steam+game → auto-login → state.json
       ├─ bot         Telegram long-poll via SOCKS5 (wrapper over curl.exe)
       │               ├─ sender thread (network never blocks polling)
       │               └─ srvmonitor: every 5 min serverlist.fetch → is AstralSigma listed
       └─ game login → runner.run_nav("seq login")
              └─ Start-ScheduledTask SigmaNav → nav.py (screen-state detect → clicks)

SigmaConsoleGuard task (SYSTEM, on RDP-disconnect event)
  └─ console_guard.ps1 → tscon <session> /dest:console

"Servers" button / monitor:
  serverlist.fetch → serverlist_steam.py (separate process)
       └─ ctypes + the game's steam_api64.dll → RequestLobbyList → Steam lobby list
       └─ fallback layer: Steam Web API GetServerList (needs a key)
```

### Components

| File | Purpose |
|---|---|
| `supervisor.py` | entry point, lock, starts watchdog + bot |
| `watchdog.py` | Steam/game keep-alive loop, auto-login, alerts |
| `bot.py` | Telegram commands and inline buttons, roles, audit, background server monitor |
| `common.py` | config, logging, `State` (in `state.json`), Telegram client over `curl.exe` + SOCKS5 |
| `i18n.py` | bilingual strings (`ru`/`en`) + `t()`; key parity checked by `selftest.py` |
| `gamectl.py` | start/stop/restart Steam and game, reboot VM, disable the bot task |
| `sysinfo.py` | collects resources, Steam/game/session state |
| `nav.py` / `detect.py` / `runner.py` | in-game login sequence (driven by screen pixels) |
| `serverlist.py` | `fetch(cfg) → (ok, servers, source)`: Steam lobbies first, Web API on failure |
| `serverlist_steam.py` | enumerates Steam lobbies via the game's `steam_api64.dll` (`ctypes`), separate process |
| `screenshot.py` | game-window capture via `PrintWindow` (works in an idle session) |
| `console_guard.ps1` | redirects the session to the console on RDP disconnect |
| `install.ps1` | auto-logon + sleep off + registers 3 tasks + desktop shortcut |
| `selftest.py` | quick check of modules/config/i18n/Telegram without entering the main loop |

### Roles

- **admin** — IDs in `telegram.allowed_user_ids`: full access.
- **moderator** — IDs in `telegram.moderator_user_ids`: only `/status`, `/shot`, `/restartgame`, `/login`, `/lang`. Admin-action buttons are hidden; `/servers`, watchdog, Steam, VM, `/stopbot` are unavailable. An ID in both lists counts as an admin.
- **super-admin** — `telegram.super_admin_id` (defaults to the first of `allowed_user_ids`): receives a `👤 Name (role) → action` line for every **state-changing** action by another admin/moderator (start/stop/restart of game and Steam, `/login`, `/watchdog on|off`, confirmed VM reboot, `/stopbot`). `/status`, `/shot`, `/lang`, `/servers` are not logged.

Language is per-user (`/lang ru|en` or the “🌐 Language” button), stored in `state.json`; default is `telegram.default_lang`.

### Bot commands

| Command / button | Role | Action |
|---|---|---|
| `/status` | admin, moderator | CPU/RAM/disk, uptime; Steam (+ signed in); game (PID, RAM, window, “at menu / logging in / in game”); session/RDP; restart counters |
| `/shot` | admin, moderator | game-window screenshot |
| `/servers` | **admin** | public server list (Steam lobbies): name, players, map, version. **AstralSigma** is highlighted 👑 and pinned to the top |
| `/restartgame` | admin, moderator | restart the game **and immediately auto-login to the world**, screenshot at the end |
| `/login` | admin, moderator | run the in-game login manually |
| `/lang ru\|en` | admin, moderator | interface language |
| `/startgame` `/stopgame` | admin | start / stop the game without login |
| `/restartsteam` | admin | restart Steam |
| `/restartvm` | admin | reboot the VM (with confirmation) |
| `/watchdog on\|off` | admin | game keep-alive |
| `/stopbot` | admin | disable the `SigmaSteamBot` task and exit the process (with confirmation). The game and Steam are left running. Restart only from the VM |

The same actions are mirrored as inline buttons. To an unknown ID, `/start` replies with its numeric ID and nothing else.

### Server list

Sigma World Online **does not register game servers** with Valve’s master list — each public host creates a **Steam lobby** (`ISteamMatchmaking::CreateLobby`). Therefore:

- **Primary path** — `serverlist_steam.py`, a short-lived separate process, loads **the game’s own** `steam_api64.dll` via `ctypes`, calls `SteamAPI_InitFlat` → `RequestLobbyList` → reads `GetLobbyData` (`server_name`, `world_name`, `players`, `max_players`, `build`). Requires a **console session** (that’s where Steam lives) — the supervisor already runs there, so a plain `subprocess` is enough.
- **Fallback layer** — Steam Web API `IGameServersService/GetServerList` (needs a `steam_web_api_key`, https://steamcommunity.com/dev/apikey). Empty until the game publishes real servers — kept for the future.

### Background server monitor

The `srvmonitor` thread in the supervisor. First check ~90 s after start, then every `monitor.interval_seconds` (default 300):

- `monitor.server_name` missing for **`misses_before_alert`** consecutive checks (2 ≈ 10 min) → broadcast to **all admins AND moderators**: `⚠️ <name> disappeared from the public Steam server list`;
- while still missing — silent, except a reminder every `repeat_alert_seconds` (3600, `0` = once);
- back → `✅ <name> is back in the public list` (once), counter reset;
- if the list request itself fails → the tick is skipped (not counted as “missing”), logged only.

State (`monitor_astral` in `state.json`) survives a bot restart — no repeated false alarms after a restart.

### Install

Full guide — [`deploy/README.md`](deploy/README.md). In short: copy `deploy\` to the VM → `setup.bat [BASE] [/autologon USER PASS]` → fill in `%BASE%\config.json` → `selftest.py` → `Start-ScheduledTask -TaskName SigmaSteamBot`. Config template — [`deploy/app/config.example.json`](deploy/app/config.example.json).

### Key `config.json` fields

| Field | Purpose |
|---|---|
| `game_appid` | `1690980` |
| `base_dir` | install folder (with `\\`) |
| `steam_api_dll` | path to the **game’s** `steam_api64.dll` (for `/servers` and the monitor) |
| `steam_web_api_key` | Steam Web API key — fallback path for the server list |
| `python_exe` | python for child scripts; empty → auto (`sys.executable`, `pythonw`→`python`) |
| `monitor` | `{ enabled, server_name, interval_seconds, misses_before_alert, repeat_alert_seconds }` |
| `telegram.token` | @BotFather token |
| `telegram.allowed_user_ids` / `moderator_user_ids` / `super_admin_id` | roles |
| `telegram.default_lang` | `ru` \| `en` |
| `telegram.proxy` | `socks5h://HOST:PORT` — the client always goes through SOCKS5 |
| `game_window_size` / `login_flow` | login click coordinates (hard-tuned for 1024×768) |
| `watchdog.*` | keep-alive, restart cap, auto-login timings |

`config.json` and `key.txt` are in `.gitignore` (secrets). Template — `deploy/app/config.example.json`.

### Operations

```powershell
Start-ScheduledTask   -TaskName SigmaSteamBot   # start
Stop-ScheduledTask    -TaskName SigmaSteamBot   # stop now
Disable-ScheduledTask -TaskName SigmaSteamBot   # don't start at logon
Get-Content <BASE>\logs\supervisor.log -Tail 40 -Wait
<BASE>\venv\Scripts\python.exe <BASE>\selftest.py
```

After `/stopbot` (task disabled, Telegram won’t help): the **“Запустить SigmaSteamBot”** desktop shortcut on the VM, or over SSH — `deploy/start-bot.sh`, or manually `Enable-ScheduledTask` + `Start-ScheduledTask`.

### Limitations

- `login_flow` coordinates are tuned for a **1024×768** window; a different resolution → re-measure the coordinates (`deploy/README.md`, §5).
- All UI interaction needs an **active console session**; on RDP connect+disconnect the session is returned by `SigmaConsoleGuard`.
- The SOCKS5 proxy must be reachable; if it isn’t, the bot retries silently and the watchdog keeps the game up locally.
- The public lobby list usually has a single entry (niche game) — the multi-entry `/servers` view is tested on synthetic data.
- The game’s language occasionally flips to Polski by itself (a click on the language arrow) — it does not affect coordinates.
