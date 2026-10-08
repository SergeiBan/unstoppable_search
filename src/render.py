# -*- coding: utf-8 -*-
"""Отрисовка: космос, станция (проекция клеток), кабина, радар, HUD."""

import math
import random

import pygame

import pixel_font as pf
from config import *
from patrol import hidden as patrol_hidden


class Camera:
    """Камера на плоскости: позиция + курс. Высоты в мире нет — она у глаза."""

    def __init__(self, x, y, yaw_deg):
        self.x, self.y, self.yaw = x, y, yaw_deg
        a = math.radians(yaw_deg)
        self.sa, self.ca = math.sin(a), math.cos(a)

    def project(self, wx, wy, h, clamp=True):
        """Мир (x, y, высота) -> экран. Возвращает (sx, sy, zc) или None."""
        dx = wx - self.x
        dy = wy - self.y
        zc = dx * self.sa + dy * self.ca
        xc = dx * self.ca - dy * self.sa
        yc = h - EYE
        if zc < MIN_Z:
            if not clamp:
                return None
            k = MIN_Z / max(zc, 0.02)
            xc *= k
            yc *= k
            zc = MIN_Z
        sx = CANVAS_W * 0.5 + FOCAL * xc / zc
        sy = HZ - FOCAL * yc / zc
        return (sx, max(-3000.0, min(3000.0, sy)), zc)


# --- кэши статики -------------------------------------------------------
_cache = {}


def sky_base():
    s = _cache.get("sky")
    if s is None:
        s = pygame.Surface((CANVAS_W, CANVAS_H))
        for y in range(CANVAS_H):
            k = y / (CANVAS_H - 1)
            col = tuple(int(C_VOID[i] + (C_VOID2[i] - C_VOID[i]) * k) for i in range(3))
            pygame.draw.line(s, col, (0, y), (CANVAS_W, y))
        _cache["sky"] = s
    return s


def nebula_surface(size=110):
    s = _cache.get(("neb", size))
    if s is None:
        s = pygame.Surface((size, size), pygame.SRCALPHA)
        c = size // 2
        for i in range(16, 0, -1):
            r = int(c * i / 16.0)
            alpha = int(6 + 4 * (16 - i))
            col = C_NEBULA if i % 2 else C_NEBULA2
            pygame.draw.circle(s, (col[0], col[1], col[2], alpha), (c, c), r)
        rng = random.Random(7)
        for _ in range(9):
            br = rng.randint(5, 13)
            bx = c + rng.randint(-c // 2, c // 2)
            by = c + rng.randint(-c // 2, c // 2)
            col = C_NEBULA if rng.random() < 0.6 else C_NEBULA2
            pygame.draw.circle(s, (col[0], col[1], col[2], 26), (bx, by), br)
        _cache[("neb", size)] = s
    return s


def planet_surface(size=46):
    s = _cache.get("planet")
    if s is None:
        s = pygame.Surface((size, size), pygame.SRCALPHA)
        c = size // 2
        r = c - 8
        pygame.draw.circle(s, C_PLANET, (c, c), r)
        pygame.draw.circle(s, C_PLANET_D, (c, c), r, 2)
        pygame.draw.circle(s, C_PLANET_D, (c - r // 2, c - r // 3), max(2, r // 3))
        pygame.draw.circle(s, C_PLANET_D, (c + r // 3, c + r // 2), max(2, r // 4))
        pygame.draw.ellipse(s, C_RING, (1, c - 5, size - 2, 10), 1)
        _cache["planet"] = s
    return s


def make_starfield(seed=20261007, n=240):
    rng = random.Random(seed)
    stars = []
    for _ in range(n):
        az = rng.uniform(-180.0, 180.0)
        el = rng.uniform(-26.0, 52.0)
        b = rng.random()
        if b > 0.965:
            stars.append((az, el, 2, C_STAR_W))
        elif b > 0.90:
            stars.append((az, el, 1, C_STAR_O if rng.random() < 0.5 else C_STAR_W))
        elif b > 0.72:
            stars.append((az, el, 1, C_STAR_W))
        else:
            stars.append((az, el, 1, C_STAR_B))
    return stars


def project_dir(cam, az_deg, el_deg):
    """Направление (азимут от +Y, высота) -> экран."""
    rel = math.radians(az_deg - cam.yaw)
    el = math.radians(el_deg)
    zc = math.cos(el) * math.cos(rel)
    if zc <= 0.03:
        return None
    xc = math.cos(el) * math.sin(rel)
    yc = math.sin(el)
    return (CANVAS_W * 0.5 + FOCAL * xc / zc, HZ - FOCAL * yc / zc, zc)


def draw_space(canvas, cam, stars, t):
    canvas.blit(sky_base(), (0, 0))
    for az, el, size, col in stars:
        p = project_dir(cam, az, el)
        if p is None:
            continue
        x, y = int(p[0]), int(p[1])
        if -3 <= x <= CANVAS_W + 3 and -3 <= y <= CANVAS_H + 3:
            if size == 1:
                canvas.set_at((x, y), col)
            else:
                pygame.draw.rect(canvas, col, (x - 1, y - 1, 2, 2))
    for az, el, surf in ((24.0, 10.0, nebula_surface()),
                         (-64.0, 26.0, nebula_surface(78))):
        p = project_dir(cam, az, el)
        if p is None:
            continue
        r = surf.get_rect(center=(int(p[0]), int(p[1])))
        canvas.blit(surf, r)
    p = project_dir(cam, -31.0, 21.0)
    if p is not None:
        ps = planet_surface()
        canvas.blit(ps, ps.get_rect(center=(int(p[0]), int(p[1]))))
    del t


# --- станция ------------------------------------------------------------
def _shade(col, d):
    return (max(0, min(255, col[0] + d)),
            max(0, min(255, col[1] + d)),
            max(0, min(255, col[2] + d)))


def _hash(a, b):
    return (a * 73856093 ^ b * 19349663) & 0xFFFF


def station_faces(world, cam):
    """Видимые наружу грани клеток: (x1,y1,x2,y2, сторона, gx, gy, h_lo, h_hi).

    Грани-ступени (h_lo > 0) — участок более высокой клетки, открытый наружу над
    соседней, более низкой: именно они дают объём ступенчатому силуэту.
    """
    out = []
    for gx, gy in world.cells():
        zc = (gx + 0.5 - cam.x) * cam.sa + (gy + 0.5 - cam.y) * cam.ca
        if zc < -2.0:
            continue
        h = world.height(gx, gy)
        if cam.y < gy:
            hn = world.height(gx, gy - 1) if world.solid(gx, gy - 1) else 0.0
            if hn < h:
                out.append((gx, gy, gx + 1, gy, "s", gx, gy, hn, h))
        if cam.y > gy + 1:
            hn = world.height(gx, gy + 1) if world.solid(gx, gy + 1) else 0.0
            if hn < h:
                out.append((gx, gy + 1, gx + 1, gy + 1, "n", gx, gy, hn, h))
        if cam.x < gx:
            hn = world.height(gx - 1, gy) if world.solid(gx - 1, gy) else 0.0
            if hn < h:
                out.append((gx, gy, gx, gy + 1, "w", gx, gy, hn, h))
        if cam.x > gx + 1:
            hn = world.height(gx + 1, gy) if world.solid(gx + 1, gy) else 0.0
            if hn < h:
                out.append((gx + 1, gy, gx + 1, gy + 1, "e", gx, gy, hn, h))
    return out


def _ru(value, width=4, prec=1):
    """Число в русской записи: 17,5 вместо 17.5."""
    return ("%*.*f" % (width, prec, value)).replace(".", ",")


def _pt(quad, u, v):
    (bx0, by0), (bx1, by1), (tx1, ty1), (tx0, ty0) = quad
    bx = bx0 + (bx1 - bx0) * u
    by = by0 + (by1 - by0) * u
    tx = tx0 + (tx1 - tx0) * u
    ty = ty0 + (ty1 - ty0) * u
    return (bx + (tx - bx) * v, by + (ty - by) * v)


def _poly(canvas, quad, u0, v0, u1, v1, color, outline=True):
    pts = [_pt(quad, u0, v0), _pt(quad, u1, v0), _pt(quad, u1, v1), _pt(quad, u0, v1)]
    pygame.draw.polygon(canvas, color, pts)
    if outline:
        pygame.draw.polygon(canvas, color, pts, 1)


FACE_COL = {"s": C_HULL, "n": C_HULL_DD, "w": C_PANEL, "e": C_HULL_D}


def draw_station(canvas, cam, world, t):
    faces = station_faces(world, cam)
    half_w = (world.sx1 - world.sx0) * 0.5
    half_h = (world.sy1 - world.sy0) * 0.5
    prep = []
    for x1, y1, x2, y2, side, gx, gy, hl, hh in faces:
        p0 = cam.project(x1, y1, hl)
        p1 = cam.project(x2, y2, hl)
        p2 = cam.project(x2, y2, hh)
        p3 = cam.project(x1, y1, hh)
        quad = (p0[:2], p1[:2], p2[:2], p3[:2])
        xs = [p[0] for p in quad]
        ys = [p[1] for p in quad]
        if max(xs) < -4 or min(xs) > CANVAS_W + 4 or max(ys) < -4 or min(ys) > CANVAS_H + 4:
            continue
        mx, my = (x1 + x2) * 0.5, (y1 + y2) * 0.5
        depth = math.hypot(mx - cam.x, my - cam.y)
        prep.append((depth, quad, side, gx, gy, min(xs), max(xs), min(ys), max(ys), hl))
    prep.sort(key=lambda r: -r[0])

    for depth, quad, side, gx, gy, sx0, sx1, sy0, sy1, hl in prep:
        # подсветка «по цилиндру»: центр корпуса светлее краёв — даёт объём
        k = (gx + 0.5 - world.cx) / half_w if side in ("s", "n") \
            else (gy + 0.5 - world.cy) / half_h
        base = _shade(FACE_COL[side],
                      int(-46.0 * min(1.0, k * k)) + (_hash(gx, gy) % 9) - 4)
        _poly(canvas, quad, 0.0, 0.0, 1.0, 1.0, base)
        # Детали рисуем на ЛЮБОМ расстоянии: раньше мелкие грани (в отдалении
        # боковая стена сжимается в полоску) оставались пустой заливкой и
        # станция «теряла» бока, пока не подлетишь. Пропускаем только
        # полностью субпиксельные грани — там рисовать уже нечего.
        if (sx1 - sx0) < 1.0 and (sy1 - sy0) < 1.0:
            continue
        if hl > 0.0:
            # ступень надстройки: плита + светлая кромка сверху
            _poly(canvas, quad, 0.0, 0.78, 1.0, 0.90, C_HULL_L)
            _poly(canvas, quad, 0.0, 0.90, 1.0, 1.0, _shade(C_HULL_L, -10))
            continue
        # цоколь + кромка
        _poly(canvas, quad, 0.0, 0.0, 1.0, 0.055, _shade(C_HULL_DDD, 4))
        _poly(canvas, quad, 0.0, 0.055, 1.0, 0.075, C_HULL_L)
        # буферная полоса на уровне глаза: чередующиеся блоки (видна в упор)
        for k in range(4):
            u0 = k * 0.25
            col = C_ACCENT if (_hash(gx, gy) + k) % 2 == 0 else (30, 26, 42)
            _poly(canvas, quad, u0, 0.10, u0 + 0.25, 0.16, col)
        # рёбра панелей
        _poly(canvas, quad, 0.02, 0.075, 0.055, 0.86, _shade(base, 16))
        _poly(canvas, quad, 0.945, 0.075, 0.98, 0.86, _shade(base, -20))
        _poly(canvas, quad, 0.47, 0.075, 0.53, 0.86, _shade(base, -12))
        # окна
        _poly(canvas, quad, 0.10, 0.40, 0.90, 0.64, _shade(base, -30))
        lit = (_hash(gx + 3, gy * 5 + 1) % 3) == 0
        on = math.sin(t * 1.7 + (_hash(gx, gy) % 7) * 0.9) > -0.35
        wcol = C_WIN if (lit and on) else C_WIN_OFF
        _poly(canvas, quad, 0.14, 0.43, 0.36, 0.61, wcol)
        _poly(canvas, quad, 0.64, 0.43, 0.86, 0.61, wcol)
        # козырёк
        _poly(canvas, quad, 0.0, 0.86, 1.0, 0.895, C_HULL_L)
        _poly(canvas, quad, 0.0, 0.895, 1.0, 1.0, _shade(C_HULL_D, -14))
        # стыковочный док: по центру ближней стены
        if side == "s" and abs(gx - (world.sx0 + world.sx1) // 2) <= 3:
            _poly(canvas, quad, 0.06, 0.18, 0.94, 0.84, C_BAY)
            _poly(canvas, quad, 0.14, 0.26, 0.86, 0.76, C_BAY_IN)
            glow = C_WIN if (int(t * 2.0) + gx) % 2 == 0 else C_BAY
            _poly(canvas, quad, 0.30, 0.42, 0.70, 0.62, glow)
            for uu, vv in ((0.10, 0.22), (0.86, 0.22), (0.10, 0.78), (0.86, 0.78)):
                _poly(canvas, quad, uu, vv, uu + 0.06, vv + 0.06, C_ACCENT)

    # мачта с маяком — на верхушке центральной надстройки, у ближней стены
    if cam.y < world.sy0:
        mgx = int(world.cx - 0.5)
        mx = mgx + 0.5
        my = float(world.sy0)
        hbase = world.height(mgx, world.sy0)
        b = cam.project(mx, my, hbase)
        tp = cam.project(mx, my, hbase + 2.6)
        if b[2] > 0.3:
            pygame.draw.line(canvas, C_HULL_DD, (b[0], b[1]), (tp[0], tp[1]), 2)
            pygame.draw.line(canvas, C_HULL_L, (tp[0] - 3, tp[1]), (tp[0] + 3, tp[1]), 1)
            on = math.sin(t * 3.0) > 0.0
            pygame.draw.circle(canvas, C_ACCENT if on else C_HULL_DDD,
                               (int(tp[0]), int(tp[1])), 2)
    return prep


def station_bbox(cam, world):
    """Габарит станции на экране для рамки захвата (None, если не видно)."""
    pts = []
    for wx, wy in world.station_corners():
        for h in (0.0, world.max_height()):
            p = cam.project(wx, wy, h, clamp=False)
            if p is not None:
                pts.append(p)
    if len(pts) < 4:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def draw_capture_frame(canvas, cam, world, ship):
    bb = station_bbox(cam, world)
    if bb is None:
        return
    x0, y0, x1, y1 = bb
    x0 = max(6, min(CANVAS_W - 7, x0))
    x1 = max(6, min(CANVAS_W - 7, x1))
    y0 = max(10, min(138, y0))
    y1 = max(10, min(138, y1))
    if x1 - x0 < 6 or y1 - y0 < 4:
        return
    col = C_ACCENT2
    L = min(9, max(3, int((x1 - x0) * 0.18)))
    for (cx, cy, sx, sy) in ((x0, y0, 1, 1), (x1, y0, -1, 1),
                             (x0, y1, 1, -1), (x1, y1, -1, -1)):
        pygame.draw.line(canvas, col, (cx, cy), (cx + sx * L, cy), 1)
        pygame.draw.line(canvas, col, (cx, cy), (cx, cy + sy * L), 1)
    d = world.dist_to_station(ship.fx, ship.fy)
    label = "СТАНЦИЯ " + _ru(d)
    tw = pf.text_width(label)
    lx = int(max(6, min(CANVAS_W - tw - 6, (x0 + x1) * 0.5 - tw * 0.5)))
    ly = int(y0) - 10
    if ly < 8:
        ly = int(y1) + 3
    pf.draw(canvas, label, lx, ly, col, shadow=(4, 10, 20))


# --- кабина и HUD -------------------------------------------------------
def draw_reticle(canvas):
    cx, cy = CANVAS_W // 2, int(HZ) - 10
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        pygame.draw.line(canvas, C_HUD_EDGE,
                         (cx + dx * 3, cy + dy * 3), (cx + dx * 9, cy + dy * 9), 1)
    canvas.set_at((cx, cy), C_HUD_TXT)


def draw_cockpit(canvas, t):
    # боковые стойки кабины
    pygame.draw.rect(canvas, C_HUD_BG, (0, 0, 5, CANVAS_H))
    pygame.draw.rect(canvas, C_HUD_BG, (CANVAS_W - 5, 0, 5, CANVAS_H))
    pygame.draw.rect(canvas, C_HUD_EDGE, (4, 0, 1, CANVAS_H))
    pygame.draw.rect(canvas, C_HUD_EDGE, (CANVAS_W - 5, 0, 1, CANVAS_H))
    # верхняя балка и раскосы
    pygame.draw.rect(canvas, C_HUD_BG, (0, 0, CANVAS_W, 6))
    pygame.draw.rect(canvas, C_HUD_BG2, (0, 5, CANVAS_W, 1))
    pygame.draw.polygon(canvas, C_HUD_BG, [(0, 7), (40, 7), (14, 32), (0, 32)])
    pygame.draw.polygon(canvas, C_HUD_BG,
                        [(CANVAS_W, 7), (CANVAS_W - 40, 7), (CANVAS_W - 14, 32), (CANVAS_W, 32)])
    pygame.draw.line(canvas, C_HUD_BG2, (0, 7), (40, 7), 1)
    pygame.draw.line(canvas, C_HUD_BG2, (CANVAS_W, 7), (CANVAS_W - 40, 7), 1)
    pygame.draw.line(canvas, C_HUD_BG2, (40, 7), (14, 32), 1)
    pygame.draw.line(canvas, C_HUD_BG2, (CANVAS_W - 40, 7), (CANVAS_W - 14, 32), 1)
    # нижняя приборная панель
    panel_y = 142
    pygame.draw.rect(canvas, C_HUD_BG, (0, panel_y, CANVAS_W, CANVAS_H - panel_y))
    pygame.draw.rect(canvas, C_HUD_EDGE, (0, panel_y, CANVAS_W, 1))
    pygame.draw.rect(canvas, C_HUD_BG2, (0, panel_y + 1, CANVAS_W, 1))
    for bx in range(6, CANVAS_W, 24):
        canvas.set_at((bx, panel_y + 4), C_HUD_DIM)
    # лампы справа
    for i, col in enumerate((C_ACCENT2, C_HUD_DIM, C_ACCENT)):
        on = (int(t * 2) + i) % 3 == 0
        pygame.draw.rect(canvas, col if on else C_HUD_BG2,
                         (CANVAS_W - 22 + i * 6, panel_y + 6, 4, 4))


def draw_radar(canvas, ship, world, t, patrols=None):
    R = 34
    x0, y0 = 4, 144
    surf = pygame.Surface((R, R))
    surf.fill(C_HUD_BG2)
    cx = cy = R * 0.5
    span = RADAR_SPAN * 0.5
    scale = (R * 0.5 - 3.0) / span
    a = math.radians(ship.fyaw)
    fwd = (math.sin(a), math.cos(a))
    rgt = (math.cos(a), -math.sin(a))

    def w2s(wx, wy):
        dx, dy = wx - ship.fx, wy - ship.fy
        return (cx + (dx * rgt[0] + dy * rgt[1]) * scale,
                cy - (dx * fwd[0] + dy * fwd[1]) * scale)

    # сетка
    for k in (0.33, 0.66, 1.0):
        r = int(R * 0.5 * k) - 1
        pygame.draw.rect(surf, (30, 46, 74), (int(cx) - r, int(cy) - r, r * 2, r * 2), 1)
    # станция
    poly = [w2s(wx, wy) for wx, wy in world.station_corners()]
    pygame.draw.polygon(surf, (58, 200, 176), poly)
    pygame.draw.polygon(surf, C_ACCENT2, poly, 1)
    inside = any(0 <= p[0] < R and 0 <= p[1] < R for p in poly)
    if not inside:
        mn = min(range(4), key=lambda i: (poly[i][0] - cx) ** 2 + (poly[i][1] - cy) ** 2)
        px, py = poly[mn]
        ang = math.atan2(py - cy, px - cx)
        ex, ey = cx + math.cos(ang) * (R * 0.5 - 3), cy + math.sin(ang) * (R * 0.5 - 3)
        pygame.draw.polygon(surf, C_ACCENT, [
            (ex + math.cos(ang) * 3, ey + math.sin(ang) * 3),
            (ex + math.cos(ang + 2.4) * 3, ey + math.sin(ang + 2.4) * 3),
            (ex + math.cos(ang - 2.4) * 3, ey + math.sin(ang - 2.4) * 3)])
    # патрульные корабли — точки с их цветом
    if patrols:
        for p in patrols:
            bx, by = w2s(p.pos[0], p.pos[1])
            if 1 <= bx < R - 1 and 1 <= by < R - 1:
                pygame.draw.rect(surf, p.color, (int(bx) - 1, int(by) - 1, 2, 2))
    # северный маркер
    nx, ny = w2s(ship.fx, ship.fy + span * 0.78)
    nx = max(2, min(R - 7, nx))
    ny = max(1, min(R - 8, ny))
    pf.draw(surf, "С", int(nx), int(ny), C_HUD_DIM)
    # свой корабль
    pygame.draw.polygon(surf, C_ACCENT, [(cx, cy - 4), (cx - 3, cy + 3), (cx + 3, cy + 3)])
    canvas.blit(surf, (x0, y0))
    pygame.draw.rect(canvas, C_HUD_EDGE, (x0 - 1, y0 - 1, R + 2, R + 2), 1)
    pf.draw(canvas, "РАДАР", x0, y0 - 9, C_HUD_DIM)


def draw_hud(canvas, ship, world, t, fps=None):
    d = world.dist_to_station(ship.fx, ship.fy)
    x = 44
    y = 147
    pf.draw(canvas, "ДО СТАНЦИИ " + _ru(d, 5) + " КЛ", x, y, C_HUD_TXT, shadow=(0, 0, 0))
    pf.draw(canvas, "КУРС %03d°  ХОД %d" % (ship.yaw, ship.steps), x, y + 11,
            C_HUD_TXT, shadow=(0, 0, 0))
    pf.draw(canvas, "A D < > ПОВОРОТ 45   Q E СНОС", x, y + 22, C_HUD_DIM,
            shadow=(0, 0, 0))
    if ship.warn_t > 0.0 and int(t * 6) % 2 == 0:
        msg = "СТОЛКНОВЕНИЕ"
        tw = pf.text_width(msg)
        pf.plate(canvas, (CANVAS_W // 2 - tw // 2 - 3, 132, tw + 6, 11), (46, 10, 16),
                 C_WARN, msg, C_WARN)
    if fps is not None:
        pf.draw(canvas, "%d К/С" % fps, CANVAS_W - 34, 9, C_HUD_DIM, shadow=(0, 0, 0))


def draw_patrols(canvas, cam, world, patrols, t):
    """Патрульные корабли: рисуются после станции, закрытые ею — не рисуются."""
    for p in patrols:
        if patrol_hidden(cam, world, p.pos):
            continue
        px, py = p.pos
        hx, hy = p.head
        hl = PATROL_LEN
        nose = cam.project(px + hx * hl, py + hy * hl, PATROL_H, clamp=False)
        tail = cam.project(px - hx * hl, py - hy * hl, PATROL_H, clamp=False)
        if nose is None or tail is None:
            continue
        nx, ny = nose[0], nose[1]
        txx, tyy = tail[0], tail[1]
        if not (-40 <= nx <= CANVAS_W + 40 and -40 <= ny <= CANVAS_H + 40):
            continue
        col = p.color or C_PATROL_A
        vx, vy = nx - txx, ny - tyy
        ln = math.hypot(vx, vy)
        if ln < 6.5:
            # Вдали силуэт всё равно не разбирается, а тёмная обводка съедает
            # спрайт целиком — рисуем яркую пару «корпус + факел», чтобы
            # патруль читался точкой, а не тёмной кляксой.
            pygame.draw.rect(canvas, col,
                             (int(round(nx)) - 1, int(round(ny)) - 1, 2, 2))
            pygame.draw.rect(canvas, C_FLAME,
                             (int(round(txx)) - 1, int(round(tyy)) - 1, 2, 2))
            continue
        ux, uy = vx / ln, vy / ln
        ox, oy = -uy, ux                       # перпендикуляр к курсу
        w = ln * 0.40
        hull = [(nx, ny),
                (nx - ux * ln * 0.30 + ox * w, ny - uy * ln * 0.30 + oy * w),
                (nx - ux * ln * 0.78 + ox * w * 0.50, ny - uy * ln * 0.78 + oy * w * 0.50),
                (nx - ux * ln, ny - uy * ln),
                (nx - ux * ln * 0.78 - ox * w * 0.50, ny - uy * ln * 0.78 - oy * w * 0.50),
                (nx - ux * ln * 0.30 - ox * w, ny - uy * ln * 0.30 - oy * w)]
        pygame.draw.polygon(canvas, col, hull)
        if ln >= 8.0:
            pygame.draw.polygon(canvas, C_PATROL_D, hull, 1)
        # кабина и сопло
        if ln >= 8.0:
            cab = [(nx - ux * ln * 0.30, ny - uy * ln * 0.30),
                   (nx - ux * ln * 0.30 + ox * w * 0.45, ny - uy * ln * 0.30 + oy * w * 0.45),
                   (nx - ux * ln * 0.55, ny - uy * ln * 0.55)]
            pygame.draw.polygon(canvas, C_WIN, cab)
            pygame.draw.polygon(canvas, C_WIN,
                                [(cab[0][0], cab[0][1]), cab[1],
                                 (nx - ux * ln * 0.55 - ox * w * 0.45,
                                  ny - uy * ln * 0.55 - oy * w * 0.45)])
        # факел двигателя: мерцает
        flick = 0.45 + 0.55 * (0.5 + 0.5 * math.sin(t * 23.0 + p.s * 0.7))
        fl = ln * (0.28 + 0.42 * flick)
        fw = w * (0.20 + 0.25 * flick)
        pygame.draw.polygon(canvas, C_FLAME, [
            (txx - ox * fw, tyy - oy * fw),
            (txx - ux * fl, tyy - uy * fl),
            (txx + ox * fw, tyy + oy * fw)])
        # габаритные огни: красный/зелёный по крыльям
        if ln >= 7.0:
            blink = int(t * 3.0 + p.margin) % 2 == 0
            for sgn, c in ((1.0, C_LIGHT_R), (-1.0, C_LIGHT_G)):
                if blink or sgn > 0:
                    lx = nx - ux * ln * 0.30 + ox * w * sgn
                    ly = ny - uy * ln * 0.30 + oy * w * sgn
                    pygame.draw.rect(canvas, c, (int(lx) - 1, int(ly) - 1, 2, 2))


def draw_frame(canvas, world, ship, stars, t, fps=None, patrols=None):
    cam = Camera(ship.fx, ship.fy, ship.fyaw)
    draw_space(canvas, cam, stars, t)
    draw_station(canvas, cam, world, t)
    if patrols:
        draw_patrols(canvas, cam, world, patrols, t)
    draw_reticle(canvas)
    draw_capture_frame(canvas, cam, world, ship)
    draw_cockpit(canvas, t)
    draw_radar(canvas, ship, world, t, patrols)
    draw_hud(canvas, ship, world, t, fps)
    return cam
