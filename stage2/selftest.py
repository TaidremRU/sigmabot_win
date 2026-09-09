# -*- coding: utf-8 -*-
"""Быстрая проверка модулей без запуска бесконечного цикла."""
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import common
import gamectl
import i18n
import serverlist
import serverlist_steam  # noqa: F401  (проверка, что модуль импортируется)
import sysinfo
from bot import Bot
from watchdog import Watchdog  # noqa: F401

cfg = common.load_config()
print("config OK:", cfg["game_name"], "appid", cfg["game_appid"])

_ru, _en = set(i18n.L["ru"]), set(i18n.L["en"])
assert _ru == _en, "i18n: расхождение ключей ru/en: %s" % (_ru ^ _en)
print("i18n OK:", len(_ru), "ключей x", len(i18n.SUPPORTED), "языка")

tg = cfg["telegram"]
print("роли: админов %d, модераторов %d, super_admin=%s, default_lang=%s"
      % (len(tg.get("allowed_user_ids", [])),
         len(tg.get("moderator_user_ids", [])),
         tg.get("super_admin_id"), tg.get("default_lang", "ru")))

_mon = cfg.get("monitor", {}) or {}
print("монитор сервера: enabled=%s name=%r interval=%ss misses=%s repeat=%ss"
      % (_mon.get("enabled", True), _mon.get("server_name", "AstralSigma"),
         _mon.get("interval_seconds", 300), _mon.get("misses_before_alert", 2),
         _mon.get("repeat_alert_seconds", 3600)))

print("steam_running:", gamectl.steam_running())
print("game_running :", gamectl.game_running(cfg))

try:
    _sok, _sres, _ssrc = serverlist.fetch(cfg)
    print("serverlist   : ok=%s source=%s -> %s"
          % (_sok, _ssrc, (("%d серв." % len(_sres)) if _sok else _sres)))
except Exception as _e:  # noqa: BLE001
    print("serverlist   : ОШИБКА", _e)

snap = sysinfo.collect(cfg)
print("snapshot keys:", sorted(snap.keys()))
print("cpu%%=%s mem%%=%s disk_free=%s rdp=%s console_active=%s"
      % (snap["cpu_percent"], snap["mem"]["percent"], snap["disk_c"]["free"],
         snap["rdp_connected"], snap["console_active"]))
print("steam:", snap["steam"])
print("game :", snap["game"])
print("sessions:", snap["sessions"])

b = Bot(cfg, common.State("state.json"))
print("--- status text (ru / en) ---")
print(b._status_text(snap, "ru"))
print("- - -")
print(b._status_text(snap, "en"))
print("--- меню (admin / moderator) ---")
for _role in ("admin", "moderator"):
    _lbl = [x["text"] for row in b._menu("ru", _role)["inline_keyboard"] for x in row]
    print(" ", _role, "→", " | ".join(_lbl))

print("--- telegram getUpdates via proxy ---")
r = b.tg.get_updates(0, 0)
print("ok=%s err=%s n=%s" % (r.get("ok"), r.get("error"), len(r.get("result", []) or [])))
sys.exit(0 if r.get("ok") else 1)
