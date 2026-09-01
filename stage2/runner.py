# -*- coding: utf-8 -*-
"""Запуск nav.py через задачу планировщика SigmaNav.

Фоновый поток супервизора не может получить фокус окна игры (SetForegroundWindow
не работает без прав на передний план), а процесс, запущенный планировщиком в
интерактивной сессии, — может. Поэтому UI-последовательности гоняем так.
"""
import logging
import os
import subprocess
import threading
import time

import common

BASE = common.BASE_DIR
CMD_FILE = os.path.join(BASE, "nav_cmd.txt")
OUT_FILE = os.path.join(BASE, "nav_out.txt")
TASK = "SigmaNav"

_lock = threading.Lock()
_BUSY_MARKERS = ("Running", "Выполняется", "Работает", "выполняется")


def _task_running():
    try:
        q = subprocess.run(["schtasks", "/query", "/tn", TASK], capture_output=True, timeout=15)
    except Exception:  # noqa: BLE001
        return False
    txt = q.stdout.decode("cp866", "replace") + q.stdout.decode("utf-8", "replace")
    return any(m in txt for m in _BUSY_MARKERS)


def run_nav(args, timeout=260):
    """Синхронно выполнить `nav.py <args>` через SigmaNav. Возвращает (ok, output)."""
    with _lock:
        try:
            os.remove(OUT_FILE)
        except OSError:
            pass
        with open(CMD_FILE, "w", encoding="ascii", errors="replace") as f:
            f.write(args.strip())

        try:
            subprocess.run(["schtasks", "/run", "/tn", TASK], capture_output=True, timeout=30)
        except Exception as e:  # noqa: BLE001
            return False, "не удалось запустить задачу %s: %s" % (TASK, e)

        time.sleep(4)
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not _task_running() and os.path.exists(OUT_FILE):
                time.sleep(1)
                break
            time.sleep(3)

        out = ""
        try:
            with open(OUT_FILE, "r", encoding="utf-8", errors="replace") as f:
                out = f.read()
        except OSError:
            pass
        ok = ("итог = ingame" in out) or ("do_seq: итог = ingame" in out) or ("-> OK" in out)
        logging.info("runner '%s' ok=%s\n%s", args, ok, out[-1800:])
        return ok, out
