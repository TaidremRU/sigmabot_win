# -*- coding: utf-8 -*-
"""Telegram-бот управления (long polling через SOCKS5-прокси)."""
import datetime
import html
import logging
import os
import queue
import threading
import time

import common
import gamectl
import screenshot
import sysinfo


def _fmt_bytes(n):
    if n is None:
        return "—"
    n = float(n)
    for u in ("Б", "КБ", "МБ", "ГБ", "ТБ"):
        if n < 1024:
            return ("%.0f %s" % (n, u)) if u == "Б" else ("%.1f %s" % (n, u))
        n /= 1024
    return "%.1f ПБ" % n


def _fmt_dur(s):
    if s is None:
        return "—"
    s = int(s)
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    if d:
        return "%dд %dч %dм" % (d, h, m)
    if h:
        return "%dч %dм" % (h, m)
    if m:
        return "%dм %dс" % (m, s)
    return "%dс" % s


MENU = {
    "inline_keyboard": [
        [{"text": "📊 Статус", "callback_data": "act:status"},
         {"text": "📷 Скрин", "callback_data": "act:shot"}],
        [{"text": "▶️ Запустить игру", "callback_data": "act:game_start"},
         {"text": "⏹ Остановить игру", "callback_data": "act:game_stop"}],
        [{"text": "🎮 Войти в игру", "callback_data": "act:login"},
         {"text": "🔄 Перезапуск игры", "callback_data": "act:game_restart"}],
        [{"text": "♻️ Перезапуск Steam", "callback_data": "act:steam_restart"}],
        [{"text": "🐕 Watchdog вкл/выкл", "callback_data": "act:wd_toggle"},
         {"text": "🖥 Перезагрузить VM", "callback_data": "act:vm_restart"}],
        [{"text": "⛔ Остановить бота", "callback_data": "act:bot_stop"}],
    ]
}

CONFIRM_VM = {
    "inline_keyboard": [[
        {"text": "✅ Да, перезагрузить", "callback_data": "act:vm_yes"},
        {"text": "❌ Отмена", "callback_data": "act:vm_no"},
    ]]
}

CONFIRM_STOP = {
    "inline_keyboard": [[
        {"text": "⛔ Да, остановить", "callback_data": "act:bot_stop_yes"},
        {"text": "❌ Отмена", "callback_data": "act:bot_stop_no"},
    ]]
}

STOP_PROMPT = (
    "⛔ Остановить SigmaSteamBot?\n"
    "Скрипт выключится и <b>сам не перезапустится</b> (ни авто-рестартом, ни при "
    "перезагрузке VM). Игра и Steam останутся работать. Вернуть — только с VM "
    "через SSH/RDP."
)


class Bot:
    def __init__(self, cfg, state, watchdog_ref=None):
        self.cfg = cfg
        self.state = state
        self.wd = watchdog_ref
        tg = cfg["telegram"]
        self.allowed = set(tg["allowed_user_ids"])
        self.tg = common.Telegram(tg["token"], tg["proxy"], tg.get("poll_timeout", 50))
        self.alerts_enabled = tg.get("alerts_enabled", True)
        self._offset = 0
        self._stop = threading.Event()
        self._outbox = queue.Queue()  # алерты уходят сюда, шлёт отдельный поток

    # ---------- отправка из любого потока (НЕ блокирует вызывающего) ----------
    def push_alert(self, text):
        if self.alerts_enabled:
            self._outbox.put(text)

    def _sender_loop(self):
        while not self._stop.is_set():
            try:
                text = self._outbox.get(timeout=1.0)
            except queue.Empty:
                continue
            for uid in self.allowed:
                try:
                    self.tg.send_message(uid, text)
                except Exception:  # noqa: BLE001
                    logging.exception("sender: не удалось отправить алерт")

    def notify_startup(self):
        try:
            snap = sysinfo.collect(self.cfg, self.state)
        except Exception:  # noqa: BLE001
            snap = None
        head = "🟢 <b>SigmaSteamBot запущен</b>"
        if snap and snap["uptime_seconds"] < 300:
            head = "✅ <b>VM снова в сети</b> (после перезагрузки)"
        body = ("\n" + self._status_text(snap)) if snap else ""
        self.push_alert(head + body)

    # ---------- основной цикл ----------
    def run(self):
        logging.info("bot: старт")
        threading.Thread(target=self._sender_loop, name="sender", daemon=True).start()
        r = self.tg.get_updates(0, 0)
        if r.get("ok") and r.get("result"):
            self._offset = r["result"][-1]["update_id"] + 1
        self.notify_startup()
        timeout = self.cfg["telegram"].get("poll_timeout", 50)
        while not self._stop.is_set():
            try:
                r = self.tg.get_updates(self._offset, timeout)
                if not r.get("ok"):
                    logging.warning("getUpdates: %s", r.get("error") or r.get("description") or r)
                    time.sleep(8)
                    continue
                for upd in r.get("result", []):
                    self._offset = upd["update_id"] + 1
                    try:
                        self._handle(upd)
                    except Exception:  # noqa: BLE001
                        logging.exception("handle update error")
            except Exception:  # noqa: BLE001
                logging.exception("poll loop error")
                time.sleep(8)

    def stop(self):
        self._stop.set()

    # ---------- обработка ----------
    def _auth(self, uid):
        return uid in self.allowed

    def _handle(self, upd):
        if "message" in upd:
            msg = upd["message"]
            uid = msg.get("from", {}).get("id")
            text = (msg.get("text") or "").strip()
            chat = msg["chat"]["id"]
            if not self._auth(uid):
                if text.startswith("/start"):
                    self.tg.send_message(
                        chat,
                        "Ваш Telegram ID: <code>%s</code>\nДоступ запрещён — добавьте ID в config.json." % uid,
                    )
                return
            self._command(chat, text)
        elif "callback_query" in upd:
            cq = upd["callback_query"]
            uid = cq.get("from", {}).get("id")
            data = cq.get("data", "")
            chat = cq["message"]["chat"]["id"]
            if not self._auth(uid):
                self.tg.answer_callback(cq["id"], "Доступ запрещён")
                return
            self.tg.answer_callback(cq["id"])
            self._action(chat, data.split(":", 1)[1] if ":" in data else data)

    def _command(self, chat, text):
        parts = text.split()
        cmd = parts[0].lower().lstrip("/").split("@")[0] if parts else ""
        arg = parts[1].lower() if len(parts) > 1 else ""
        if cmd in ("start", "help", "menu"):
            self.tg.send_message(chat, self._help_text(), MENU)
        elif cmd == "status":
            self.tg.send_message(chat, self._status_text(), MENU)
        elif cmd == "shot":
            self._do_shot(chat)
        elif cmd == "startgame":
            self._async(chat, "▶️ Запускаю игру…", lambda: gamectl.start_game(self.cfg))
        elif cmd == "stopgame":
            self._async(chat, "⏹ Останавливаю игру…", lambda: gamectl.stop_game(self.cfg))
        elif cmd == "restartgame":
            self._async(chat, "🔄 Перезапускаю игру…", lambda: gamectl.restart_game(self.cfg))
        elif cmd == "restartsteam":
            self._async(chat, "♻️ Перезапускаю Steam…", lambda: gamectl.restart_steam(self.cfg))
        elif cmd == "login":
            self._async(chat, "🎮 Прохожу вход в игру…", self._do_login, shot_after=True)
        elif cmd == "restartvm":
            self.tg.send_message(chat, "⚠️ Перезагрузить VM? Steam и игра будут закрыты.", CONFIRM_VM)
        elif cmd in ("stopbot", "stop"):
            self.tg.send_message(chat, STOP_PROMPT, CONFIRM_STOP)
        elif cmd == "watchdog":
            if arg in ("on", "off") and self.wd:
                self.wd.set_enabled(arg == "on")
            st = "включён" if (self.wd and self.wd.enabled) else "выключен"
            self.tg.send_message(chat, "🐕 Watchdog сейчас <b>%s</b>." % st, MENU)
        else:
            self.tg.send_message(chat, "Не понял. /help", MENU)

    def _action(self, chat, act):
        if act == "status":
            self.tg.send_message(chat, self._status_text(), MENU)
        elif act == "shot":
            self._do_shot(chat)
        elif act == "game_start":
            self._async(chat, "▶️ Запускаю игру…", lambda: gamectl.start_game(self.cfg))
        elif act == "game_stop":
            self._async(chat, "⏹ Останавливаю игру…", lambda: gamectl.stop_game(self.cfg))
        elif act == "game_restart":
            self._async(chat, "🔄 Перезапускаю игру…", lambda: gamectl.restart_game(self.cfg))
        elif act == "steam_restart":
            self._async(chat, "♻️ Перезапускаю Steam…", lambda: gamectl.restart_steam(self.cfg))
        elif act == "login":
            self._async(chat, "🎮 Прохожу вход в игру…", self._do_login, shot_after=True)
        elif act == "wd_toggle":
            if self.wd:
                self.wd.set_enabled(not self.wd.enabled)
                self.tg.send_message(
                    chat,
                    "🐕 Watchdog теперь <b>%s</b>." % ("включён" if self.wd.enabled else "выключен"),
                    MENU,
                )
        elif act == "vm_restart":
            self.tg.send_message(chat, "⚠️ Перезагрузить VM?", CONFIRM_VM)
        elif act == "vm_yes":
            self.push_alert("🖥 Перезагрузка VM по команде из Telegram…")
            ok, msg = gamectl.restart_vm()
            if not ok:
                self.tg.send_message(chat, "🔴 Не удалось: %s" % html.escape(str(msg)))
        elif act == "vm_no":
            self.tg.send_message(chat, "Отменено.", MENU)
        elif act == "bot_stop":
            self.tg.send_message(chat, STOP_PROMPT, CONFIRM_STOP)
        elif act == "bot_stop_yes":
            self._do_stop_bot(chat)
        elif act == "bot_stop_no":
            self.tg.send_message(chat, "Отменено.", MENU)

    def _async(self, chat, wait_text, fn, shot_after=False):
        self.tg.send_message(chat, wait_text)

        def worker():
            try:
                ok, msg = fn()
                self.tg.send_message(
                    chat,
                    ("✅ " if ok else "🔴 ") + html.escape(str(msg)) + "\n\n" + self._status_text(),
                    MENU,
                )
                if shot_after:
                    self._do_shot(chat)
            except Exception as e:  # noqa: BLE001
                logging.exception("action error")
                self.tg.send_message(chat, "🔴 Ошибка: %s" % html.escape(str(e)))

        threading.Thread(target=worker, name="action", daemon=True).start()

    def _do_login(self):
        try:
            import runner

            ok, out = runner.run_nav("seq login", timeout=280)
        except Exception as e:  # noqa: BLE001
            logging.exception("login sequence error")
            return False, "ошибка последовательности: %s" % e
        tail = [ln for ln in out.strip().splitlines() if ln.strip()][-3:]
        suffix = ("\n<code>%s</code>" % html.escape("\n".join(tail))) if tail else ""
        return ok, ("вошёл в игру" if ok else "последовательность не довершена") + suffix

    def _do_stop_bot(self, chat):
        """Отключить задачу планировщика и завершить супервизор.

        Выполняется прямо в цикле опроса, поэтому сообщения шлём синхронно (через
        _outbox не успеют уйти до выхода процесса).
        """
        self.tg.send_message(chat, "⛔ Останавливаю бота…")
        task = self.cfg.get("task_name", "SigmaSteamBot")
        ok, msg = gamectl.disable_bot_task(task)
        logging.info("bot: /stopbot из Telegram, disable %s ok=%s (%s)", task, ok, msg)
        if ok:
            txt = (
                "🛑 <b>SigmaSteamBot остановлен.</b>\n"
                "Задача <code>%s</code> отключена — авто-рестарта не будет.\n\n"
                "Запуск снова (на VM):\n"
                "<code>Enable-ScheduledTask -TaskName %s; Start-ScheduledTask -TaskName %s</code>"
                % (task, task, task)
            )
        else:
            txt = (
                "⚠️ Процесс завершаю, но задачу <code>%s</code> отключить не вышло:\n"
                "<code>%s</code>\n"
                "Планировщик поднимет бота снова в течение ~2 минут — отключите задачу вручную."
                % (task, html.escape(str(msg)))
            )
        self.tg.send_message(chat, txt)
        if self.wd:
            try:
                self.wd.stop()
            except Exception:  # noqa: BLE001
                logging.exception("stop: не удалось остановить watchdog")
        self.stop()

    def _do_shot(self, chat):
        path = os.path.join(self.cfg["base_dir"], "logs", "shot.png")
        hwnd = None
        try:
            procs = sysinfo.find_procs(["sigmaworld.exe"], self.cfg.get("game_install_dir"))
            if procs:
                hwnd = screenshot.find_game_window([p.pid for p in procs])
        except Exception:  # noqa: BLE001
            logging.exception("shot: поиск окна игры")
        try:
            method, size = screenshot.capture(path, hwnd)
        except Exception as e:  # noqa: BLE001
            logging.exception("shot: захват не удался")
            self.tg.send_message(chat, "🔴 Не удалось снять экран:\n<code>%s</code>" % html.escape(str(e)))
            return
        cap = "Экран VM • %s • %sx%s • %s" % (
            method, size[0], size[1], datetime.datetime.now().strftime("%H:%M:%S"),
        )
        r = self.tg.send_photo(chat, path, cap)
        if not r.get("ok"):
            self.tg.send_message(
                chat, "🔴 Отправка не удалась: %s" % html.escape(str(r.get("error") or r.get("description")))
            )

    def _help_text(self):
        return (
            "<b>SigmaSteamBot</b> — управление игрой Sigma World Online на VM\n\n"
            "/status — состояние VM, Steam и игры\n"
            "/shot — скриншот экрана\n"
            "/startgame · /stopgame · /restartgame\n"
            "/login — пройти вход в игру (Game→Local→Steam→Play→Ok)\n"
            "/restartsteam — перезапуск Steam\n"
            "/restartvm — перезагрузка VM (с подтверждением)\n"
            "/watchdog on|off — авто-поддержание игры\n"
            "/stopbot — остановить сам скрипт (с подтверждением; запуск обратно — только с VM)\n\n"
            "Ниже — кнопки для того же самого."
        )

    def _status_text(self, snap=None):
        if snap is None:
            try:
                snap = sysinfo.collect(self.cfg, self.state)
            except Exception as e:  # noqa: BLE001
                return "🔴 Не удалось собрать статус: %s" % html.escape(str(e))
        g = snap["game"]
        s = snap["steam"]
        out = []
        out.append("🖥 <b>VM</b> • аптайм %s" % _fmt_dur(snap["uptime_seconds"]))
        out.append(
            "   CPU %.0f%% (%s ядер) • RAM %.0f%% (%s / %s) • C: своб. %s (%.0f%% занято)"
            % (
                snap["cpu_percent"], snap["cpu_count"] or "?", snap["mem"]["percent"],
                _fmt_bytes(snap["mem"]["used"]), _fmt_bytes(snap["mem"]["total"]),
                _fmt_bytes(snap["disk_c"]["free"]), snap["disk_c"]["percent"],
            )
        )
        sess = (
            "RDP подключён" if snap["rdp_connected"]
            else ("консоль активна" if snap["console_active"] else "нет активной сессии")
        )
        out.append("   Сессия: %s" % sess)

        li = {True: "вошёл в аккаунт", False: "НЕ вошёл", None: "?"}[s["logged_in"]]
        out.append(
            "\n🎮 <b>Steam</b>: %s • %s • %s"
            % (
                "🟢 работает" if s["running"] else "🔴 не запущен",
                html.escape(s["account"] or "?"),
                li,
            )
        )

        if g["running"]:
            ls = {"done": "в игре ✅", "running": "вход выполняется…", "idle": "в меню"}.get(
                self.state.data.get("login_state"), "?"
            )
            out.append(
                "🕹 <b>Игра</b>: 🟢 работает • %s • PID %s • %s • RAM %s • CPU %.0f%%"
                % (ls, g.get("pid"), _fmt_dur(g.get("run_seconds")), _fmt_bytes(g.get("rss")), g.get("cpu") or 0)
            )
            extra = []
            if g.get("window_title"):
                extra.append("окно: «%s»" % html.escape(g["window_title"]))
            if g.get("minimized"):
                extra.append("свёрнуто")
            if g.get("responding") is False:
                extra.append("⚠️ не отвечает")
            if extra:
                out.append("   " + " • ".join(extra))
        else:
            out.append("🕹 <b>Игра</b>: 🔴 не запущена")

        c = snap.get("counters", {})
        wd_on = self.wd.enabled if self.wd else c.get("watchdog_enabled")
        out.append(
            "\n🐕 Watchdog: %s • перезапусков с загрузки: игра %s / Steam %s"
            % (
                "вкл" if wd_on else "выкл",
                c.get("game_restarts", 0),
                c.get("steam_restarts", 0),
            )
        )
        if c.get("last_restart_ts"):
            out.append(
                "   последний перезапуск: %s"
                % datetime.datetime.fromtimestamp(c["last_restart_ts"]).strftime("%d.%m %H:%M:%S")
            )
        return "\n".join(out)
