# -*- coding: utf-8 -*-
"""Определение текущего экрана игры по скриншоту окна (1024x768).

Состояния: 'ingame' | 'menu' | 'login' | 'loading' | 'unknown'.
Работает по нескольким пиксельным пробам — грубо, но стабильно для этого UI.
"""
from PIL import Image


def _mean(img, box):
    """Средний (R,G,B) по прямоугольнику box=(l,t,r,b)."""
    c = img.crop(box).resize((1, 1))
    return c.getpixel((0, 0))[:3]


def _bright_frac(img, box, thr=170):
    """Доля «белых» пикселей (все каналы > thr) в box — детектор текста на тёмной плашке."""
    c = img.crop(box)
    px = c.getdata()
    n = len(px)
    if not n:
        return 0.0
    b = sum(1 for p in px if p[0] > thr and p[1] > thr and p[2] > thr)
    return b / n


def game_state(img_or_path):
    img = img_or_path if isinstance(img_or_path, Image.Image) else Image.open(img_or_path)
    img = img.convert("RGB")
    w, h = img.size
    # пробы рассчитаны на 1024x768; масштабируем, если размер иной
    sx, sy = w / 1024.0, h / 768.0

    def B(l, t, r, b):
        return (int(l * sx), int(t * sy), int(r * sx), int(b * sy))

    # 1) внутриигровой HUD: ярко-красная полоса HP слева сверху
    hp = _mean(img, B(40, 42, 190, 53))
    if hp[0] > 110 and hp[0] > hp[1] * 1.8 and hp[0] > hp[2] * 1.8:
        return "ingame"

    # 2) окно логина: светлое поле ввода логина + голубая кнопка Ok (проверять ДО loading —
    #    у диалога логина тоже есть белый текст по центру)
    field = _mean(img, B(390, 288, 635, 308))       # заполненное поле "Login"
    okbtn = _mean(img, B(445, 508, 580, 543))        # рамка кнопки Ok (циан)
    if min(field) > 95 or (okbtn[2] > 70 and okbtn[1] > 60 and okbtn[2] > okbtn[0] + 18):
        return "login"

    # 3) плашка загрузки: много белого текста по центру на тёмной плашке
    if _bright_frac(img, B(320, 300, 700, 470)) > 0.05:
        return "loading"

    # 4) главное меню: крупный циановый заголовок сверху
    title = _mean(img, B(300, 120, 720, 230))
    if title[1] > 70 and title[2] > 70 and title[1] > title[0] * 1.4:
        return "menu"

    return "unknown"


def is_checked(img_or_path, x, y, half=11):
    """Похоже ли, что чекбокс с центром (x,y) отмечен (синяя галочка)."""
    img = img_or_path if isinstance(img_or_path, Image.Image) else Image.open(img_or_path)
    img = img.convert("RGB")
    box = (x - half, y - half, x + half, y + half)
    c = img.crop(box)
    px = list(c.getdata())
    if not px:
        return False
    # галочка — насыщенный голубой: B высокий, B заметно больше R
    blue = sum(1 for p in px if p[2] > 110 and p[2] > p[0] + 30)
    return blue / len(px) > 0.12
