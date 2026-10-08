# -*- coding: utf-8 -*-
"""Патрульные корабли, летающие вокруг станции на заданном расстоянии.

Расстояние считается до КРОМКИ станции (квадрата), а не до её центра, и оно
постоянно по всему маршруту: путь — это «раздутый» прямоугольник станции
(прямые участки вдоль стен + четверть окружности радиусом margin в каждом
углу). Круг вокруг центра так не умеет: по диагонали корабль подходил бы к
станции почти в 1,41 раза ближе, чем по осям.

Мировая плоскость двумерная, поэтому корабль просто скользит по маршруту;
высота у него — только визуальная (чтобы смотреть чуть выше линии горизонта).
"""

import math
from bisect import bisect_right

from config import PATROL_LEN, PATROL_SPEED_1, PATROL_SPEED_2


def offset_path(world, margin, arc_steps=32):
    """Замкнутая ломаная на постоянном расстоянии margin от кромки станции."""
    x0, y0 = float(world.sx0), float(world.sy0)
    x1, y1 = float(world.sx1), float(world.sy1)
    pts = []

    def add(px, py):
        if not pts or abs(px - pts[-1][0]) > 1e-9 or abs(py - pts[-1][1]) > 1e-9:
            pts.append((px, py))

    def arc(cx, cy, a0, a1):
        for i in range(arc_steps + 1):
            a = math.radians(a0 + (a1 - a0) * i / float(arc_steps))
            add(cx + margin * math.cos(a), cy + margin * math.sin(a))

    add(x0, y0 - margin)              # южная кромка: ровно от угла до угла
    add(x1, y0 - margin)
    arc(x1, y0, -90.0, 0.0)
    add(x1 + margin, y1)              # восточная кромка
    arc(x1, y1, 0.0, 90.0)
    add(x0, y1 + margin)              # северная кромка
    arc(x0, y1, 90.0, 180.0)
    add(x0 - margin, y0)              # западная кромка
    arc(x0, y0, 180.0, 270.0)
    if len(pts) > 1 and pts[-1] == pts[0]:
        pts.pop()                     # замыкание делается неявно
    return pts


class OrbitPath:
    """Маршрут с параметром по длине дуги: at(s) -> (точка, направление)."""

    def __init__(self, world, margin, arc_steps=32):
        self.world = world
        self.margin = margin
        self.pts = offset_path(world, margin, arc_steps)
        self.cum = [0.0]
        for i, (px, py) in enumerate(self.pts):
            nx, ny = self.pts[(i + 1) % len(self.pts)]
            self.cum.append(self.cum[-1] + math.hypot(nx - px, ny - py))
        self.total = self.cum[-1]

    def at(self, s):
        s = s % self.total
        i = max(0, min(len(self.pts) - 1, bisect_right(self.cum, s) - 1))
        nxt = (i + 1) % len(self.pts)
        seg = self.cum[i + 1] - self.cum[i]
        k = (s - self.cum[i]) / seg if seg > 1e-9 else 0.0
        x0, y0 = self.pts[i]
        x1, y1 = self.pts[nxt]
        dx, dy = x1 - x0, y1 - y0
        ln = math.hypot(dx, dy) or 1.0
        return (x0 + dx * k, y0 + dy * k), (dx / ln, dy / ln)


class Patrol:
    """Патрульный корабль: скользит по маршруту с постоянной скоростью."""

    def __init__(self, world, margin, speed, phase=0.0, color=None, name="патруль"):
        self.path = OrbitPath(world, margin)
        self.speed = float(speed)          # клеток в секунду, знак — направление
        self.s = (phase % 1.0) * self.path.total
        self.color = color
        self.name = name
        self.pos = (0.0, 0.0)
        self.head = (0.0, 1.0)
        self.update(0.0)

    @property
    def margin(self):
        return self.path.margin

    def update(self, dt):
        self.s = (self.s + self.speed * dt) % self.path.total
        self.pos, head = self.path.at(self.s)
        sign = 1.0 if self.speed >= 0 else -1.0
        self.head = (head[0] * sign, head[1] * sign)


def make_patrols(world, colors):
    """Два патруля: 15 и 20 клеток от станции, в разные стороны."""
    a = Patrol(world, 15.0, PATROL_SPEED_1, phase=0.12, color=colors[0],
               name="патруль-1 (15 кл)")
    b = Patrol(world, 20.0, -PATROL_SPEED_2, phase=0.55, color=colors[1],
               name="патруль-2 (20 кл)")
    return [a, b]


def seg_hits_rect(ax, ay, bx, by, rx0, ry0, rx1, ry1):
    """Пересекает ли отрезок прямоугольник (метод слэбов).

    Так проверяется, закрыт ли патруль корпусом станции: если отрезок от
    камеры до корабля проходит через габарит станции, корабль за ней.
    """
    dx, dy = bx - ax, by - ay
    tmin, tmax = 0.0, 1.0
    for p, d, lo, hi in ((ax, dx, rx0, rx1), (ay, dy, ry0, ry1)):
        if abs(d) < 1e-9:
            if p < lo or p > hi:
                return False
        else:
            t1, t2 = (lo - p) / d, (hi - p) / d
            if t1 > t2:
                t1, t2 = t2, t1
            tmin = max(tmin, t1)
            tmax = min(tmax, t2)
            if tmin > tmax:
                return False
    return True


def hidden(cam, world, pos):
    """Скрыт ли объект корпусом станции от камеры."""
    return seg_hits_rect(cam.x, cam.y, pos[0], pos[1],
                         float(world.sx0), float(world.sy0),
                         float(world.sx1), float(world.sy1))


def half_len():
    return PATROL_LEN
