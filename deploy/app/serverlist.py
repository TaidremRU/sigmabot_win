# -*- coding: utf-8 -*-
"""Список публичных серверов Sigma World Online для бота.

Игра не регистрирует game-server'ы в мастер-листе Valve — каждый публичный хост
создаёт **Steam-лобби** (``ISteamMatchmaking::CreateLobby``). Поэтому:

* **Основной источник** — перечисление Steam-лобби на VM: ``serverlist_steam.py``
  запускается отдельным дочерним процессом (Steam-IPC живёт в консольной сессии,
  где и работает супервизор, поэтому обычного ``subprocess`` достаточно —
  отдельная задача планировщика, как для ``nav.py``, не нужна).
* **Запасной слой** — Steam Web API ``IGameServersService/GetServerList`` (на
  случай, если игра когда-нибудь начнёт публиковать настоящие серверы). Требует
  ``steam_web_api_key`` в ``config.json``.

``fetch(cfg)`` -> ``(ok, servers | errmsg, source)``, где ``source`` —
``"lobbies"`` | ``"webapi"`` | ``"none"``; ``servers`` — список словарей единой
формы: ``name``, ``addr``, ``players``, ``max_players``, ``map``, ``version``,
``members`` (только для лобби, иначе ``None``).
"""
import json
import logging
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

_API = "https://api.steampowered.com/IGameServersService/GetServerList/v1/"


def _int(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return 0


def _python_exe(cfg):
    exe = (cfg.get("python_exe") or "").strip()
    if exe and os.path.isfile(exe):
        return exe
    cand = sys.executable or ""
    # супервизор идёт под pythonw.exe — для дочернего скрипта берём python.exe
    if cand.lower().endswith("pythonw.exe"):
        alt = cand[:-len("pythonw.exe")] + "python.exe"
        if os.path.isfile(alt):
            return alt
    return cand or "python"


def _script_path(cfg):
    here = os.path.dirname(os.path.abspath(__file__))
    for base in (cfg.get("base_dir"), here):
        if base:
            p = os.path.join(base, "serverlist_steam.py")
            if os.path.isfile(p):
                return p
    return os.path.join(here, "serverlist_steam.py")


def from_lobbies(cfg, timeout=35):
    """Запустить serverlist_steam.py, вернуть ``(ok, servers | errmsg)``."""
    script = _script_path(cfg)
    if not os.path.isfile(script):
        return False, "serverlist_steam.py не найден"
    cmd = [_python_exe(cfg), script,
           "--appid", str(cfg.get("game_appid", 1690980)), "--timeout", "20"]
    dll = (cfg.get("steam_api_dll") or "").strip()
    if dll:
        cmd += ["--dll", dll]
    # не мигать консольным окном при запуске из pythonw (монитор дёргает раз в 5 мин)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout, creationflags=flags)
    except subprocess.TimeoutExpired:
        return False, "enumerator: таймаут"
    except Exception as e:  # noqa: BLE001
        return False, "enumerator: %s" % e
    out = (r.stdout or b"").decode("utf-8", "replace").strip()
    err = (r.stderr or b"").decode("utf-8", "replace").strip()
    try:
        data = json.loads(out.splitlines()[-1]) if out else {}
    except Exception:  # noqa: BLE001
        return False, "enumerator: неразборный вывод (%s)" % ((out or err)[:180])
    if not data.get("ok"):
        return False, data.get("error") or "enumerator: неизвестная ошибка"
    servers = []
    for lb in data.get("lobbies", []):
        d = lb.get("data", {}) or {}
        servers.append({
            "name": d.get("server_name") or d.get("world_name") or ("lobby " + str(lb.get("id", "?"))),
            "addr": "lobby:" + str(lb.get("id", "?")),
            "players": _int(d.get("players")),
            "max_players": _int(d.get("max_players")),
            "map": d.get("world_name") or "",
            "version": d.get("build") or d.get("version") or "",
            "members": lb.get("members"),
        })
    return True, servers


def from_webapi(cfg, timeout=15):
    key = (cfg.get("steam_web_api_key") or "").strip()
    if not key:
        return False, "нет steam_web_api_key"
    flt = r"\appid\%d" % cfg.get("game_appid", 1690980)
    qs = urllib.parse.urlencode({"key": key, "filter": flt, "limit": 5000})
    try:
        with urllib.request.urlopen(_API + "?" + qs, timeout=timeout) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        return False, "Web API http %s" % e.code
    except Exception as e:  # noqa: BLE001
        return False, "Web API: %s" % e
    servers = []
    for s in (data.get("response", {}).get("servers") or []):
        servers.append({
            "name": s.get("name") or "?",
            "addr": s.get("addr") or "?",
            "players": _int(s.get("players")),
            "max_players": _int(s.get("max_players")),
            "map": s.get("map") or "",
            "version": s.get("version") or "",
            "members": None,
        })
    return True, servers


def fetch(cfg):
    ok, res = from_lobbies(cfg)
    if ok:
        return True, res, "lobbies"
    logging.info("serverlist: лобби недоступны (%s) — пробую Web API", res)
    lobby_err = res
    ok2, res2 = from_webapi(cfg)
    if ok2:
        return True, res2, "webapi"
    return False, "%s; %s" % (lobby_err, res2), "none"
