# -*- coding: utf-8 -*-
"""Планета: замеры силуэта. Поворот, подлёт, время кадра.

Три вопроса, на которые тут есть числа:

* ПОВОРОТ: силуэт обязан оставаться кругом одного размера на любом курсе
  (перспектива его растягивала: 112x112 в лоб и 108x168 в 45 градусах вбок) и
  край круга обязан совпадать с касательным лучом, иначе шар пропадёт или
  появится не там, где кончается его поверхность.
* ПОДЛЁТ: силуэт обязан расти ровно, без провалов — ровно на этом шар и
  терялся раньше (на 55,5 клетках от поверхности он падал с 211x180 до 17x18).
* ЦЕНА: время кадра с планетой и граней в силуэте.

Кадры для глаза кладём в shots/planet/.
"""
import math
import os
import sys
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

import pygame  # noqa: E402
pygame.init()
pygame.display.set_mode((320, 180))

import render  # noqa: E402
from config import CANVAS_H, CANVAS_W, FOCAL, HZ, PLANET_H  # noqa: E402
from planet import make_planet  # noqa: E402
from ship import Ship  # noqa: E402
from world import World  # noqa: E402

OUT = os.path.join(HERE, "..", "shots", "planet")
os.makedirs(OUT, exist_ok=True)

world = World()
pl = make_planet(world)
world.planet = pl
stars = render.make_starfield()

BG = (255, 0, 255)
surf = pygame.Surface((CANVAS_W, CANVAS_H))
full = pygame.Surface((CANVAS_W, CANVAS_H))


def mask_of(surface):
    """Маска «не фон» — по ней габарит и площадь силуэта (C-скорость)."""
    m = pygame.mask.from_threshold(surface, BG, (10, 10, 10, 255))
    m.invert()
    return m


def truth(cam, xx, yy):
    """Истина: пересекает ли луч из камеры настоящий шар (не многогранник)."""
    xc, yc, zc = cam.to_cam(pl.cx, pl.cy, pl.h)
    dx = (xx + 0.5 - CANVAS_W * 0.5) / FOCAL
    dy = -(yy + 0.5 - HZ) / FOCAL
    a = dx * dx + dy * dy + 1.0
    b = 2.0 * (dx * xc + dy * yc + zc)
    c = xc * xc + yc * yc + zc * zc - pl.r * pl.r
    disc = b * b - 4.0 * a * c
    return disc > 0.0 and (b - math.sqrt(disc)) / (2.0 * a) > 0.0


def shot(cam, tag):
    """Кадр планеты на фоне (для замера) и полный кадр (для глаза)."""
    surf.fill(BG)
    render.draw_planet(surf, cam, pl)
    m = mask_of(surf)
    r = None
    for q in m.get_bounding_rects():
        r = q if r is None else r.union(q)
    if r is None:
        r = pygame.Rect(0, 0, 0, 0)
    sh = Ship(cam.x, cam.y, cam.yaw)
    sh.snap()
    sh.fx, sh.fy = cam.x, cam.y
    render.draw_frame(full, world, sh, stars, 1.0, planet=pl)
    big = pygame.transform.scale(full, (CANVAS_W * 3, CANVAS_H * 3))
    pygame.image.save(big, os.path.join(OUT, tag + ".png"))
    return m, r


print("=== ПОВОРОТ: 251,5 клетки до центра (151,5 до поверхности) ===")
print("%6s %7s %14s %8s %8s %10s %9s" % (
    "курс", "alpha°", "габарит", "верх y", "низ y", "ширина/выс", "граней"))
_rows = []
for yaw in (180, 195, 210, 225, 240, 255):
    cam = render.Camera(pl.cx + 0.5, pl.cy + pl.r + 151.5, yaw)
    m, r = shot(cam, "поворот_%03d" % yaw)
    aff = pl.angular(cam)
    alpha, theta, d, rp, u = aff
    # ширина — по строке через верх силуэта, высота — от верхнего края
    y0, y1 = r.top, r.bottom - 1
    dia = 2.0 * (HZ - y0) if y0 < HZ else 0.0
    row = [x for x in range(CANVAS_W) if m.get_at((x, y0 + 2))]
    wid = (max(row) - min(row) + 1) if row else 0
    rows = len(pl.faces(cam))
    _rows.append((yaw, dia, wid))
    print("%6d %7.1f %14s %8d %8d %10s %9d" % (
        yaw, math.degrees(alpha), "%dx%d" % (r.width, r.height), y0, y1,
        "%d/%d" % (wid, int(dia)), len(pl.faces(cam))))
print("  ожидаемый диаметр силуэта 2*rp = %.0f px (одинаков на всех курсах)"
      % (2.0 * pl.angular(render.Camera(pl.cx + 0.5, pl.cy + pl.r + 151.5, 180))[3]))

print()
print("=== край силуэта против касательного луча (курс 225) ===")
cam = render.Camera(pl.cx + 0.5, pl.cy + pl.r + 151.5, 225)
alpha, theta, d, rp, u = pl.angular(cam)
m, r = shot(cam, "край_225")
s = math.hypot(u[0], u[1])
dx, dy = u[0] / s, -u[1] / s
# касательный луч ближе к прицелу и дальше от прицела — в пикселях вдоль û
near_pred = FOCAL * math.tan(max(-1.55, min(1.55, theta - alpha)))
far_pred = FOCAL * math.tan(min(1.55, theta + alpha))
cx, cy, rr = pl.screen(cam)
near_px = (cx + rr * dx, cy + rr * dy)          # ближний край нарисованного
far_px = (cx - rr * dx, cy - rr * dy)           # дальний край нарисованного
print("  theta %.1f°, alpha %.1f°, rp %.1f px, центр круга (%.0f, %.0f)"
      % (math.degrees(theta), math.degrees(alpha), rp, cx, cy))
print("  ближний край: нарисован на %.0f px от прицела, касательный луч даёт %.0f"
      % (math.hypot(cx - CANVAS_W * 0.5, cy - HZ) - rp, near_pred))
print("  дальний край: нарисован на %.0f px, касательный луч даёт %.0f"
      % (math.hypot(cx - CANVAS_W * 0.5, cy - HZ) + rp, far_pred))

print()
print("=== ПОДЛЁТ: 200 -> 0,5 клетки до поверхности, шаг 0,5 ===")


def approach(dist):
    """Габарит силуэта для данного расстояния до поверхности."""
    cam = render.Camera(pl.cx + 0.5, pl.cy + pl.r + dist, 180)
    surf.fill(BG)
    render.draw_planet(surf, cam, pl)
    m = mask_of(surf)
    r = None
    for q in m.get_bounding_rects():
        r = q if r is None else r.union(q)
    return m, r, cam


_worst_shrink = (0.0, None)
_worst_grow = (0.0, None)
_w_shrink = (0.0, None)
_w_grow = (0.0, None)
_samples = {200.0, 150.0, 100.0, 60.0, 57.0, 56.0, 55.5, 55.0, 54.5, 54.0,
            50.0, 40.0, 22.0, 10.0, 3.0, 1.0, 0.5}
prev = None
prevw = None
prev_rp = 0.0
_rp_bad = 0
dd = 200.0
rows = []
while dd >= 0.5 - 1e-9:
    m, r, cam = approach(dd)
    h = r.height
    rows.append((dd, r.width, h, r.top, m.count()))
    _rp = pl.angular(cam)[3]
    if _rp <= prev_rp:
        _rp_bad += 1
    prev_rp = _rp
    if prev is not None:
        gr = (h - prev) / float(prev) if prev else 0.0
        if gr < 0 and gr < _worst_shrink[0]:
            _worst_shrink = (gr, dd)
        if gr > 0 and gr > _worst_grow[0]:
            _worst_grow = (gr, dd)
    # ширина — единственная величина, которая не упирается в кадр раньше нас
    if prevw is not None and prevw < CANVAS_W:
        gw = (r.width - prevw) / float(prevw)
        if gw < 0 and gw < _w_shrink[0]:
            _w_shrink = (gw, dd)
        if gw > 0 and gw > _w_grow[0]:
            _w_grow = (gw, dd)
    prev = h
    prevw = r.width
    dd = round(dd - 0.5, 6)

print("%8s %14s %8s %9s" % ("до пов.", "габарит", "верх y", "пикселей"))
for dd, w, h, top, cnt in rows:
    if dd in _samples:
        print("%8.1f %14s %8d %9d" % (dd, "%dx%d" % (w, h), top, cnt))
print("  размер силуэта (аналитический радиус rp) не убывает ни на шаге: %s"
      % ("да" if _rp_bad == 0 else "НЕТ (%d раз)" % _rp_bad))
print("  ширина силуэта за шаг 0,5 кл: максимум -%.1f%% (на %.1f кл), "
      "максимум +%.1f%% (на %.1f кл)"
      % (-100.0 * _w_shrink[0], _w_shrink[1] or 0.0,
         100.0 * _w_grow[0], _w_grow[1] or 0.0))
print("  высота силуэта за шаг 0,5 кл: максимум %+.1f%% (на %.1f кл)"
      % (100.0 * _worst_shrink[0], _worst_shrink[1] or 0.0))
print("  силуэт в 200 кл: %d px, в 55,5 кл: %d px, в 55 кл: %d px, в 0,5 кл: %d px"
      % (rows[0][2], [r for r in rows if r[0] == 55.5][0][2],
         [r for r in rows if r[0] == 55.0][0][2], rows[-1][2]))

print()
print("=== кадры подлёта (для глаза) ===")
for dd in (60.0, 55.5, 55.0, 54.0, 22.0, 3.0, 0.5):
    cam = render.Camera(pl.cx + 0.5, pl.cy + pl.r + dd, 180)
    shot(cam, "подлёт_%05.1f" % dd)

print()
print("=== сходимость с расчётом луч—сфера ===")
for dist, yaw, name in ((40.0, 180, "40 кл в лоб"), (22.0, 180, "22 кл в лоб"),
                        (3.0, 180, "3 кл в лоб"), (10.0, 90, "10 кл вдоль"),
                        (3.0, 90, "3 кл вдоль"), (0.5, 90, "вплотную вдоль"),
                        (3.0, 135, "3 кл вкось"), (3.0, 0, "3 кл прочь"),
                        (300.0, 90, "300 кл вбок"), (151.5, 225, "151 кл в 45°")):
    cam = render.Camera(pl.cx + 0.5, pl.cy + pl.r + dist, yaw)
    surf.fill(BG)
    render.draw_planet(surf, cam, pl)
    m = mask_of(surf)
    ok = tot = 0
    for yy in range(12, 140, 2):
        for xx in range(40, 280, 2):
            ok += 1 if (m.get_at((xx, yy)) == 1) == truth(cam, xx, yy) else 0
            tot += 1
    print("  %-16s совпадение %.0f%%" % (name, 100.0 * ok / tot))

print()
print("=== время кадра ===")
for lab, dist, yaw in (("в 151 кл в лоб", 151.5, 180), ("в 151 кл вбок", 151.5, 210),
                       ("в 25 кл в лоб", 25.0, 180), ("в 3 кл вдоль", 3.0, 90)):
    sh = Ship(int(pl.cx), int(pl.cy + pl.r + dist), yaw)
    sh.snap()
    sh.fx, sh.fy = pl.cx + 0.5, int(pl.cy + pl.r + dist) + 0.5
    cam = render.Camera(sh.fx, sh.fy, sh.fyaw)
    for _ in range(10):
        render.draw_frame(full, world, sh, stars, 1.0, planet=pl)
    t0 = time.perf_counter()
    for _ in range(40):
        render.draw_frame(full, world, sh, stars, 1.0, planet=pl)
    ms_all = (time.perf_counter() - t0) * 1000.0 / 40.0
    surf.fill(BG)
    for _ in range(10):
        render.draw_planet(surf, cam, pl)
    t0 = time.perf_counter()
    for _ in range(40):
        render.draw_planet(surf, cam, pl)
    ms_pl = (time.perf_counter() - t0) * 1000.0 / 40.0
    print("  %-16s кадр %.2f мс, из них шар %.2f мс (граней %d)"
          % (lab, ms_all, ms_pl, len(pl.faces(cam))))

print()
print("кадры:", os.path.abspath(OUT))
