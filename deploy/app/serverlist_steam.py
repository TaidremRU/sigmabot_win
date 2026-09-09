# -*- coding: utf-8 -*-
"""Перечисление публичных Steam-лобби Sigma World Online.

Игра не регистрирует game-server'ы в мастер-листе Valve — вместо этого каждый
хост с включённой галкой «Show server in the public Steam list» создаёт
**публичное Steam-лобби** (``ISteamMatchmaking::CreateLobby``). Список лобби
доступен только клиентским вызовом ``RequestLobbyList`` из процесса с
инициализированным Steam API под appid игры — Web API для этого нет.

Скрипт запускается отдельным короткоживущим процессом (Steam на VM уже запущен и
залогинен), грузит ``steam_api64.dll`` из папки игры через ctypes, спрашивает
список лобби и печатает JSON в stdout:

    {"ok": true, "count": N, "lobbies": [
        {"id": "...", "owner": "...", "members": K, "data": {<lobby metadata>}}, ...]}

либо ``{"ok": false, "error": "..."}``. Ненулевой код возврата — при фатальной
ошибке (нет DLL / SteamAPI_Init провалился).

CLI: ``python serverlist_steam.py [--appid N] [--dll PATH] [--timeout SEC] [--raw]``
"""
import argparse
import ctypes as C
import json
import os
import sys
import time

DEFAULT_APPID = 1690980
DEFAULT_DLL = (
    r"C:\Program Files (x86)\Steam\steamapps\common\Sigma World Online"
    r"\SigmaWorld_Data\Plugins\x86_64\steam_api64.dll"
)
# k_iSteamMatchmakingCallbacks (500) + 10
LOBBY_MATCH_LIST_CALLBACK = 510
LOBBY_DISTANCE_WORLDWIDE = 3
MAX_KEY = 256
MAX_VAL = 8192
STEAM_ERRMSG_LEN = 1024  # typedef char SteamErrMsg[k_cchMaxSteamErrMsg]


class LobbyMatchList_t(C.Structure):
    _fields_ = [("m_nLobbiesMatching", C.c_uint32)]


def _bind(dll):
    """Проставить сигнатуры используемым функциям плоского API.

    steam_api64.dll игры — современный SDK: точки входа ``SteamAPI_Init`` нет,
    есть ``SteamAPI_InitFlat(SteamErrMsg*)`` -> ESteamAPIInitResult (0 = ок).
    """
    sigs = {
        "SteamAPI_InitFlat": ([C.c_char_p], C.c_int),
        "SteamAPI_Shutdown": ([], None),
        "SteamAPI_RunCallbacks": ([], None),
        "SteamAPI_GetHSteamUser": ([], C.c_int),
        "SteamInternal_FindOrCreateUserInterface": ([C.c_int, C.c_char_p], C.c_void_p),
        "SteamAPI_SteamMatchmaking_v009": ([], C.c_void_p),
        "SteamAPI_SteamUtils_v010": ([], C.c_void_p),
        "SteamAPI_ISteamUtils_IsAPICallCompleted":
            ([C.c_void_p, C.c_uint64, C.POINTER(C.c_bool)], C.c_bool),
        "SteamAPI_ISteamUtils_GetAPICallResult":
            ([C.c_void_p, C.c_uint64, C.c_void_p, C.c_int, C.c_int, C.POINTER(C.c_bool)], C.c_bool),
        "SteamAPI_ISteamMatchmaking_RequestLobbyList": ([C.c_void_p], C.c_uint64),
        "SteamAPI_ISteamMatchmaking_AddRequestLobbyListDistanceFilter": ([C.c_void_p, C.c_int], None),
        "SteamAPI_ISteamMatchmaking_AddRequestLobbyListResultCountFilter": ([C.c_void_p, C.c_int], None),
        "SteamAPI_ISteamMatchmaking_GetLobbyByIndex": ([C.c_void_p, C.c_int], C.c_uint64),
        "SteamAPI_ISteamMatchmaking_GetLobbyData": ([C.c_void_p, C.c_uint64, C.c_char_p], C.c_char_p),
        "SteamAPI_ISteamMatchmaking_GetLobbyDataCount": ([C.c_void_p, C.c_uint64], C.c_int),
        "SteamAPI_ISteamMatchmaking_GetLobbyDataByIndex":
            ([C.c_void_p, C.c_uint64, C.c_int, C.c_char_p, C.c_int, C.c_char_p, C.c_int], C.c_bool),
        "SteamAPI_ISteamMatchmaking_GetNumLobbyMembers": ([C.c_void_p, C.c_uint64], C.c_int),
        "SteamAPI_ISteamMatchmaking_GetLobbyOwner": ([C.c_void_p, C.c_uint64], C.c_uint64),
    }
    for name, (argtypes, restype) in sigs.items():
        fn = getattr(dll, name)
        fn.argtypes = argtypes
        fn.restype = restype
    return dll


def enumerate_lobbies(appid, dll_path, timeout):
    if not os.path.isfile(dll_path):
        return {"ok": False, "error": "steam_api64.dll not found: %s" % dll_path}

    os.environ["SteamAppId"] = str(appid)
    os.environ["SteamGameId"] = str(appid)
    game_dir = None
    p = dll_path
    for _ in range(4):
        p = os.path.dirname(p)
    if os.path.isfile(os.path.join(p, "steam_appid.txt")):
        game_dir = p
    if game_dir:
        os.chdir(game_dir)
    else:
        with open("steam_appid.txt", "w") as f:
            f.write(str(appid))

    try:
        dll = _bind(C.CDLL(dll_path))
    except OSError as e:
        return {"ok": False, "error": "load DLL: %s" % e}

    errbuf = C.create_string_buffer(STEAM_ERRMSG_LEN)
    rc = dll.SteamAPI_InitFlat(errbuf)
    if rc != 0:
        return {"ok": False, "error": "SteamAPI_InitFlat rc=%d: %s"
                % (rc, errbuf.value.decode("utf-8", "replace") or
                   "Steam не запущен / не залогинен / чужой appid")}

    try:
        mm = dll.SteamAPI_SteamMatchmaking_v009()
        utils = dll.SteamAPI_SteamUtils_v010()
        if not mm or not utils:
            huser = dll.SteamAPI_GetHSteamUser()
            mm = mm or dll.SteamInternal_FindOrCreateUserInterface(huser, b"SteamMatchMaking009")
            utils = utils or dll.SteamInternal_FindOrCreateUserInterface(huser, b"SteamUtils010")
        if not mm or not utils:
            return {"ok": False, "error": "нет интерфейса Matchmaking/Utils"}

        dll.SteamAPI_ISteamMatchmaking_AddRequestLobbyListDistanceFilter(mm, LOBBY_DISTANCE_WORLDWIDE)
        dll.SteamAPI_ISteamMatchmaking_AddRequestLobbyListResultCountFilter(mm, 200)
        hcall = dll.SteamAPI_ISteamMatchmaking_RequestLobbyList(mm)

        failed = C.c_bool(False)
        res = LobbyMatchList_t()
        deadline = time.time() + timeout
        done = False
        while time.time() < deadline:
            dll.SteamAPI_RunCallbacks()
            if dll.SteamAPI_ISteamUtils_IsAPICallCompleted(utils, hcall, C.byref(failed)):
                ok = dll.SteamAPI_ISteamUtils_GetAPICallResult(
                    utils, hcall, C.byref(res), C.sizeof(res),
                    LOBBY_MATCH_LIST_CALLBACK, C.byref(failed),
                )
                done = ok and not failed.value
                break
            time.sleep(0.1)
        if not done:
            return {"ok": False, "error": "RequestLobbyList: таймаут/ошибка (failed=%s)" % failed.value}

        n = res.m_nLobbiesMatching
        lobbies = []
        kbuf = C.create_string_buffer(MAX_KEY)
        vbuf = C.create_string_buffer(MAX_VAL)
        for i in range(n):
            lid = dll.SteamAPI_ISteamMatchmaking_GetLobbyByIndex(mm, i)
            if not lid:
                continue
            data = {}
            cnt = dll.SteamAPI_ISteamMatchmaking_GetLobbyDataCount(mm, lid)
            for j in range(cnt):
                if dll.SteamAPI_ISteamMatchmaking_GetLobbyDataByIndex(
                    mm, lid, j, kbuf, MAX_KEY, vbuf, MAX_VAL
                ):
                    data[kbuf.value.decode("utf-8", "replace")] = vbuf.value.decode("utf-8", "replace")
            owner = dll.SteamAPI_ISteamMatchmaking_GetLobbyOwner(mm, lid)
            lobbies.append({
                "id": str(lid),
                "owner": str(owner),
                "members": dll.SteamAPI_ISteamMatchmaking_GetNumLobbyMembers(mm, lid),
                "data": data,
            })
        return {"ok": True, "count": n, "lobbies": lobbies}
    finally:
        try:
            dll.SteamAPI_Shutdown()
        except Exception:  # noqa: BLE001
            pass


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--appid", type=int, default=DEFAULT_APPID)
    ap.add_argument("--dll", default=DEFAULT_DLL)
    ap.add_argument("--timeout", type=float, default=12.0)
    ap.add_argument("--raw", action="store_true", help="pretty-print (для отладки)")
    ap.add_argument("--out", help="писать JSON в этот файл (UTF-8), а не только в stdout")
    a = ap.parse_args(argv)
    try:
        out = enumerate_lobbies(a.appid, a.dll, a.timeout)
    except Exception as e:  # noqa: BLE001
        out = {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}
    text = json.dumps(out, ensure_ascii=False, indent=2 if a.raw else None)
    if a.out:
        try:
            with open(a.out, "w", encoding="utf-8") as f:
                f.write(text + "\n")
        except Exception as e:  # noqa: BLE001
            sys.stderr.write("cannot write --out: %s\n" % e)
    sys.stdout.write(text + "\n")
    return 0 if out.get("ok") else 2


if __name__ == "__main__":
    sys.exit(main())
