# -*- coding: utf-8 -*-
"""Проверка шрифта: печатает глифы в консоль и рисует таблицу в PNG.

Запуск: .venv/bin/python tools/probe_font.py [файл.png]
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import pygame
import pixel_font as pf


def dump():
    rows = "".join(sorted(pf.GLYPHS.keys()))
    print("глифов:", len(pf.GLYPHS))
    print("набор:", rows)
    missing = []
    for ch in rows:
        if len(pf.glyph(ch)) != pf.H or any(len(r) != pf.W for r in pf.glyph(ch)):
            missing.append(ch)
    print("битые глифы:", missing or "нет")
    # что превращается в '?'
    bad = []
    for ch in ("А", "Я", "Ж", "Щ", "Ы", "Ю", "Ё", "Й", "Ж", "0", "9", ":", "°",
               "A", "B", "D", "G", "J", "L", "N", "Q", "R", "S", "U", "V", "W",
               "Z", "I", "F", "E", "T", "H", "—", "<", ">"):
        if pf.glyph(ch) is pf.GLYPHS["?"]:
            bad.append(ch)
    print("рисуются как '?':", bad or "нет")
    for ch in "АБВГДЕЖЗИКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ":
        print("  " + ch + "  " + " / ".join(pf.GLYPHS[ch]))


def render_png(path):
    pygame.init()
    pygame.display.set_mode((10, 10))
    alphabet = "АБВГДЕЖЗИКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ"
    other = "0123456789 :.,-+/()<>°!=*%?!" + "DFGIJL NQRSUVWZ"
    w, h = 40, 12
    cols = 16
    rows = (len(alphabet) + cols - 1) // cols + (len(other) + cols - 1) // cols + 2
    surf = pygame.Surface((cols * w, rows * h * 2))
    surf.fill((16, 16, 28))
    y = 4
    for chunk in (alphabet, other):
        for i, ch in enumerate(chunk):
            if ch == " ":
                continue
            pf.draw(surf, ch, 4 + (i % cols) * w, y + (i // cols) * h, (220, 240, 255))
        y += ((len(chunk) + cols - 1) // cols) * h + 8
    surf = pygame.transform.scale(surf, (surf.get_width() * 2, surf.get_height() * 2))
    pygame.image.save(surf, path)
    print("таблица глифов:", path)


if __name__ == "__main__":
    dump()
    render_png(sys.argv[1] if len(sys.argv) > 1 else "/tmp/probe_font.png")
