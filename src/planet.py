# -*- coding: utf-8 -*-
"""Планета: настоящий шар из полигонов.

Мир двумерный, но высота у объектов есть (см. проекцию в render.py), поэтому
шар строится как обычная многогранная фигура: сетка треугольников единичной
сферы, растянутая до радиуса планеты. Дальше всё как со станцией — грани в
координатах камеры, отсечение по ближней плоскости, заливка.

Важное следствие выпуклости: у шара не нужно ни сортировать грани, ни
подбирать силуэт. Достаточно отбросить грани, повёрнутые от камеры, — они всё
равно закрыты передними. Именно поэтому такая планета честно выглядит и в
упор, и сбоку: форма получается сама, а не из «диска нужного размера».
"""

import math

from config import (CANVAS_H, CANVAS_W, C_PLANET, C_PLANET_D, EYE, FOCAL, HZ,
                    PLANET_H, PLANET_LAT, PLANET_LAT_SMALL, PLANET_LIGHT,
                    PLANET_LON, PLANET_LON_SMALL, PLANET_R, PLANET_SIMPLE_AT)


def _norm3(v):
    n = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]) or 1.0
    return (v[0] / n, v[1] / n, v[2] / n)


def _face_normal(p, q, s):
    """Нормаль треугольника, направленная НАРУЖУ от центра сферы."""
    ux, uy, uz = q[0] - p[0], q[1] - p[1], q[2] - p[2]
    vx, vy, vz = s[0] - p[0], s[1] - p[1], s[2] - p[2]
    nx = uy * vz - uz * vy
    ny = uz * vx - ux * vz
    nz = ux * vy - uy * vx
    ln = math.sqrt(nx * nx + ny * ny + nz * nz)
    if ln < 1e-9:
        return None
    nx, ny, nz = nx / ln, ny / ln, nz / ln
    # у сферы внешняя нормаль совпадает с направлением от центра: выравниваем
    cx = (p[0] + q[0] + s[0]) / 3.0
    cy = (p[1] + q[1] + s[1]) / 3.0
    cz = (p[2] + q[2] + s[2]) / 3.0
    if nx * cx + ny * cy + nz * cz < 0.0:
        nx, ny, nz = -nx, -ny, -nz
    return (nx, ny, nz)


def build_mesh(lat, lon):
    """Треугольники единичной сферы: (три вершины, внешняя нормаль).

    Ось z — высота (полюса сверху и снизу), оси x и y — мировые. Полюсные
    треугольники вырождаются в линию, их выбрасываем сразу.
    """
    rings = []
    for i in range(lat + 1):
        th = math.pi * i / lat                     # 0 — полюс, pi — другой полюс
        hh = math.cos(th)
        rr = math.sin(th)
        ring = []
        for j in range(lon):
            ph = 2.0 * math.pi * j / lon
            ring.append((rr * math.cos(ph), rr * math.sin(ph), hh))
        rings.append(ring)
    tris = []
    for i in range(lat):
        for j in range(lon):
            k = (j + 1) % lon
            a, b = rings[i][j], rings[i][k]
            c, d = rings[i + 1][j], rings[i + 1][k]
            for tri in ((a, b, d), (a, d, c)):
                n = _face_normal(*tri)
                if n is not None:
                    tris.append((tri, n))
    return tris


class Planet:
    """Шар: центр, радиус, сетка граней и отбор лицевых."""

    def __init__(self, cx, cy, radius, h=PLANET_H):
        self.cx, self.cy = float(cx), float(cy)
        self.h = float(h)
        self.r = float(radius)
        self._mesh = {}

    def contains(self, x, y):
        """Внутри ли точка мира тела планеты (по ней и упирается корабль)."""
        dx, dy = x - self.cx, y - self.cy
        return dx * dx + dy * dy <= self.r * self.r

    def dist_to(self, x, y):
        """Расстояние до ПОВЕРХНОСТИ планеты (0 — на поверхности)."""
        dx, dy = x - self.cx, y - self.cy
        return max(0.0, math.hypot(dx, dy) - self.r)

    def mesh(self, lat, lon):
        if (lat, lon) not in self._mesh:
            self._mesh[(lat, lon)] = build_mesh(lat, lon)
        return self._mesh[(lat, lon)]

    def screen(self, cam):
        """Экранный круг шара: (cx, cy, r) или None, если рисовать нечего."""
        xc, yc, zc = cam.to_cam(self.cx, self.cy, self.h)
        d2 = xc * xc + yc * yc + zc * zc
        if d2 <= self.r * self.r:
            return None                    # камера внутри планеты (не бывает)
        # Шар виден, если часть его перед камерой: ближняя точка по оси взгляда
        # стоит zc + r. Без этой проверки диск рисовался и когда планета ровно
        # за спиной.
        if zc + self.r <= 0.0:
            return None
        rp = FOCAL * self.r / math.sqrt(max(d2 - self.r * self.r, 1e-6))
        z = max(zc, self.r * 0.15)
        return (CANVAS_W * 0.5 + FOCAL * xc / z, HZ - FOCAL * yc / z, rp)

    def visible(self, cam):
        """Есть ли шар в кадре.

        Считаем по углам: расстояние от направления на центр до оси взгляда
        меньше углового радиуса шара плюс половина поля зрения. Проверка по
        экранному диску здесь не годится: в упор изображение шара выходит далеко
        за «кружок» касательного конуса, и диск объявлял планету невидимой.
        """
        xc, yc, zc = cam.to_cam(self.cx, self.cy, self.h)
        d2 = xc * xc + yc * yc + zc * zc
        if d2 <= self.r * self.r:
            return False                   # камера внутри планеты (не бывает)
        d = math.sqrt(d2)
        ang = math.acos(max(-1.0, min(1.0, zc / d)))
        alpha = math.asin(min(1.0, self.r / d))
        half = math.atan(math.hypot(CANVAS_W * 0.5, CANVAS_H * 0.5) / FOCAL)
        return ang < alpha + half

    def faces(self, cam):
        """Лицевые грани в координатах камеры: [(три точки, цвет), ...].

        Отбор: грань видна, если её внешняя нормаль смотрит в сторону камеры,
        то есть скалярное произведение нормали на направление к камере больше
        нуля. Для выпуклого тела этого достаточно — задние грани закрыты
        передними, сортировка не нужна.

        Цвет — базовая краска, ослабленная по косинусу угла к источнику света.
        Свет в мировых осях, поэтому терминатор стоит на месте, как бы игрок
        ни разворачивался.
        """
        sc = self.screen(cam)
        if sc is None:
            return []
        lat, lon = ((PLANET_LAT, PLANET_LON) if sc[2] >= PLANET_SIMPLE_AT
                    else (PLANET_LAT_SMALL, PLANET_LON_SMALL))
        light = _norm3(PLANET_LIGHT)
        out = []
        for tri, n in self.mesh(lat, lon):
            # центр грани в мире (вершины — это r * нормаль в осях шара)
            wx = self.cx + self.r * (tri[0][0] + tri[1][0] + tri[2][0]) / 3.0
            wy = self.cy + self.r * (tri[0][1] + tri[1][1] + tri[2][1]) / 3.0
            wh = self.h + self.r * (tri[0][2] + tri[1][2] + tri[2][2]) / 3.0
            # видна, если нормаль смотрит в сторону камеры: у выпуклого тела
            # задние грани всё равно закрыты передними, сортировка не нужна
            to_cam = (cam.x - wx, cam.y - wy, EYE - wh)
            if n[0] * to_cam[0] + n[1] * to_cam[1] + n[2] * to_cam[2] <= 0.0:
                continue
            dl = n[0] * light[0] + n[1] * light[1] + n[2] * light[2]
            # Разброс яркости широкий (от 15% до 100%): при узком шар выглядел
            # однотонным, объём не читался.
            k = 0.15 + 0.85 * max(0.0, dl) ** 0.8
            col = tuple(int(C_PLANET_D[i] + (C_PLANET[i] - C_PLANET_D[i]) * k)
                        for i in range(3))
            # Обводка темнее заливки: она и закрывает волосяные щели между
            # гранями, и показывает саму многогранную структуру шара.
            edge = tuple(int(c * 0.72) for c in col)
            pts = []
            for v in tri:
                pts.append(cam.to_cam(self.cx + self.r * v[0],
                                      self.cy + self.r * v[1],
                                      self.h + self.r * v[2]))
            out.append((pts, col, edge))
        return out


def make_planet(world):
    """Планета к югу от станции: центр в 500 клетках от её кромки, радиус 100."""
    from config import PLANET_DIST, PLANET_R
    return Planet(world.cx, world.sy0 - PLANET_DIST, PLANET_R)
