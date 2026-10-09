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

from config import (AGGRO_GIVEUP, AGGRO_RANGE, ATTACK_BACKOFF, ATTACK_STANDOFF,
                    CHASE_CLEAR, PATROL_R, PATROL_SPEED_1, PATROL_SPEED_2,
                    RING_STEP, STAND_CELL, STAND_HEAD, STAND_PAD)


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

    def nearest_s(self, x, y):
        """Параметр ближайшей точки маршрута к (x, y).

        Нужен, когда корабль уходил в атаку по прямой и возвращается к обходу
        станции: без пересчёта он бы «телепортировался» на старую точку пути.
        """
        best_s, best_d = 0.0, None
        for i, (px, py) in enumerate(self.pts):
            nx, ny = self.pts[(i + 1) % len(self.pts)]
            vx, vy = nx - px, ny - py
            vlen2 = vx * vx + vy * vy
            if vlen2 < 1e-12:
                continue
            k = ((x - px) * vx + (y - py) * vy) / vlen2
            k = max(0.0, min(1.0, k))
            qx, qy = px + vx * k, py + vy * k
            d = math.hypot(x - qx, y - qy)
            if best_d is None or d < best_d:
                best_d, best_s = d, self.cum[i] + math.sqrt(vlen2) * k
        return best_s


class Patrol:
    """Патрульный корабль: скользит по маршруту; став врагом — идёт на игрока.

    Пока фракция нейтральна, корабль просто облетает станцию по маршруту. Как
    только фракция стала враждебной, он бросает маршрут и идёт на игрока, держа
    дистанцию боя: подлетает до ATTACK_STANDOFF и там остаётся, а если игрок
    пролетел вплотную — отходит, чтобы не таранить. Станция на прямой мешает,
    поэтому обход строится через её ближний угол; когда игрок убегает дальше
    AGGRO_GIVEUP, корабль возвращается к обходу станции.
    """

    def __init__(self, world, margin, speed, phase=0.0, color=None, name="патруль"):
        self.path = OrbitPath(world, margin)
        self.world = world
        self.speed = float(speed)          # клеток в секунду, знак — направление
        self.s = (phase % 1.0) * self.path.total
        self.color = color
        self.name = name
        self.pos = (0.0, 0.0)
        self.head = (0.0, 1.0)
        self.mode = "orbit"                # orbit | attack
        self.update(0.0)

    @property
    def margin(self):
        return self.path.margin

    def update(self, dt, target=None, at_war=False):
        """Полёт за кадр. target — позиция игрока, at_war — враждебна ли фракция."""
        if target is not None:
            dist = math.hypot(target[0] - self.pos[0], target[1] - self.pos[1])
            if at_war:
                if self.mode == "orbit" and dist <= AGGRO_RANGE:
                    self.mode = "attack"
                elif self.mode == "attack" and dist > AGGRO_GIVEUP:
                    self.mode = "orbit"
                    self.s = self.path.nearest_s(*self.pos)
                    self.speed = abs(self.speed)
            elif self.mode == "attack":
                self.mode = "orbit"        # война кончилась — снова патрулируем
                self.s = self.path.nearest_s(*self.pos)
                self.speed = abs(self.speed)
            if self.mode == "attack":
                self._chase(target, dt)
                return
        self.s = (self.s + self.speed * dt) % self.path.total
        self.pos, head = self.path.at(self.s)
        sign = 1.0 if self.speed >= 0 else -1.0
        self.head = (head[0] * sign, head[1] * sign)

    # --- атака --------------------------------------------------------
    def _chase(self, target, dt):
        """Идём на игрока, обходя станцию; держим дистанцию боя."""
        tx, ty = target
        dx, dy = tx - self.pos[0], ty - self.pos[1]
        dist = math.hypot(dx, dy) or 1e-9
        step = abs(self.speed) * dt
        if dist > ATTACK_STANDOFF:
            wx, wy = self._waypoint(tx, ty)
            vx, vy = wx - self.pos[0], wy - self.pos[1]
            vlen = math.hypot(vx, vy) or 1e-9
            k = min(1.0, step / vlen)
            self.pos = (self.pos[0] + vx * k, self.pos[1] + vy * k)
            self.head = (vx / vlen, vy / vlen)
        elif dist < ATTACK_STANDOFF - ATTACK_BACKOFF:
            k = min(1.0, step / dist)
            self.pos = (self.pos[0] - dx * k, self.pos[1] - dy * k)
            self.head = (-dx / dist, -dy / dist)
        else:
            self.head = (dx / dist, dy / dist)   # держим дистанцию, смотрим на цель

    def _waypoint(self, tx, ty):
        """Куда идти: прямо на игрока или по кольцу вокруг станции.

        Если станция стоит на прямой, идём не «сквозь неё», а по своему же
        кольцу обхода — в ту сторону, где ближе к игроку. Кольцо вынесено от
        станции на 15 или 20 клеток, поэтому корабль обходит её честно и никогда
        не режет через корпус. Проверяем не сам корпус, а корпус с запасом
        CHASE_CLEAR: иначе корабль проходит вплотную и задевает стену боком.
        """
        if not seg_hits_rect(self.pos[0], self.pos[1], tx, ty,
                             self.world.sx0 - CHASE_CLEAR,
                             self.world.sy0 - CHASE_CLEAR,
                             self.world.sx1 + CHASE_CLEAR,
                             self.world.sy1 + CHASE_CLEAR):
            return tx, ty
        s_now = self.path.nearest_s(self.pos[0], self.pos[1])
        s_goal = self.path.nearest_s(tx, ty)
        fwd = (s_goal - s_now) % self.path.total
        step = RING_STEP if fwd <= self.path.total - fwd else -RING_STEP
        pt, _ = self.path.at(s_now + step)
        return pt


def make_patrols(world, colors):
    """Два патруля: 15 и 20 клеток от станции, в разные стороны."""
    a = Patrol(world, 15.0, PATROL_SPEED_1, phase=0.12, color=colors[0],
               name="патруль-1 (15 кл)")
    b = Patrol(world, 20.0, -PATROL_SPEED_2, phase=0.55, color=colors[1],
               name="патруль-2 (20 кл)")
    return [a, b]


class Standing:
    """Корабль, который стоит на месте: та же круглая тарелка, что у патруля.

    У стоящего корабля ракурс меняется ТОЛЬКО от движения игрока, поэтому на нём
    удобно проверять спрайт. В отличие от патрулей он ещё и перекрывает свою
    клетку: сквозь стоящий корабль пролететь нельзя. Огня у него нет, как и у
    всех кораблей в игре: что он стоит, видно по отсутствию движения.
    """

    def __init__(self, pos, head, color=None, name="стоящий корабль",
                 pad=STAND_PAD):
        self.pos = (float(pos[0]), float(pos[1]))
        self.head = (float(head[0]), float(head[1]))
        self.color = color
        self.name = name
        self.s = 0.0                 # фаза мигания огней по ободу
        self.speed = 0.0             # ноль — значит, ореола не будет
        self.margin = 0.0
        self.pad = pad               # запас по толщине для препятствия

    def update(self, dt):
        return                       # стоит на месте

    def blocked_cells(self):
        """Клетки, которые занимает тарелка.

        Корабль круглый, поэтому габарит — квадрат со стороной 2*(радиус + запас),
        без всякой возни с курсом. Занятой считаем клетку, у которой ЦЕНТР попал
        внутрь габарита: так корабль по центру клетки занимает ровно одну клетку,
        а не четыре от сдвига на десятые доли.
        """
        r = PATROL_R + self.pad
        x0, x1 = self.pos[0] - r, self.pos[0] + r
        y0, y1 = self.pos[1] - r, self.pos[1] + r
        cells = []
        for gx in range(int(math.floor(x0)), int(math.ceil(x1))):
            for gy in range(int(math.floor(y0)), int(math.ceil(y1))):
                if x0 <= gx + 0.5 <= x1 and y0 <= gy + 0.5 <= y1:
                    cells.append((gx, gy))
        return sorted(cells)


def make_standing(world, color=None):
    """Стоящий корабль в своей клетке у станции; его клетки сразу заняты."""
    gx, gy = STAND_CELL
    st = Standing((gx + 0.5, gy + 0.5), STAND_HEAD, color=color,
                  name="стоящий корабль (%d,%d)" % (gx, gy))
    world.block_cells(st.blocked_cells())
    return st


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
    return PATROL_R
