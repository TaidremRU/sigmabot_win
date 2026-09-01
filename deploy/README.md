# SigmaSteamBot — развёртывание на Windows-VM

Автозапуск и авто-вход в игру **Sigma World Online** (Steam) + управление через
Telegram-бота. Держит Steam и игру запущенными, после запуска сам проходит
`Game → Local → ✔ Show server in the public Steam list → Play → окно Login → Ok`
и заходит в мир. Мониторинг и ручное управление — из Telegram.

---

## 1. Требования на целевой VM

| Что | Зачем |
|---|---|
| Windows 10/11, аккаунт **с правами администратора** | автологон, задачи, `tscon` |
| **Python 3.10+** в PATH (галочка «Add to PATH» при установке) | venv для бота |
| **Steam** установлен, вход в аккаунт сохранён (Remember password) | запуск игры |
| **Sigma World Online** установлена через Steam | сама игра |
| В игре: логин/пароль введены и стоит галочка **Remember** | авто-вход жмёт только «Ok» |
| **SOCKS5-прокси** до `api.telegram.org` (если Telegram заблокирован) | бот ходит через него |
| Разрешение сессии, где идёт игра — **1024×768** (см. §5) | координаты кликов рассчитаны под него |
| Telegram-бот от **@BotFather** (token) и ваш numeric ID (**@userinfobot**) | доступ к боту |

> `curl.exe` входит в Windows 10 1803+ — отдельно не нужен.

---

## 2. Установка

1. Скопируйте папку `deploy\` на целевую VM (например в `C:\deploy`).
2. Откройте **cmd от администратора**, перейдите в неё и запустите:

   ```bat
   cd C:\deploy
   setup.bat
   ```

   По умолчанию всё ставится в `%USERPROFILE%\sigmabot`. Свой путь и автологон:

   ```bat
   setup.bat C:\Users\alex\sigmabot /autologon alex МОЙ_ПАРОЛЬ
   ```

   `setup.bat` создаёт venv, ставит зависимости, копирует файлы, регистрирует
   3 задачи планировщика и (при `/autologon`) прописывает автологон.

3. **Отредактируйте `%BASE%\config.json`** (см. §3).

4. Проверьте окружение:

   ```bat
   "%BASE%\venv\Scripts\python.exe" "%BASE%\selftest.py"
   ```

   Должно напечатать состояние VM/Steam/игры и `telegram getUpdates ... ok=True`.

5. Запустите:

   ```powershell
   Start-ScheduledTask -TaskName SigmaSteamBot
   ```

   В Telegram придёт «🟢 SigmaSteamBot запущен». Дальше `/help`.

---

## 3. `config.json` — что заполнить

| Поле | Пример / примечание |
|---|---|
| `steam_exe` | `C:\Program Files (x86)\Steam\Steam.exe` |
| `game_appid` | `1690980` (Sigma World Online) |
| `game_install_dir` | папка игры в `steamapps\common\...` — по ней ищется процесс |
| `base_dir` | **та же папка, куда всё поставлено** (`%BASE%`), с двойными `\\` |
| `telegram.token` | токен от @BotFather |
| `telegram.allowed_user_ids` | `[280331544]` — ваш numeric Telegram ID |
| `telegram.proxy` | `socks5h://HOST:PORT` вашего SOCKS5; если Telegram доступен напрямую — всё равно нужен рабочий SOCKS5 (клиент всегда идёт через него) |
| `game_window_size` | `[1024, 768]` — под него рассчитаны координаты `login_flow` |
| `login_flow.menu_steps` / `ok` | координаты кликов ОТНОСИТЕЛЬНО окна игры (см. §5) |
| `login_flow.after_ingame` | шаги после входа в мир — по умолчанию клик по иконке чата в тулбаре (чтобы читать чат через `/shot`); пустой список = ничего |
| `watchdog.auto_login` | `true` — заходить в игру автоматически после запуска |
| `watchdog.login_settle_seconds` | пауза после появления игры до попытки входа |

---

## 4. Команды бота

| Команда / кнопка | Действие |
|---|---|
| `/status` | CPU/RAM/диск, аптайм; Steam (+вход в аккаунт); игра (PID, RAM, окно, «в меню / вход выполняется / в игре»); сессия/RDP; счётчики перезапусков |
| `/shot` | скриншот окна игры (работает и в простаивающей сессии) |
| `/login` | пройти вход в игру вручную |
| `/startgame` `/stopgame` `/restartgame` | управление игрой |
| `/restartsteam` | перезапуск Steam |
| `/restartvm` | перезагрузка VM (с подтверждением) |
| `/watchdog on\|off` | авто-поддержание игры |
| `/stopbot` | остановить сам скрипт: отключает задачу `SigmaSteamBot` (авто-рестарта и старта при загрузке VM больше не будет) и завершает процесс. С подтверждением. Игра и Steam продолжают работать. Запуск обратно — только с VM: `Enable-ScheduledTask -TaskName SigmaSteamBot; Start-ScheduledTask -TaskName SigmaSteamBot` |

Имя задачи берётся из `task_name` в `config.json` (по умолчанию `SigmaSteamBot`).

Алерты (падение/перезапуск/итог автологина) шлются в чат сами.

### Как поднять бота после `/stopbot`

Telegram уже не поможет (бот выключен) — только с VM или по SSH:

* **На VM:** двойной клик по ярлыку **«Запустить SigmaSteamBot»** на рабочем столе
  (его создаёт `install.ps1`; сам скрипт — `start-bot.cmd` в папке бота, при
  необходимости сам просит повышение прав).
* **По SSH с Linux:** `deploy/start-bot.sh` (обёртка над `ssh` + `sshpass`).
  Хост/логин/пароль/имя задачи переопределяются через переменные окружения
  `SIGMA_VM_HOST` / `SIGMA_VM_USER` / `SIGMA_VM_PASS` / `SIGMA_TASK`.
* **Вручную (PowerShell на VM):**
  `Enable-ScheduledTask -TaskName SigmaSteamBot; Start-ScheduledTask -TaskName SigmaSteamBot`
  (`Enable` обязателен — `/stopbot` именно отключает задачу).

---

## 5. Подгонка координат кликов (если другое разрешение / версия игры)

Координаты в `login_flow` — пиксели ОТНОСИТЕЛЬНО левого-верхнего угла окна игры
при `game_window_size`. Проверить/снять новые:

```bat
REM записать команду для задачи SigmaNav и запустить её
echo shot menu > "%BASE%\nav_cmd.txt"
powershell Start-ScheduledTask -TaskName SigmaNav
REM скрин: %BASE%\logs\nav\latest.png  — по нему меряете кнопки
```

Другие команды `nav.py` (через `nav_cmd.txt` + `Start-ScheduledTask SigmaNav`, либо
`"%BASE%\venv\Scripts\python.exe" "%BASE%\nav.py" <...>`):

* `state` — что на экране (`menu/login/loading/ingame`)
* `click <rx> <ry> [left|right]` — клик + скрин после
* `restore` — развернуть окно в `0,0,W,H`
* `seq login` — вся последовательность входа

Пиксельные пробы распознавания экрана — в `detect.py` (тоже под 1024×768,
масштабируются, но при сильно другом UI сверьте).

---

## 6. Как это устроено

```
Задача SigmaSteamBot (AtLogon, Interactive/Highest, авто-рестарт)
  └─ venv\pythonw.exe supervisor.py         (один процесс)
       ├─ watchdog  — держит Steam+игру; после запуска игры и паузы
       │              login_settle_seconds -> авто-вход; пишет state.json
       ├─ bot       — Telegram long-poll через SOCKS5 (обёртка над curl.exe),
       │              отдельный поток-отправитель, чтобы сеть не блокировала
       └─ авто-вход и /login  ->  runner.run_nav("seq login")
              └─ Start-ScheduledTask SigmaNav   (нужен реальный фокус окна —
                     фоновый поток супервизора SetForegroundWindow не может)
                     └─ nav.py: normalize окна -> detect состояния ->
                        клики Game/Local/✔/Play -> ждать сервер ->
                        Ok (в цикле, пока не ingame)

Задача SigmaConsoleGuard (SYSTEM, по событию отключения RDP 24/40)
  └─ console_guard.ps1  ->  tscon <сессия alex> /dest:console
```

**Почему консольная сессия обязательна:** SendInput/фокус в игру работают только
когда сессия с игрой — активная консольная. Если зайти по RDP и отключиться,
`SigmaConsoleGuard` вернёт сессию на консоль. Штатно в эту сессию по RDP не
заходят — смотрят через `/shot`.

Файлы в `%BASE%`: `*.py` (код), `config.json`, `state.json` (счётчики+снапшот),
`logs\supervisor.log` (ротация 5МБ×3), `logs\nav\*.png` (скрины шагов, авто-чистка
до 80), `supervisor.lock`, `nav_cmd.txt`/`nav_out.txt` (обмен с SigmaNav).

---

## 7. Управление и диагностика

```powershell
Start-ScheduledTask  -TaskName SigmaSteamBot     # запустить
Stop-ScheduledTask   -TaskName SigmaSteamBot     # остановить
Disable-ScheduledTask -TaskName SigmaSteamBot    # не стартовать при входе
Get-Content C:\...\sigmabot\logs\supervisor.log -Tail 40 -Wait
```

`start.cmd` — запуск supervisor в консоли (видно stdout) для отладки.

Снять автологон: в `HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon`
`AutoAdminLogon=0`, удалить `DefaultPassword`.

Полностью удалить:

```powershell
'SigmaSteamBot','SigmaNav','SigmaConsoleGuard' | % { Unregister-ScheduledTask -TaskName $_ -Confirm:$false }
Remove-Item -Recurse C:\Users\alex\sigmabot
```

---

## 8. Типовые проблемы

| Симптом | Причина / что делать |
|---|---|
| `/shot` присылает ошибку `screen grab failed` | сессия не консольная — зайдите один раз и отключитесь (сработает `SigmaConsoleGuard`), либо перезагрузите VM без RDP |
| Клики в игру не проходят, в логе `NOT-FOCUSED` | то же — нужна активная консольная сессия |
| Авто-вход кликает мимо / открывает язык | окно игры не 1024×768 или другое разрешение сессии — выставьте разрешение и/или пересоберите координаты (§5) |
| `getUpdates: curl rc=28/35` в логе | прокси недоступен/медленный; бот сам ретраит, watchdog не блокируется |
| После ребута бот не заходит в игру | проверьте автологон (должна быть `console <user> Активна` в `qwinsta`) и что Steam помнит пароль, а игра — креды |
| `login_state` застрял в `running` | смотрите `logs\nav\seq*.png` и `nav_out.txt` — на каком шаге встало |
