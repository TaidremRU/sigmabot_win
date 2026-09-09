# -*- coding: utf-8 -*-
"""Управление Steam и игрой Sigma World Online.

Функции жизненного цикла Steam/игры возвращают тройку ``(ok, msg_key, params)``:
``msg_key`` — ключ i18n (``gc.*``), ``params`` — словарь подстановок (может быть
пустым). Перевод делает вызывающий (bot по языку пользователя, watchdog по
языку по умолчанию). ``restart_vm`` и ``disable_bot_task`` возвращают
``(ok, text)`` с сырым системным выводом — переводить там нечего.
"""
import logging
import os
import subprocess
import time

import sysinfo


def _run(cmd, timeout=30):
    logging.info("run: %s", " ".join(str(c) for c in cmd))
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout)
        return (
            r.returncode,
            r.stdout.decode("cp866", "replace"),
            r.stderr.decode("cp866", "replace"),
        )
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except Exception as e:  # noqa: BLE001
        return -2, "", str(e)


def steam_running():
    return bool(sysinfo.find_procs(["steam.exe"]))


def game_running(cfg):
    return bool(sysinfo.find_procs(["sigmaworld.exe"], cfg.get("game_install_dir")))


def start_steam(cfg, wait=25):
    if steam_running():
        return True, "gc.steam_already_running", {}
    subprocess.Popen([cfg["steam_exe"], "-silent"], close_fds=True)
    for _ in range(wait):
        time.sleep(1)
        if steam_running():
            return True, "gc.steam_started", {}
    return False, "gc.steam_timeout", {"sec": wait}


def stop_steam(cfg, wait=25):
    if not steam_running():
        return True, "gc.steam_already_stopped", {}
    _run([cfg["steam_exe"], "-shutdown"], timeout=10)
    for _ in range(wait):
        time.sleep(1)
        if not steam_running():
            return True, "gc.steam_stopped", {}
    _run(["taskkill", "/F", "/T", "/IM", "steam.exe"])
    time.sleep(2)
    return (not steam_running()), "gc.steam_killed", {}


def start_game(cfg, ensure_steam=True, wait=60):
    if game_running(cfg):
        return True, "gc.game_already_running", {}
    if ensure_steam and not steam_running():
        ok, key, params = start_steam(cfg)
        if not ok:
            return False, key, params
        time.sleep(8)
    url = "steam://rungameid/%d" % cfg["game_appid"]
    try:
        os.startfile(url)  # noqa: S606  (запуск в интерактивной сессии — намеренно)
    except OSError:
        subprocess.Popen(["explorer.exe", url])
    for _ in range(wait):
        time.sleep(1)
        if game_running(cfg):
            return True, "gc.game_started", {}
    return False, "gc.game_timeout", {"sec": wait}


def stop_game(cfg):
    if not game_running(cfg):
        return True, "gc.game_already_stopped", {}
    _run(["taskkill", "/F", "/IM", "SigmaWorld.exe"])
    _run(["taskkill", "/F", "/IM", "UnityCrashHandler64.exe"])
    time.sleep(2)
    return (not game_running(cfg)), "gc.game_stopped", {}


def restart_game(cfg):
    stop_game(cfg)
    time.sleep(3)
    return start_game(cfg)


def restart_steam(cfg):
    stop_steam(cfg)
    time.sleep(3)
    ok, key, params = start_steam(cfg)
    if ok:
        return True, "gc.steam_restarted", {}
    return False, key, params


def restart_vm(reason="SigmaSteamBot restart"):
    rc, out, err = _run(["shutdown", "/r", "/t", "3", "/f", "/c", reason], timeout=10)
    return rc == 0, (err or out or ("rc=%d" % rc))


def disable_bot_task(task_name="SigmaSteamBot"):
    """Отключить задачу планировщика супервизора, чтобы он не поднялся заново.

    Задача SigmaSteamBot стартует и по входу в систему, и авто-рестартом раз в 2
    минуты; без её отключения простой выход процесса ничего не даст.
    """
    rc, out, err = _run(["schtasks", "/Change", "/TN", task_name, "/DISABLE"], timeout=20)
    return rc == 0, (err.strip() or out.strip() or ("rc=%d" % rc))
