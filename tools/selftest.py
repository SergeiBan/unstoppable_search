# -*- coding: utf-8 -*-
"""Автотест логики (клавиатуру в headless не нажать): движение, столкновения,
повторы шага при удержании, повороты на 45, диагональ, проекция, шрифт.

Запуск: .venv/bin/python tools/selftest.py
"""

import math
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import pygame

pygame.init()
pygame.display.set_mode((10, 10))

import pixel_font as pf
import render
from config import (CANVAS_H, CANVAS_W, FPS, SHIP_START_GX, SHIP_START_GY,
                    SHIP_START_YAW, STEP_REPEAT, TURN_REPEAT, TURN_STEP)
from ship import Ship
from world import World

FAIL = []
COUNT = [0]


def check(name, ok, detail=""):
    COUNT[0] += 1
    print("%-48s %s %s" % (name, "ОК " if ok else "ПРОВАЛ", detail))
    if not ok:
        FAIL.append(name)


# --- мир ---------------------------------------------------------------
w = World()
check("станция квадратная 20x20 = 400 клеток",
      w.area() == 400 and (w.sx1 - w.sx0) == (w.sy1 - w.sy0),
      "%dx%d" % (w.sx1 - w.sx0, w.sy1 - w.sy0))
check("клетки станции сплошные", all(w.solid(gx, gy) for gx, gy in w.cells()))
check("снаружи станции пусто", not w.solid(w.sx0 - 1, w.sy0 - 1))
check("высота-хребет выше базовой",
      w.height(int(w.cx - 0.5), w.sy0) > w.height(w.sx0, w.sy0),
      "%.1f > %.1f" % (w.height(int(w.cx - 0.5), w.sy0), w.height(w.sx0, w.sy0)))

# --- сближение и упор ---------------------------------------------------
s = Ship(SHIP_START_GX, SHIP_START_GY, SHIP_START_YAW)
d0 = w.dist_to_station(*s.world())
check("старт в 17,5 кл от станции", abs(d0 - 17.5) < 0.01, "%.2f" % d0)
for i in range(40):
    s.try_move("fwd", w)
check("упор в станцию на клетке (57,47)", (s.gx, s.gy) == (57, 47), str((s.gx, s.gy)))
check("шаги вперёд: 17 принято, 23 отбито", (s.steps, s.blocks) == (17, 23),
      "шагов %d, отказов %d" % (s.steps, s.blocks))
check("в упор расстояние 0,5 кл",
      abs(w.dist_to_station(*s.world()) - 0.5) < 0.01,
      "%.2f" % w.dist_to_station(*s.world()))
tx, ty = s.target_cell("fwd")
check("клетка впереди занята станцией, шаг отбит",
      w.solid(tx, ty) and s.try_move("fwd", w) is False and (s.gx, s.gy) == (57, 47),
      "цель (%d,%d)" % (tx, ty))

# --- уход от станции ----------------------------------------------------
s2 = Ship(57, 47, 180)
d_before = w.dist_to_station(*s2.world())
for _ in range(10):
    s2.try_move("fwd", w)
d_after = w.dist_to_station(*s2.world())
check("от станции можно улететь", d_after > d_before + 9.0,
      "%.1f -> %.1f кл" % (d_before, d_after))

# --- поворот на 45 ------------------------------------------------------
s3 = Ship(57, 30, 0)
s3.turn(TURN_STEP)
check("один поворот = 45 градусов", s3.yaw == 45, str(s3.yaw))
s3.turn(-TURN_STEP)
check("обратный поворот возвращает курс", s3.yaw == 0, str(s3.yaw))
for _ in range(8):
    s3.turn(TURN_STEP)
check("восемь поворотов = полный круг", s3.yaw == 0, str(s3.yaw))
s4 = Ship(57, 30, 0)
s4.turn(-TURN_STEP)
check("поворот влево: 0 -> 315", s4.yaw == 315, str(s4.yaw))

dirs = {}
for yaw, want in ((0, (0, 1)), (90, (1, 0)), (180, (0, -1)), (270, (-1, 0)),
                  (45, (1, 1)), (135, (1, -1)), (225, (-1, -1)), (315, (-1, 1))):
    dirs[yaw] = Ship(57, 30, yaw).target_cell("fwd") == (57 + want[0], 30 + want[1])
check("все 8 курсов ведут в верную клетку", all(dirs.values()),
      str([k for k, v in dirs.items() if not v]) or "все 8")

# --- диагональный шаг ---------------------------------------------------
sd = Ship(57, 30, 45)
moved = sd.try_move("fwd", w)
check("на 45 шаг идёт по диагонали в (58,31)",
      moved and (sd.gx, sd.gy) == (58, 31), str((sd.gx, sd.gy)))
check("диагональный шаг длиннее: %.2f с" % (STEP_REPEAT * math.sqrt(2)),
      abs(sd.step_time - STEP_REPEAT * math.sqrt(2)) < 1e-6,
      "%.3f" % sd.step_time)
check("скорость не зависит от направления",
      abs((STEP_REPEAT / sd.step_time) - (1.0 / math.sqrt(2))) < 1e-6)
sw = Ship(47, 47, 45)
check("в угол станции по диагонали не пройти",
      sw.try_move("fwd", w) is False and (sw.gx, sw.gy) == (47, 47), str((sw.gx, sw.gy)))

# диагональная щель: цель свободна, но оба соседа заняты — срезать угол нельзя
w2 = World()
wall = {(10, 10), (11, 11)}
w2.solid = lambda gx, gy: (gx, gy) in wall
sc = Ship(10, 11, 135)          # цель (11,10) свободна, соседи (11,11) и (10,10) — нет
check("угол между двух блоков не срезается",
      sc.try_move("fwd", w2) is False and (sc.gx, sc.gy) == (10, 11))

# --- удержание клавиши: темп шагов и поворотов --------------------------
dt = 1.0 / FPS
s5 = Ship(SHIP_START_GX, SHIP_START_GY, 0)
for i in range(60):                      # секунда удержания «вперёд»
    s5.update(dt, {"fwd"}, w)
expect = 1 + int(1.0 / STEP_REPEAT)
check("удержание «вперёд» за 1 с даёт ~%d шагов" % expect,
      abs(s5.steps - expect) <= 1, "шагов %d" % s5.steps)

s6 = Ship(SHIP_START_GX, SHIP_START_GY, 0)
for i in range(60):                      # секунда удержания стрелки вправо
    s6.update(dt, {"turn_r"}, w)
expect_t = 1 + int(1.0 / TURN_REPEAT)
check("удержание «поворот» за 1 с даёт ~%d поворотов" % expect_t,
      abs(s6.turns - expect_t) <= 1, "поворотов %d, курс %d" % (s6.turns, s6.yaw))

s6b = Ship(SHIP_START_GX, SHIP_START_GY, 0)
for i in range(60):
    s6b.update(dt, {"turn_r", "fwd"}, w)   # поворот и ход одновременно
check("поворот и ход работают одновременно",
      s6b.turns > 0 and s6b.steps > 0,
      "шагов %d, поворотов %d" % (s6b.steps, s6b.turns))

s7 = Ship(SHIP_START_GX, SHIP_START_GY, 0)
for i in range(60):
    s7.update(dt, {"left"}, w)
check("снос влево идёт по X", s7.gx < SHIP_START_GX and s7.gy == SHIP_START_GY,
      str((s7.gx, s7.gy)))
s8 = Ship(SHIP_START_GX, SHIP_START_GY, 0)
for i in range(60):
    s8.update(dt, {"back"}, w)
check("«назад» тянет в -Y", s8.gy < SHIP_START_GY, "gy=%d" % s8.gy)
s9 = Ship(SHIP_START_GX, SHIP_START_GY, 0)
for i in range(60):
    s9.update(dt, {"right"}, w)
check("снос вправо идёт по X", s9.gx > SHIP_START_GX, "gx=%d" % s9.gx)
s10 = Ship(SHIP_START_GX, SHIP_START_GY, 0)
for i in range(60):
    s10.update(dt, set(), w)
check("без нажатых клавиш шагов нет", s10.steps == 0 and s10.turns == 0)
check("без нажатых клавиш курс не течёт",
      abs(s10.fyaw - s10.yaw) < 1e-6, "%.4f" % s10.fyaw)

# --- предупреждение гаснет ---------------------------------------------
s11 = Ship(57, 47, 0)
s11.try_move("fwd", w)
warn0 = s11.warn_t
for i in range(120):
    s11.update(dt)
check("предупреждение о столкновении гаснет", warn0 > 0 and s11.warn_t == 0.0,
      "%.2f -> %.2f" % (warn0, s11.warn_t))

# --- визуал: сглаживание доводит до цели ---------------------------------
s12 = Ship(57, 30, 0)
s12.try_move("fwd", w)
s12.turn(45)
for i in range(60):
    s12.update(dt)
check("визуал догоняет логику (позиция и курс)",
      abs(s12.fy - (s12.gy + 0.5)) < 0.01 and abs(s12.fyaw - 45.0) < 0.06,
      "fy=%.3f, fyaw=%.2f" % (s12.fy, s12.fyaw))

# --- раскладка клавиатуры: скан-коды ------------------------------------
import main as M
check("W определяется по скан-коду 26 (=fwd)", M.KEY_ACTIONS.get(26) == "fwd")
check("A/D теперь поворот влево/вправо",
      M.KEY_ACTIONS.get(4) == "turn_l" and M.KEY_ACTIONS.get(7) == "turn_r",
      "A=%s D=%s" % (M.KEY_ACTIONS.get(4), M.KEY_ACTIONS.get(7)))
check("Q/E теперь дрейф влево/вправо",
      M.KEY_ACTIONS.get(20) == "left" and M.KEY_ACTIONS.get(8) == "right",
      "Q=%s E=%s" % (M.KEY_ACTIONS.get(20), M.KEY_ACTIONS.get(8)))
check("S/↓ — назад", M.KEY_ACTIONS.get(22) == "back" and M.KEY_ACTIONS.get(81) == "back")
check("стрелки < > тоже поворачивают",
      M.KEY_ACTIONS.get(80) == "turn_l" and M.KEY_ACTIONS.get(79) == "turn_r")
check("код русской раскладки 'ц' (1094) в таблице НЕ используется",
      1094 not in M.KEY_ACTIONS)
keys_sc = set(M.KEY_ACTIONS)
check("движение задано скан-кодами (<= 512), а не кодами символов",
      all(0 <= k < 512 for k in keys_sc), str(sorted(keys_sc)))

# то же самое через реальные события: W под русской раскладкой идёт с key=1094
inp = M.Input()
inp.handle(pygame.event.Event(pygame.KEYDOWN, key=1094, scancode=26, mod=0, unicode="ц"))
check("W при русской раскладке даёт «вперёд»", inp.acts() == {"fwd"},
      str(sorted(inp.acts())))
inp.handle(pygame.event.Event(pygame.KEYDOWN, key=1094, scancode=26, mod=0, unicode="ц"))
check("повторный KEYDOWN не дублируется", inp.acts() == {"fwd"})
inp.handle(pygame.event.Event(pygame.KEYUP, key=1094, scancode=26, mod=0, unicode="ц"))
check("KEYUP снимает действие", inp.acts() == set())
inp.handle(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RIGHT, scancode=79,
                              mod=0, unicode=None))
inp.handle(pygame.event.Event(pygame.KEYDOWN, key=1094, scancode=26, mod=0, unicode="ц"))
check("поворот и ход нажимаются вместе", inp.acts() == {"turn_r", "fwd"},
      str(sorted(inp.acts())))
inp.handle(pygame.event.Event(pygame.WINDOWFOCUSLOST))
check("потеря фокуса снимает все клавиши", inp.acts() == set())
check("обычные клавиши (Esc) не попадают в управление",
      inp.handle(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE,
                                    scancode=41, mod=0, unicode="\x1b")) is False)
# A/D (рус. «ф»/«в») должны поворачивать, Q/E (рус. «й»/«у») — дрейфовать
inp2 = M.Input()
inp2.handle(pygame.event.Event(pygame.KEYDOWN, key=1092, scancode=4, mod=0, unicode="ф"))
check("A при русской раскладке даёт поворот влево", inp2.acts() == {"turn_l"},
      str(sorted(inp2.acts())))
inp2.handle(pygame.event.Event(pygame.KEYDOWN, key=1074, scancode=7, mod=0, unicode="в"))
check("D при русской раскладке даёт поворот вправо", inp2.acts() == {"turn_l", "turn_r"})
inp2.handle(pygame.event.Event(pygame.KEYUP, key=1092, scancode=4, mod=0, unicode="ф"))
inp2.handle(pygame.event.Event(pygame.KEYUP, key=1074, scancode=7, mod=0, unicode="в"))
inp2.handle(pygame.event.Event(pygame.KEYDOWN, key=1081, scancode=20, mod=0, unicode="й"))
inp2.handle(pygame.event.Event(pygame.KEYDOWN, key=1091, scancode=8, mod=0, unicode="у"))
check("Q/E дают дрейф влево/вправо", inp2.acts() == {"left", "right"},
      str(sorted(inp2.acts())))

# поворот на A и дрейф на Q действительно двигают корабль по-разному
sa = Ship(57, 30, 0)
for _ in range(30):
    sa.update(dt, {"turn_l"}, w)
check("A крутит, а не сносит", sa.yaw == 225 and sa.gx == 57 and sa.gy == 30,
      "курс %d, клетка (%d,%d)" % (sa.yaw, sa.gx, sa.gy))
sq = Ship(57, 30, 0)
for _ in range(30):
    sq.update(dt, {"left"}, w)
check("Q сносит без поворота", sq.yaw == 0 and sq.gx < 57,
      "курс %d, клетка (%d,%d)" % (sq.yaw, sq.gx, sq.gy))

# --- проекция и грани ---------------------------------------------------
cam = render.Camera(57.5, 47.5, 0.0)
p = cam.project(57.5, 48.0, 0.9)
check("точка на уровне глаза ложится на линию горизонта",
      abs(p[1] - 98.0) < 8.0, "sy=%.1f" % p[1])
p2 = cam.project(57.5, 64.0, 0.9)
check("дальняя точка тоже на горизонте", abs(p2[1] - 98.0) < 8.0, "sy=%.1f" % p2[1])
check("правее по X -> правее на экране",
      cam.project(58.5, 48.0, 0.9)[0] > cam.project(57.0, 48.0, 0.9)[0])
faces = render.station_faces(World(), cam)
check("в упор видно 20 граней ближней стены", len(faces) == 20, "%d" % len(faces))
check("за спиной граней нет",
      len(render.station_faces(World(), render.Camera(57.5, 20.5, 180.0))) == 0)
cam2 = render.Camera(78.5, 31.5, 0.0)
check("под углом видно обе стены + ступени",
      len(render.station_faces(World(), cam2)) >= 55,
      "%d" % len(render.station_faces(World(), cam2)))
cam45 = render.Camera(57.5, 30.5, 45.0)
check("на курсе 45 станция тоже в кадре",
      len(render.station_faces(World(), cam45)) >= 20,
      "%d" % len(render.station_faces(World(), cam45)))
cam0 = render.Camera(57.5, 30.5, 0.0)
sx0 = cam0.project(48.0, 48.0, 0.0)[0]
sx45 = cam45.project(48.0, 48.0, 0.0)[0]
check("поворот камеры на 45 сдвигает проекцию",
      abs(sx0 - sx45) > 100.0, "x=%.0f -> %.0f" % (sx0, sx45))
check("на 45 ближняя стена уходит за левый край (камера внутри габарита)",
      sx45 < 0.0, "x=%.0f" % sx45)

# --- патрульные корабли -------------------------------------------------
import patrol as P

p1 = P.OrbitPath(w, 15.0)
p2 = P.OrbitPath(w, 20.0)
for path, m in ((p1, 15.0), (p2, 20.0)):
    ds = [w.dist_to_station(*path.at(i * path.total / 400)[0]) for i in range(400)]
    check("маршрут %.0f кл: расстояние до станции постоянное" % m,
          max(abs(d - m) for d in ds) < 0.01,
          "мин %.3f, макс %.3f" % (min(ds), max(ds)))
    check("маршрут %.0f кл: длина = 4 стороны + 2πr" % m,
          abs(path.total - (80.0 + 2 * math.pi * m)) / path.total < 0.005,
          "%.2f против %.2f" % (path.total, 80.0 + 2 * math.pi * m))

ships = P.make_patrols(w, ("#fff", "#000"))
check("патрулей два", len(ships) == 2)
check("расстояния 15 и 20 кл", sorted(round(s.margin) for s in ships) == [15, 20])
check("патрули идут навстречу (разные знаки скорости)",
      ships[0].speed > 0 > ships[1].speed,
      "%.1f и %.1f" % (ships[0].speed, ships[1].speed))

worst = 99.0
for _ in range(1200):                    # 20 с полёта при 60 к/с
    for s in ships:
        s.update(dt)
        worst = min(worst, w.dist_to_station(*s.pos))
        cell = (int(s.pos[0]), int(s.pos[1]))
        if w.solid(*cell):
            worst = -1.0
check("за 20 с полёта патрули ни разу не вошли в станцию и не приблизились",
      worst > 14.9, "минимальное расстояние %.3f кл" % worst)

s0 = P.Patrol(w, 15.0, 6.0)
start = s0.pos
lap_frames = int(round((s0.path.total / 6.0) * FPS))
for _ in range(lap_frames):
    s0.update(dt)
check("за полный круг патруль возвращается к началу маршрута",
      math.hypot(s0.pos[0] - start[0], s0.pos[1] - start[1]) < 0.15,
      "сдвиг %.4f кл (кадр = %.2f кл)" % (
          math.hypot(s0.pos[0] - start[0], s0.pos[1] - start[1]), 6.0 * dt))

cam_far = render.Camera(58.5, 20.5, 0.0)
check("патруль за станцией считается скрытым",
      P.hidden(cam_far, w, (58.0, 75.0)) is True)
check("патруль перед станцией не скрыт",
      P.hidden(cam_far, w, (58.0, 30.0)) is False)

# --- дымовой тест отрисовки патруля --------------------------------------
canvas = pygame.Surface((CANVAS_W, CANVAS_H))
sh = Ship(58, 20, 0)
sh.snap()
stars = render.make_starfield(20261007)
fake = P.Patrol(w, 15.0, 6.0, color=(150, 245, 255))
fake.pos = (58.0, 30.0)
fake.head = (1.0, 0.0)
fake.s = 0.0
render.draw_frame(canvas, w, sh, stars, 1.0, patrols=[fake])
def count_col(surf, col):
    n = 0
    for y in range(surf.get_height()):
        for x in range(surf.get_width()):
            if surf.get_at((x, y))[:3] == col[:3]:
                n += 1
    return n
near = count_col(canvas, (150, 245, 255))
check("патруль в кадре виден (есть его цвет)", near > 12, "пикселей %d" % near)
fake.pos = (58.0, 75.0)                  # за станцией
fake.s = 1.0
render.draw_frame(canvas, w, sh, stars, 1.0, patrols=[fake])
check("патруль за станцией не рисуется",
      count_col(canvas, (150, 245, 255)) < 12,
      "пикселей %d" % count_col(canvas, (150, 245, 255)))

# --- регрессия: спиной к станции кадр не должен заливаться серым ---------
# Причина бага: точке ЗА камерой подставлялся zc = MIN_Z, а xc оставался прежним —
# точка «перелетала» на другую сторону, четырёхугольник выворачивался наизнанку и
# заливал кадр одной краской. Теперь такие точки не проецируются, а полигон
# честно отсекается по ближней плоскости.
def dominant(surf):
    """Доля самого частого цвета в окне вида (без кабины и панели)."""
    cnt = {}
    tot = 0
    for y in range(10, 138, 2):
        for x in range(8, 312, 2):
            c = tuple(surf.get_at((x, y))[:3])
            cnt[c] = cnt.get(c, 0) + 1
            tot += 1
    top = max(cnt, key=lambda c: cnt[c])
    return cnt[top] / float(tot), top


c3 = pygame.Surface((CANVAS_W, CANVAS_H))
worst = (0.0, None, None)
for gy_ in (46, 47, 48, 30, 20):
    for yaw in (0, 45, 90, 135, 180, 225, 270, 315):
        sh_g = Ship(57, gy_, yaw)
        sh_g.snap()
        render.draw_frame(c3, World(), sh_g, stars, 1.0)
        share, col = dominant(c3)
        if share > worst[0]:
            worst = (share, (gy_, yaw), col)
check("кадр не залит одним цветом ни в одном из 40 положений",
      worst[0] < 0.72,
      "максимум %.0f%% цвета %s при y=%d, курсе %d"
      % (worst[0] * 100, worst[2], worst[1][0], worst[1][1]))

sh_b = Ship(57, 47, 180)          # прижался к станции спиной
sh_b.snap()
render.draw_frame(c3, World(), sh_b, stars, 1.0)
grey = tot = 0
for y in range(10, 138, 2):
    for x in range(8, 312, 2):
        r, g, b = tuple(c3.get_at((x, y))[:3])
        tot += 1
        if r > 60 and g > 60 and b > 60 and max(r, g, b) - min(r, g, b) < 45:
            grey += 1
check("спиной к станции видно космос, а не серую заливку",
      grey / float(tot) < 0.08, "серых пикселей %.1f%%" % (100.0 * grey / tot))

cam_b = render.Camera(57.5, 46.5, 180.0)   # смотрит в −y
check("точка за камерой не проецируется вовсе",
      cam_b.project(57.5, 50.0, 0.9) is None
      and cam_b.project(57.5, 40.0, 0.9) is not None,
      "позади %s, впереди %s" % (cam_b.project(57.5, 50.0, 0.9),
                                 bool(cam_b.project(57.5, 40.0, 0.9))))

quad_cut = [(0.0, 0.0, -1.0), (2.0, 0.0, 2.0), (2.0, 2.0, 2.0), (0.0, 2.0, -1.0)]
cut = render.clip_near(quad_cut)
check("полигон, режущий ближнюю плоскость, отсекается по ней",
      len(cut) == 4 and all(p[2] >= render.MIN_Z - 1e-9 for p in cut),
      "вершин после отсечения %d, минимальная z %.3f"
      % (len(cut), min(p[2] for p in cut)))

check("грань целиком за камерой не рисуется",
      render.cam_poly(cam_b, [(0.0, 0.0, -1.0), (2.0, 0.0, -2.0), (1.0, 1.0, -3.0)]) is None)

# --- стоящий корабль у станции -------------------------------------------
from patrol import Standing, make_standing

ws = World()
st = make_standing(ws, (255, 212, 128))
check("стоящий корабль стоит в 10 кл от кромки станции",
      abs(ws.dist_to_station(st.pos[0], st.pos[1]) - 10.0) < 1e-9,
      "%.4f кл, клетка (%d,%d)" % (ws.dist_to_station(st.pos[0], st.pos[1]),
                                   int(st.pos[0]), int(st.pos[1])))
pos_s = st.pos
for _ in range(120):
    st.update(1.0 / 60.0)
check("стоящий корабль именно стоит, а не летает", st.pos == pos_s, str(st.pos))
check("стоящий корабль не мешает курсу захода",
      not any(abs(st.pos[0] - 57.5) < 3.0 and abs(st.pos[1] - gy) < 3.0
              for gy in range(30, 48)),
      "он в клетке (%d,%d), коридор захода — x=57" % (int(st.pos[0]),
                                                      int(st.pos[1])))

# он рисуется тем же кодом, что патрули: в кадре должен быть его силуэт
from config import C_PATROL_D
canvas_s = pygame.Surface((CANVAS_W, CANVAS_H))
sh_s = Ship(64, 32, 0)
sh_s.snap()
stars_s = render.make_starfield(20261007)
render.draw_frame(canvas_s, ws, sh_s, stars_s, 2.0, patrols=[st])
hull_s = [(x, y) for y in range(6, 140) for x in range(4, 316)
          if tuple(canvas_s.get_at((x, y))[:3]) in ((255, 212, 128), C_PATROL_D)]
check("стоящий корабль виден в кадре с курса захода", len(hull_s) > 100,
      "пикселей корпуса %d" % len(hull_s))

# дрейф мимо него: силуэт должен ехать по экрану ровно, без переворотов
prev_c = None
worst_step = 0.0
sizes = []
for gx_ in range(58, 71):
    sh_d2 = Ship(gx_, 32, 0)
    sh_d2.snap()
    cv_s = pygame.Surface((CANVAS_W, CANVAS_H))
    render.draw_frame(cv_s, ws, sh_d2, stars_s, 2.0, patrols=[st])
    pts = [(x, y) for y in range(6, 140) for x in range(4, 316)
           if tuple(cv_s.get_at((x, y))[:3]) in ((255, 212, 128), C_PATROL_D)]
    if len(pts) < 60:
        worst_step = 99.0
        break
    cx_ = sum(p[0] for p in pts) / float(len(pts))
    cy_ = sum(p[1] for p in pts) / float(len(pts))
    sizes.append((max(p[0] for p in pts) - min(p[0] for p in pts),
                  max(p[1] for p in pts) - min(p[1] for p in pts)))
    if prev_c is not None:
        worst_step = max(worst_step, abs(cx_ - prev_c[0]) - 26.0)
    prev_c = (cx_, cy_)
check("силуэт стоящего корабля едет по экрану без переворотов",
      worst_step < 6.0 and len(sizes) == 13,
      "лишний скачок центра %.1f px за клетку (сам снос — 23-24 px), "
      "габарит от %dx%d до %dx%d"
      % (worst_step, min(s[0] for s in sizes), min(s[1] for s in sizes),
         max(s[0] for s in sizes), max(s[1] for s in sizes)))

# --- шрифт --------------------------------------------------------------
hud = ["ДО СТАНЦИИ 17,5 КЛ", "КУРС 045°  ХОД 65",
       "A D < > ПОВОРОТ 45   Q E СНОС", "СТАНЦИЯ 16,6", "СТОЛКНОВЕНИЕ",
       "РАДАР"]
bad = []
for line in hud:
    for ch in line:
        if ch != " " and pf.glyph(ch) is pf.GLYPHS["?"]:
            bad.append(ch)
check("в HUD нет символов, рисующихся как '?'", not bad, "".join(sorted(set(bad))))

print()
print("итог: %d проверок, провалов %d" % (COUNT[0], len(FAIL)))
sys.exit(1 if FAIL else 0)
