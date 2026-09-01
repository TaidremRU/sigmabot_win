# -*- coding: utf-8 -*-
"""Сбор данных о состоянии VM, Steam и игры."""
import ctypes
import logging
import time
from ctypes import wintypes

import psutil

try:
    import winreg
except ImportError:  # не Windows — только для локальной проверки синтаксиса
    winreg = None

user32 = ctypes.windll.user32 if hasattr(ctypes, "windll") else None


def _steam_reg(subkey, value):
    if not winreg:
        return None
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, subkey)
        try:
            v, _ = winreg.QueryValueEx(k, value)
            return v
        finally:
            winreg.CloseKey(k)
    except OSError:
        return None


def steam_logged_in():
    v = _steam_reg(r"Software\Valve\Steam\ActiveProcess", "ActiveUser")
    return None if v is None else int(v) != 0


def steam_account():
    return _steam_reg(r"Software\Valve\Steam", "AutoLoginUser") or None


def find_procs(names=None, exe_prefix=None):
    out = []
    names = set(n.lower() for n in (names or []))
    prefix = exe_prefix.lower() if exe_prefix else None
    for p in psutil.process_iter(["name", "exe", "create_time"]):
        try:
            nm = (p.info["name"] or "").lower()
            ex = (p.info["exe"] or "")
            if nm in names or (prefix and ex and ex.lower().startswith(prefix)):
                out.append(p)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return out


def _main_window(pid):
    """Возвращает (hwnd, title) первого видимого окна процесса с текстом."""
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _lparam):
        pv = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pv))
        if pv.value == pid and user32.IsWindowVisible(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            if n > 0:
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, buf, n + 1)
                if buf.value.strip():
                    found.append((hwnd, buf.value))
        return True

    try:
        user32.EnumWindows(cb, 0)
    except Exception as e:  # noqa: BLE001
        logging.debug("EnumWindows: %s", e)
    return found[0] if found else (None, None)


def _sessions():
    try:
        import win32ts

        h = win32ts.WTS_CURRENT_SERVER_HANDLE
        names = {
            0: "active", 1: "connected", 2: "connectquery", 3: "shadow", 4: "disconnected",
            5: "idle", 6: "listen", 7: "reset", 8: "down", 9: "init",
        }
        res = []
        for s in win32ts.WTSEnumerateSessions(h):
            sid = s["SessionId"]
            try:
                user = win32ts.WTSQuerySessionInformation(h, sid, win32ts.WTSUserName)
            except Exception:  # noqa: BLE001
                user = ""
            res.append({
                "id": sid,
                "station": s["WinStationName"],
                "state": names.get(int(s["State"]), str(s["State"])),
                "user": user,
            })
        return res
    except Exception as e:  # noqa: BLE001
        logging.debug("sessions: %s", e)
        return []


def collect(cfg, state=None):
    now = time.time()
    boot = psutil.boot_time()
    vm = psutil.virtual_memory()
    du = psutil.disk_usage("C:\\")

    steam_procs = find_procs(["steam.exe"])
    game_procs = find_procs(["sigmaworld.exe"], cfg.get("game_install_dir"))

    game = {"running": bool(game_procs)}
    if game_procs:
        p = game_procs[0]
        try:
            cpu = p.cpu_percent(interval=0.3)
            with p.oneshot():
                game["pid"] = p.pid
                game["rss"] = p.memory_info().rss
                game["run_seconds"] = int(now - p.create_time())
            game["cpu"] = cpu
            hwnd, title = _main_window(p.pid)
            game["window_title"] = title
            if hwnd:
                game["minimized"] = bool(user32.IsIconic(hwnd))
                game["responding"] = not bool(user32.IsHungAppWindow(hwnd))
            else:
                game["minimized"] = None
                game["responding"] = None
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            game["running"] = bool(find_procs(["sigmaworld.exe"], cfg.get("game_install_dir")))

    sess = _sessions()
    rdp = [s for s in sess if str(s["station"]).lower().startswith("rdp-tcp") and s["user"]]
    console = [s for s in sess if str(s["station"]).lower() == "console" and s["user"]]

    snap = {
        "ts": now,
        "boot_time": boot,
        "uptime_seconds": int(now - boot),
        "cpu_percent": psutil.cpu_percent(interval=0.5),
        "cpu_count": psutil.cpu_count(),
        "mem": {"total": vm.total, "used": vm.total - vm.available, "percent": vm.percent},
        "disk_c": {"total": du.total, "used": du.used, "free": du.free, "percent": du.percent},
        "steam": {
            "running": bool(steam_procs),
            "pids": [p.pid for p in steam_procs],
            "logged_in": steam_logged_in(),
            "account": steam_account(),
        },
        "game": game,
        "sessions": sess,
        "rdp_connected": bool(rdp),
        "console_active": any(s["state"] == "active" for s in console),
    }
    if state is not None:
        with state.lock:
            snap["counters"] = {
                "game_restarts": state.data.get("game_restarts", 0),
                "steam_restarts": state.data.get("steam_restarts", 0),
                "last_game_exit_code": state.data.get("last_game_exit_code"),
                "last_restart_ts": state.data.get("last_restart_ts"),
                "watchdog_enabled": state.data.get("watchdog_enabled"),
            }
    return snap
