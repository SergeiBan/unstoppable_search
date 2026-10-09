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
from config import (CANVAS_H, CANVAS_W, C_PATROL_D, C_WIN, DEATH_PAUSE,
                    DUEL_PATIENCE, DUEL_PAUSE, DUEL_RANGE, DUEL_TIME, FOCAL, FPS,
                    PATROL_R, SHIP_START_GX, SHIP_START_GY, SHIP_START_YAW,
                    STEP_REPEAT, TURN_REPEAT, TURN_STEP)
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

# Цифровая клавиатура справа от Enter шлёт СВОИ скан-коды: без них ответ,
# набранный на ней, до игры не доходил.
kpad = {98: "0", 89: "1", 90: "2", 91: "3", 92: "4",
        93: "5", 94: "6", 95: "7", 96: "8", 97: "9"}
top_row = {39: "0", 30: "1", 31: "2", 32: "3", 33: "4",
           34: "5", 35: "6", 36: "7", 37: "8", 38: "9"}
check("цифры принимаются и с верхнего ряда, и с цифровой клавиатуры",
      all(M.DIGIT_SCANS.get(sc) == ch for sc, ch in kpad.items())
      and all(M.DIGIT_SCANS.get(sc) == ch for sc, ch in top_row.items()),
      "KP-1=%s, 1=%s, KP-0=%s, 0=%s" % (M.DIGIT_SCANS.get(89), M.DIGIT_SCANS.get(30),
                                        M.DIGIT_SCANS.get(98), M.DIGIT_SCANS.get(39)))
check("ввод ответа задан скан-кодами (<= 512)",
      all(0 <= k < 512 for k in M.DIGIT_SCANS), str(sorted(M.DIGIT_SCANS)))
check("коды цифр с двух клавиатур не конфликтуют между собой",
      len(set(kpad) & set(top_row)) == 0 and M.DIGIT_SCANS.get(86) == "-")

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


def ship_pixels(with_ship, without_ship):
    """Пиксели корабля: всё, чем кадр с кораблём отличается от кадра без него.

    Так надёжнее, чем угадывать палитру: у станции есть свои цвета, и любой
    список «цветов корабля» нет-нет да и совпадёт с каким-нибудь её пикселем.
    """
    pts = []
    for y in range(6, 140):
        for x in range(4, 316):
            if with_ship.get_at((x, y))[:3] != without_ship.get_at((x, y))[:3]:
                pts.append((x, y))
    return pts


cv_empty = pygame.Surface((CANVAS_W, CANVAS_H))
render.draw_frame(cv_empty, w, sh, stars, 1.0)
free_sky = cv_empty.copy()
fake.pos = (58.0, 30.0)
render.draw_frame(canvas, w, sh, stars, 1.0, patrols=[fake])
near = len(ship_pixels(canvas, free_sky))
check("патруль в кадре виден", near > 30, "пикселей %d" % near)
fake.pos = (58.0, 75.0)                  # за станцией
fake.s = 1.0
render.draw_frame(canvas, w, sh, stars, 1.0, patrols=[fake])
check("патруль за станцией не рисуется",
      len(ship_pixels(canvas, free_sky)) < 8,
      "пикселей %d" % len(ship_pixels(canvas, free_sky)))

# огня у корабля нет вовсе: спрайт не выходит за габарит самой тарелки
# (ни ореола вокруг, ни факела сзади), и летящий со стоящим выглядят одинаково
sh_h = Ship(64, 32, 0)
sh_h.snap()
render.draw_frame(cv_empty, w, sh_h, stars, 2.0)
free_sky = cv_empty.copy()
fake.pos = (64.5, 38.5)
fake.head = (1.0, 0.0)
render.draw_frame(canvas, w, sh_h, stars, 2.0, patrols=[fake])
fly = ship_pixels(canvas, free_sky)
still = P.Standing((64.5, 38.5), (1.0, 0.0), color=(150, 245, 255))
render.draw_frame(canvas, w, sh_h, stars, 2.0, patrols=[still])
stand = ship_pixels(canvas, free_sky)
r_px = FOCAL * PATROL_R / 6.5          # радиус тарелки на экране в 6,5 клетках
w_px = max(p[0] for p in fly) - min(p[0] for p in fly) + 1
h_px = max(p[1] for p in fly) - min(p[1] for p in fly) + 1
check("у корабля нет ни ореола, ни факела: спрайт не выходит за тарелку",
      w_px <= 2.4 * r_px + 6 and h_px <= 2.4 * r_px + 6
      and abs(len(fly) - len(stand)) < 0.25 * len(stand),
      "габарит %dx%d px при радиусе тарелки %.1f px; пикселей в полёте %d, "
      "на стоянке %d" % (w_px, h_px, r_px, len(fly), len(stand)))

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
check("стоящий корабль стоит в 9,5 кл от кромки станции (по центру клетки)",
      abs(ws.dist_to_station(st.pos[0], st.pos[1]) - 9.5) < 1e-9,
      "%.4f кл, клетка (%d,%d)" % (ws.dist_to_station(st.pos[0], st.pos[1]),
                                   int(st.pos[0]), int(st.pos[1])))
check("стоящий корабль занимает ровно свою клетку",
      st.blocked_cells() == [(64, 38)] and ws.solid(64, 38),
      "заняты клетки %s" % (st.blocked_cells(),))
pos_s = st.pos
for _ in range(120):
    st.update(1.0 / 60.0)
check("стоящий корабль именно стоит, а не летает", st.pos == pos_s, str(st.pos))
check("стоящий корабль не мешает курсу захода",
      not any(abs(st.pos[0] - 57.5) < 3.0 and abs(st.pos[1] - gy) < 3.0
              for gy in range(30, 48)),
      "он в клетке (%d,%d), коридор захода — x=57" % (int(st.pos[0]),
                                                      int(st.pos[1])))

# в его клетку не влететь: ни в лоб, ни сбоку
sh_i1 = Ship(64, 37, 0)
sh_i1.steps = 0
check("в стоящий корабль не влететь в лоб",
      not sh_i1.try_move("fwd", ws) and (sh_i1.gx, sh_i1.gy) == (64, 37)
      and sh_i1.blocks == 1 and sh_i1.warn_t > 0.0,
      "клетка (%d,%d), отказов %d, предупреждение %.1f с"
      % (sh_i1.gx, sh_i1.gy, sh_i1.blocks, sh_i1.warn_t))
sh_i2 = Ship(63, 38, 90)
sh_i2.steps = 0
check("в стоящий корабль не влететь сбоку",
      not sh_i2.try_move("fwd", ws) and (sh_i2.gx, sh_i2.gy) == (63, 38)
      and sh_i2.blocks == 1,
      "клетка (%d,%d), отказов %d" % (sh_i2.gx, sh_i2.gy, sh_i2.blocks))
check("мимо стоящего корабля пройти можно, а в станцию упереться всё ещё можно",
      ws.solid(64, 37) is False and ws.solid(64, 39) is False
      and ws.solid(57, 48) is True,
      "соседние клетки свободны, станция на месте")
# он стоит в стороне от курса захода: 17 шагов к станции по-прежнему проходят
w_c2 = World()
make_standing(w_c2, (255, 212, 128))
sh_c2 = Ship(57, 30, 0)
for _ in range(20):
    sh_c2.try_move("fwd", w_c2)
check("заход к станции не сломан стоящим кораблём",
      (sh_c2.gx, sh_c2.gy) == (57, 47), str((sh_c2.gx, sh_c2.gy)))

# он рисуется тем же кодом, что патрули: в кадре должна быть его тарелка
cv_s = pygame.Surface((CANVAS_W, CANVAS_H))
cv_f = pygame.Surface((CANVAS_W, CANVAS_H))
sh_s = Ship(64, 32, 0)
sh_s.snap()
stars_s = render.make_starfield(20261007)
render.draw_frame(cv_f, ws, sh_s, stars_s, 2.0)
render.draw_frame(cv_s, ws, sh_s, stars_s, 2.0, patrols=[st])
hull_s = len(ship_pixels(cv_s, cv_f))
check("стоящий корабль виден в кадре с курса захода", hull_s > 80,
      "пикселей корабля %d" % hull_s)

# дрейф мимо него: тарелка должна ехать по экрану ровно, без скачков центра
prev_c = None
worst_step = 0.0
sizes = []
for gx_ in range(58, 71):
    sh_d2 = Ship(gx_, 32, 0)
    sh_d2.snap()
    render.draw_frame(cv_f, ws, sh_d2, stars_s, 2.0)
    render.draw_frame(cv_s, ws, sh_d2, stars_s, 2.0, patrols=[st])
    pts = ship_pixels(cv_s, cv_f)
    if len(pts) < 40:
        worst_step = 99.0
        break
    cx_ = sum(p[0] for p in pts) / float(len(pts))
    cy_ = sum(p[1] for p in pts) / float(len(pts))
    sizes.append((max(p[0] for p in pts) - min(p[0] for p in pts),
                  max(p[1] for p in pts) - min(p[1] for p in pts)))
    if prev_c is not None:
        worst_step = max(worst_step, abs(cx_ - prev_c[0]) - 26.0)
    prev_c = (cx_, cy_)
check("тарелка стоящего корабля едет по экрану без скачков",
      worst_step < 6.0 and len(sizes) == 13,
      "лишний скачок центра %.1f px за клетку (сам снос — 23-24 px), "
      "габарит от %dx%d до %dx%d"
      % (worst_step, min(s[0] for s in sizes), min(s[1] for s in sizes),
         max(s[0] for s in sizes), max(s[1] for s in sizes)))

# --- поединки ------------------------------------------------------------
import random

import duel as D

rng_t = random.Random(1)
tasks = [D.Problem.make(1, rng_t) for _ in range(50)]
check("задача первого уровня — сложение двух чисел, ответ сходится",
      all(p.answer == p.a + p.b and 2 <= p.a <= 9 and 2 <= p.b <= 9
          for p in tasks),
      "пример: %s = %d" % (tasks[0].text(), tasks[0].answer))

f_neutral = D.Faction("патруль")
check("нейтральная фракция сама не воюет", f_neutral.at_war() is False)
check("выстрел по члену фракции злит всю фракцию",
      f_neutral.player_fired() is True and f_neutral.at_war() is True
      and f_neutral.player_fired() is False,
      "вражда включается ровно один раз")
check("враждебная фракция воюет без повода",
      D.Faction("пираты", hostile=True).at_war() is True)


class Doll:
    """Подставная цель: поединку от неё нужна только позиция."""

    def __init__(self):
        self.pos = (60.0, 30.0)


# выстрел игрока: NPC защищается примерно в половине случаев
N_TRIES = 400
downs = 0
for i in range(N_TRIES):
    d0 = D.Duel(Doll(), rng=random.Random(i))
    if d0.player_fire() == "enemy_down":
        downs += 1
check("NPC отбивает выстрел игрока примерно в половине случаев",
      0.42 < downs / float(N_TRIES) < 0.58,
      "уничтожен %d раз из %d, то есть защита %.0f%%"
      % (downs, N_TRIES, 100.0 * (1.0 - downs / float(N_TRIES))))

# отбитый выстрел передаёт ход врагу, враг наводится и задаёт задачу
d = D.Duel(Doll(), rng=random.Random(1))          # 0.134 < 0.5 — NPC отбил
check("отбитый выстрел передаёт ход врагу",
      d.player_fire() == "repelled" and d.state == "enemy_windup"
      and ("repelled", d.target) in d.take_events(),
      "состояние %s" % d.state)
d.update(DUEL_PAUSE + 0.01)
check("враг стреляет сам, и над ним встаёт задача",
      d.state == "enemy_asking" and d.problem is not None
      and abs(d.timer - DUEL_TIME) < 1e-9
      and ("enemy_shot", d.target) in d.take_events(),
      "задача %s, таймер %.2f с" % (d.problem.text(), d.timer))

# верный ответ: выстрел отбит, ход возвращается игроку
solved_all = True
for ch in str(d.problem.answer):
    solved_all = d.type_digit(ch)
check("верный ответ отбивает выстрел и возвращает ход игроку",
      solved_all and d.state == "player_turn" and d.solved == 1
      and ("shot_repelled", d.target) in d.take_events(),
      "состояние %s, решено %d" % (d.state, d.solved))

# ответ принимается СРАЗУ при наборе, без Ввода — и с цифровой клавиатуры
kp_of = {ch: sc for sc, ch in kpad.items()}
d_kp = D.Duel(Doll(), rng=random.Random(1))
d_kp.player_fire()
d_kp.update(DUEL_PAUSE + 0.01)
ans_kp = str(d_kp.problem.answer)
accepted_on = None
for i, ch in enumerate(ans_kp):
    if d_kp.type_digit(M.DIGIT_SCANS[kp_of[ch]]):
        accepted_on = i
check("ответ принимается сразу при наборе, без Ввода",
      accepted_on == len(ans_kp) - 1 and d_kp.state == "player_turn",
      "ответ %s, принят на %d-й цифре из %d" % (ans_kp, accepted_on + 1, len(ans_kp)))

d_one = D.Duel(Doll(), rng=random.Random(1))
d_one.problem = D.Problem(2, 3)           # ответ 5 — однозначный
d_one.state = "enemy_asking"
check("однозначный ответ отбивает выстрел первой же цифрой",
      d_one.type_digit("5") is True and d_one.state == "player_turn",
      "состояние %s" % d_one.state)

# просроченный ответ: игрок гибнет
d = D.Duel(Doll(), rng=random.Random(1))
d.player_fire()
d.update(DUEL_PAUSE + 0.01)
d.type_digit("0")                     # 0 не может быть ответом: слагаемые от 2
d.update(DUEL_TIME + 0.01)
check("не успел ответить — игрок гибнет и ход уходит врагу",
      ("player_down", d.target) in d.take_events()
      and d.state == "enemy_windup" and d.missed == 1,
      "состояние %s, провалов %d" % (d.state, d.missed))

# неверный ответ не засчитывается, но его можно стереть и исправить
d = D.Duel(Doll(), rng=random.Random(1))
d.player_fire()
d.update(DUEL_PAUSE + 0.01)
wrong = str(d.problem.answer + 1)
for ch in wrong:
    d.type_digit(ch)
check("неверный ответ выстрел не отбивает", d.state == "enemy_asking",
      "состояние %s" % d.state)
d.backspace()
check("забой стирает последний символ ответа", d.answer == wrong[:-1],
      "ответ «%s»" % d.answer)

# если игрок тянет, враг стреляет сам
d = D.Duel(Doll(), rng=random.Random(1))
d.update(DUEL_PATIENCE + 0.01)
check("если игрок тянет, враг начинает сам",
      d.state == "enemy_windup", "состояние %s" % d.state)
d.update(DUEL_PAUSE + 0.01)
check("после наведения враг действительно стреляет",
      d.state == "enemy_asking" and d.problem is not None,
      "состояние %s" % d.state)

# уничтожение врага заканчивает поединок
d = D.Duel(Doll(), rng=random.Random(0))          # 0.844 > 0.5 — NPC не отбил
check("если NPC не отбил, он уничтожен и поединок окончен",
      d.player_fire() == "enemy_down" and d.state == "done"
      and ("enemy_down", d.target) in d.take_events(),
      "состояние %s" % d.state)

# разрыв дистанции прерывает бой
d = D.Duel(Doll(), rng=random.Random(1))
check("бой распадается, если враг ушёл из зоны боя",
      d.too_far((60.0, 30.0 + DUEL_RANGE - 1.0)) is False
      and d.too_far((60.0, 30.0 + DUEL_RANGE + 1.0)) is True)

# бой с несколькими врагами: ход переходит по кругу, все стреляют по очереди
a1, a2, a3 = Doll(), Doll(), Doll()
f = D.Fight(rng=random.Random(1))
f.start(a1)
check("выстрел по одному завязывает поединок именно с ним",
      len(f.duels) == 1 and f.current.target is a1)
f.start(a2, make_active=False)
f.start(a3, make_active=False)
check("подмога встаёт в очередь, но ход остаётся у первого",
      len(f.duels) == 3 and f.current.target is a1,
      "врагов в бою %d, ход у %s" % (len(f.duels), "первого" if f.current.target is a1 else "другого"))
f.player_fire()                       # rng(1): 0.134 < 0.5 — отбито
f.update(DUEL_PAUSE + 0.01)           # враг дал задачу
for ch in str(f.current.problem.answer):
    f.type_digit(ch)
f.update(0.01)                        # события боя разбираются здесь
check("после отбитого выстрела ход переходит следующему врагу",
      f.current.target is a2 and f.duels[1].state == "player_turn",
      "теперь стреляет %s" % ("второй" if f.current.target is a2 else "другой"))
f.player_fire()
f.update(DUEL_PAUSE + 0.01)
for ch in str(f.current.problem.answer):
    f.type_digit(ch)
f.update(0.01)
check("круг идёт дальше: третий враг тоже получает ход",
      f.current.target is a3, "в бою врагов %d" % len(f.duels))

# уничтоженный враг выпадает из боя, а гибель игрока даёт передышку
f2 = D.Fight(rng=random.Random(0))     # 0.844 > 0.5 — враг не отбил
f2.start(a1)
f2.start(a2, make_active=False)
f2.player_fire()
f2.update(0.01)
check("уничтоженный враг выпадает из очереди",
      len(f2.duels) == 1 and f2.current.target is a2,
      "врагов осталось %d" % len(f2.duels))
f2.start(a3, make_active=False)
f2.current.state = "enemy_windup"      # враг наводится...
f2.current.timer = 0.01
f2.update(0.02)                        # ...и стреляет
f2.update(DUEL_TIME + 0.01)            # игрок не успел ответить
f2.update(0.01)
check("гибель игрока даёт врагам передышку и снимает задачу",
      all(d.state == "player_turn" and d.problem is None
          and d.timer > DEATH_PAUSE * 0.8 for d in f2.duels),
      "врагов %d, минимальный таймер %.1f с"
      % (len(f2.duels), min(d.timer for d in f2.duels)))

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
