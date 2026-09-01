# -*- coding: utf-8 -*-
"""Быстрая проверка модулей без запуска бесконечного цикла."""
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import common
import gamectl
import sysinfo
from bot import Bot
from watchdog import Watchdog  # noqa: F401

cfg = common.load_config()
print("config OK:", cfg["game_name"], "appid", cfg["game_appid"])

print("steam_running:", gamectl.steam_running())
print("game_running :", gamectl.game_running(cfg))

snap = sysinfo.collect(cfg)
print("snapshot keys:", sorted(snap.keys()))
print("cpu%%=%s mem%%=%s disk_free=%s rdp=%s console_active=%s"
      % (snap["cpu_percent"], snap["mem"]["percent"], snap["disk_c"]["free"],
         snap["rdp_connected"], snap["console_active"]))
print("steam:", snap["steam"])
print("game :", snap["game"])
print("sessions:", snap["sessions"])

b = Bot(cfg, common.State("state.json"))
print("--- status text ---")
print(b._status_text(snap))

print("--- telegram getUpdates via proxy ---")
r = b.tg.get_updates(0, 0)
print("ok=%s err=%s n=%s" % (r.get("ok"), r.get("error"), len(r.get("result", []) or [])))
sys.exit(0 if r.get("ok") else 1)
