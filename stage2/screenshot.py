# -*- coding: utf-8 -*-
"""Захват экрана / окна игры несколькими способами (для /shot).

Порядок попыток:
  1. PrintWindow по окну игры  — работает даже если RDP-сессия свёрнута/простаивает;
  2. PrintWindow по рабочему столу;
  3. PIL.ImageGrab.grab()       — обычный BitBlt дисплея.

Перед захватом процесс/поток принудительно привязывается к WinSta0\\Default —
иначе фоновый процесс (запущенный не из интерактивной сессии) не видит рабочий стол.
"""
import ctypes
import logging
from ctypes import wintypes

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32

MAXIMUM_ALLOWED = 0x02000000
GWL_STYLE = -16
WS_VISIBLE = 0x10000000


def attach_input_desktop():
    """Привязать процесс к WinSta0 и поток к рабочему столу Default. Тихо игнорирует ошибки."""
    try:
        hwinsta = _user32.OpenWindowStationW("WinSta0", False, MAXIMUM_ALLOWED)
        if hwinsta:
            _user32.SetProcessWindowStation(hwinsta)
        for name in ("Default", "Winlogon"):
            hdesk = _user32.OpenDesktopW(name, 0, False, MAXIMUM_ALLOWED)
            if hdesk and _user32.SetThreadDesktop(hdesk):
                return name
        return None
    except Exception as e:  # noqa: BLE001
        logging.debug("attach_input_desktop: %s", e)
        return None


def enum_windows_for_pid(pid):
    """Список (hwnd, class, title, visible, (w,h)) всех окон процесса."""
    res = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):
        p = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value != pid:
            return True
        cls = ctypes.create_unicode_buffer(256)
        _user32.GetClassNameW(hwnd, cls, 256)
        n = _user32.GetWindowTextLengthW(hwnd)
        title = ""
        if n:
            b = ctypes.create_unicode_buffer(n + 1)
            _user32.GetWindowTextW(hwnd, b, n + 1)
            title = b.value
        r = wintypes.RECT()
        _user32.GetWindowRect(hwnd, ctypes.byref(r))
        style = _user32.GetWindowLongW(hwnd, GWL_STYLE)
        vis = bool(_user32.IsWindowVisible(hwnd)) or bool(style & WS_VISIBLE)
        res.append((hwnd, cls.value, title, vis, (r.right - r.left, r.bottom - r.top)))
        return True

    _user32.EnumWindows(cb, 0)
    return res


def find_game_window(pids):
    """hwnd самого большого подходящего окна среди процессов игры (Unity / с заголовком).

    pids — int или итерируемое из int (у игры бывает несколько процессов, окно — не у первого).
    """
    if isinstance(pids, int):
        pids = [pids]
    best, best_area = None, 0
    for pid in pids:
        for hwnd, cls, title, vis, (w, h) in enum_windows_for_pid(pid):
            if not vis or w < 100 or h < 100:
                continue
            if "Unity" in cls or title:
                if w * h > best_area:
                    best, best_area = hwnd, w * h
    return best


def _pw_capture(hwnd, path, flags, client=False):
    import win32gui
    import win32ui
    from PIL import Image

    if client:
        _l, _t, w, h = win32gui.GetClientRect(hwnd)
        flags |= 1  # PW_CLIENTONLY
        hwnd_dc = win32gui.GetDC(hwnd)
    else:
        l, t, r, b = win32gui.GetWindowRect(hwnd)
        w, h = r - l, b - t
        hwnd_dc = win32gui.GetWindowDC(hwnd)
    if w <= 0 or h <= 0:
        raise OSError("нулевой размер окна %dx%d" % (w, h))

    mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
    save_dc = mfc_dc.CreateCompatibleDC()
    bmp = win32ui.CreateBitmap()
    bmp.CreateCompatibleBitmap(mfc_dc, w, h)
    save_dc.SelectObject(bmp)
    try:
        ok = _user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), flags)
        info = bmp.GetInfo()
        bits = bmp.GetBitmapBits(True)
    finally:
        win32gui.DeleteObject(bmp.GetHandle())
        save_dc.DeleteDC()
        mfc_dc.DeleteDC()
        win32gui.ReleaseDC(hwnd, hwnd_dc)

    if not ok:
        raise OSError("PrintWindow вернул 0")
    img = Image.frombuffer("RGB", (info["bmWidth"], info["bmHeight"]), bits, "raw", "BGRX", 0, 1)
    if img.getbbox() is None:
        raise OSError("кадр полностью чёрный")
    img.save(path)
    return img.size


def _imagegrab(path):
    from PIL import ImageGrab

    im = ImageGrab.grab(all_screens=True)
    im.save(path)
    return im.size


def capture(path, game_hwnd=None):
    """Вернёт (method, (w, h)). Бросит OSError со списком ошибок, если ничего не вышло.

    Для окна игры снимается КЛИЕНТСКАЯ область (без рамки/заголовка) — тогда пиксель
    кадра == клиентская координата, и клики через ClientToScreen попадают точно.
    """
    attach_input_desktop()
    errors = []

    if game_hwnd:
        for flags, tag in ((2, "game-window[full]"), (0, "game-window")):
            try:
                return tag, _pw_capture(game_hwnd, path, flags)
            except Exception as e:  # noqa: BLE001
                errors.append("%s: %s" % (tag, e))

    try:
        desk = _user32.GetDesktopWindow()
        return "desktop-printwindow", _pw_capture(desk, path, 2)
    except Exception as e:  # noqa: BLE001
        errors.append("desktop-printwindow: %s" % e)

    try:
        return "imagegrab", _imagegrab(path)
    except Exception as e:  # noqa: BLE001
        errors.append("imagegrab: %s" % e)

    logging.warning("screenshot: все способы не сработали — %s", "; ".join(errors))
    raise OSError("; ".join(errors))


if __name__ == "__main__":  # ручной тест / диагностика
    import sys

    import common
    import sysinfo

    cfg = common.load_config()
    out = sys.argv[1] if len(sys.argv) > 1 else "shot_test.png"

    print("attach_input_desktop ->", attach_input_desktop())
    wsbuf = ctypes.create_unicode_buffer(256)
    hws = _user32.GetProcessWindowStation()
    needed = wintypes.DWORD()
    _user32.GetUserObjectInformationW(hws, 2, wsbuf, 256, ctypes.byref(needed))
    print("window station:", wsbuf.value)

    procs = sysinfo.find_procs(["sigmaworld.exe"], cfg.get("game_install_dir"))
    pids = [p.pid for p in procs]
    print("game pids:", pids)
    for pid in pids:
        for row in enum_windows_for_pid(pid):
            print("  win pid=%d:" % pid, row)
    hwnd = find_game_window(pids) if pids else None
    print("chosen hwnd:", hwnd)

    try:
        m, sz = capture(out, hwnd)
        print("OK method=%s size=%s -> %s" % (m, sz, out))
    except Exception as e:  # noqa: BLE001
        print("FAIL:", e)
        sys.exit(1)
