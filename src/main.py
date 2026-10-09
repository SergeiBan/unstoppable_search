# -*- coding: utf-8 -*-
"""unstoppable_search — этап 1: космос, одна станция 20x20, вид из кабины.

Обычный запуск:      ./run.sh           (или .venv/bin/python src/main.py)
Снимки для проверки: .venv/bin/python src/main.py --shots shots/stage1 --perf
"""

import argparse
import hashlib
import math
import os
import random
import sys
import time

import pygame
from pygame.locals import K_ESCAPE, K_F1, K_F2


def _sc(name, default):
    """Скан-код физической клавиши (число в скобках — резерв на случай,
    если константы в pygame-ce не объявлены)."""
    return getattr(pygame, name, default)


# Движение разбираем по СКАН-КОДАМ, а не по кодам символов: при русской
# раскладке на клавишу W приходит «ц» (1094), K_w (119) не срабатывает, и
# WASD молча умирает, хотя стрелки работают.
# A/D (и <>) — поворот на 45, Q/E — дрейф влево/вправо.
KEY_ACTIONS = {
    _sc("KSCAN_W", 26): "fwd", _sc("KSCAN_UP", 82): "fwd",
    _sc("KSCAN_S", 22): "back", _sc("KSCAN_DOWN", 81): "back",
    _sc("KSCAN_A", 4): "turn_l", _sc("KSCAN_D", 7): "turn_r",
    _sc("KSCAN_Q", 20): "left", _sc("KSCAN_E", 8): "right",
    _sc("KSCAN_LEFT", 80): "turn_l", _sc("KSCAN_RIGHT", 79): "turn_r",
}

# Огонь и ввод ответа — тоже по скан-кодам: раскладка на них не влияет.
# Цифры берём И с верхнего ряда, И с цифровой клавиатуры справа от Enter: у неё
# собственные скан-коды (KSCAN_KP_*), и без них набранный на ней ответ просто не
# доходил до игры.
FIRE_SCAN = _sc("KSCAN_SPACE", 44)
BACKSPACE_SCAN = _sc("KSCAN_BACKSPACE", 42)
MINUS_SCAN = _sc("KSCAN_MINUS", 45)
DIGIT_SCANS = {
    # верхний ряд
    _sc("KSCAN_0", 39): "0", _sc("KSCAN_1", 30): "1", _sc("KSCAN_2", 31): "2",
    _sc("KSCAN_3", 32): "3", _sc("KSCAN_4", 33): "4", _sc("KSCAN_5", 34): "5",
    _sc("KSCAN_6", 35): "6", _sc("KSCAN_7", 36): "7", _sc("KSCAN_8", 37): "8",
    _sc("KSCAN_9", 38): "9",
    # цифровая клавиатура (NumPad) справа от Enter
    _sc("KSCAN_KP_0", 98): "0", _sc("KSCAN_KP_1", 89): "1",
    _sc("KSCAN_KP_2", 90): "2", _sc("KSCAN_KP_3", 91): "3",
    _sc("KSCAN_KP_4", 92): "4", _sc("KSCAN_KP_5", 93): "5",
    _sc("KSCAN_KP_6", 94): "6", _sc("KSCAN_KP_7", 95): "7",
    _sc("KSCAN_KP_8", 96): "8", _sc("KSCAN_KP_9", 97): "9",
    _sc("KSCAN_KP_MINUS", 86): "-",
}

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import duel as D
import pixel_font as pf
import render
from config import (CANVAS_H, CANVAS_W, C_PATROL_A, C_PATROL_B, DUEL_PAUSE,
                    FIRE_RANGE, FPS, SHIP_START_GX, SHIP_START_GY,
                    SHIP_START_YAW, TURN_STEP)
from patrol import hidden as patrol_hidden
from patrol import make_patrols, make_standing
from ship import Ship
from world import World


def build_state(seed=20261007):
    world = World()
    ship = Ship(SHIP_START_GX, SHIP_START_GY, SHIP_START_YAW)
    stars = render.make_starfield(seed)
    patrols = make_patrols(world, (C_PATROL_A, C_PATROL_B))
    standing = make_standing(world, C_PATROL_B)
    # Патрульные — одна фракция: ударишь одного, встанут все. Пока фракция
    # нейтральная (сама огня не открывает), вражда начинается с выстрела игрока.
    faction = D.Faction("патруль")
    for p in patrols + [standing]:
        p.faction = faction
    return world, ship, stars, patrols, standing


def engage(fight, ships, target, dead):
    """Враждебные корабли, подошедшие на дистанцию боя, вступают в бой сами.

    Так враг «стремится напасть»: как только фракция стала враждебной и корабль
    подошёл на FIRE_RANGE, у него появляется свой поединок — и он стреляет в
    свою очередь, даже если игрок в него не целился. Возвращает тех, кто вступил
    в этот кадр: это можно проверить тестом без окна.
    """
    joined = []
    for p in ships:
        if id(p) in dead:
            continue
        fac = getattr(p, "faction", None)
        if fac is None or not fac.at_war():
            continue
        if math.hypot(p.pos[0] - target[0], p.pos[1] - target[1]) > FIRE_RANGE:
            continue
        if any(d.target is p for d in fight.duels):
            continue
        fight.start(p, make_active=not fight.duels)
        joined.append(p)
    return joined


def new_canvas():
    return pygame.Surface((CANVAS_W, CANVAS_H))


class Input:
    """Состояние органов управления по скан-кодам физических клавиш.

    Отдельный класс, чтобы это можно было проверить тестом: подсунуть событие
    с key=1094 («ц») и scancode=26 (физическая W) и убедиться, что корабль
    всё равно поедет вперёд.
    """

    def __init__(self):
        self.held = set()

    def handle(self, e):
        """Разобрать событие. True, если это была клавиша управления."""
        if e.type == pygame.KEYDOWN:
            if e.scancode in KEY_ACTIONS:
                self.held.add(e.scancode)
                return True
        elif e.type == pygame.KEYUP:
            self.held.discard(e.scancode)
        elif e.type == pygame.WINDOWFOCUSLOST:
            self.held.clear()          # иначе клавиши «залипают»
        return False

    def acts(self):
        return {KEY_ACTIONS[sc] for sc in self.held if sc in KEY_ACTIONS}


def present(screen, canvas):
    """Целочисленный апскейл с чёрными полями (без растяжки пропорций)."""
    sw, sh = screen.get_size()
    k = max(1, min(sw // CANVAS_W, sh // CANVAS_H))
    if k > 1:
        src = pygame.transform.scale(canvas, (CANVAS_W * k, CANVAS_H * k))
    else:
        src = canvas
    screen.fill((0, 0, 0))
    screen.blit(src, ((sw - CANVAS_W * k) // 2, (sh - CANVAS_H * k) // 2))


# --- интерактивный режим ------------------------------------------------
def run_window(args):
    pygame.init()
    info = pygame.display.Info()
    # на рабочем столе с масштабом 2.0 логический холст 960x540: оставляем запас
    # на заголовок окна, иначе масштаб 3 не влезет и окно выйдет за экран
    k = max(1, min(info.current_w // CANVAS_W, (info.current_h - 90) // CANVAS_H))
    if args.scale:
        k = max(1, args.scale)
    screen = pygame.display.set_mode((CANVAS_W * k, CANVAS_H * k), pygame.RESIZABLE)
    # ОС может ужать окно (заголовок, панели), и тогда целочисленный масштаб
    # перестаёт совпадать — пересчитываем по фактическому размеру, чтобы кадр
    # занимал окно без лишних чёрных полей
    k2 = max(1, min(screen.get_width() // CANVAS_W, screen.get_height() // CANVAS_H))
    if k2 != k:
        k = k2
        screen = pygame.display.set_mode((CANVAS_W * k, CANVAS_H * k), pygame.RESIZABLE)
    pygame.display.set_caption("unstoppable_search")
    canvas = new_canvas()
    world, ship, stars, patrols, standing = build_state(args.seed)
    clock = pygame.time.Clock()
    t = 0.0
    show_fps = bool(args.fps)
    shot_n = 0
    frame = 0
    print("окно %dx%d, масштаб %d (логический стол %dx%d)" % (
        CANVAS_W * k, CANVAS_H * k, k, info.current_w, info.current_h))
    running = True
    inp = Input()
    ships = patrols + [standing]
    fight = D.Fight()
    dead = set()                     # id() уничтоженных: их больше не рисуем

    def pick_target():
        """По кому стреляем: ближайший корабль в прицеле и в зоне огня."""
        fx, fy = ship.forward_xy()
        cam = render.Camera(ship.fx, ship.fy, ship.fyaw)
        best, best_d = None, FIRE_RANGE
        for p in ships:
            if id(p) in dead:
                continue
            dx, dy = p.pos[0] - ship.fx, p.pos[1] - ship.fy
            d = math.hypot(dx, dy)
            if d < 1e-6 or d > best_d:
                continue
            if (dx * fx + dy * fy) / d < 0.86:
                continue             # цель дальше 30° от прицела
            if patrol_hidden(cam, world, p.pos):
                continue             # за станцией — не достать
            best, best_d = p, d
        return best

    def fire():
        tgt = pick_target()
        if tgt is None:
            ship.hit_msg = "НЕТ ЦЕЛИ В ПРИЦЕЛЕ"
            ship.hit_t = 1.2
            return
        fight.start(tgt)
        fac = getattr(tgt, "faction", None)
        if fac is not None and fac.player_fired():
            for p in ships:          # первая атака злит всю фракцию
                if (p is not tgt and id(p) not in dead
                        and getattr(p, "faction", None) is fac):
                    fight.start(p, make_active=False)
        fight.player_fire()

    def apply_events():
        for kind, target in fight.take_events():
            if kind == "enemy_down":
                dead.add(id(target))
                if hasattr(target, "blocked_cells"):
                    world.unblock_cells(target.blocked_cells())
                ship.hit_msg = "ВРАГ УНИЧТОЖЕН"
                ship.hit_t = 1.4
            elif kind == "player_down":
                ship.gx, ship.gy, ship.yaw = (SHIP_START_GX, SHIP_START_GY,
                                              SHIP_START_YAW)
                ship.snap()
                ship.hit_msg = "ВАС СБИЛИ — ВОЗВРАТ НА СТАНЦИЮ"
                ship.hit_t = 2.2
            elif kind == "repelled":
                ship.hit_msg = "ВЫСТРЕЛ ОТБИТ СИЛОВЫМ ПОЛЕМ"
                ship.hit_t = 1.0
            elif kind == "shot_repelled":
                ship.hit_msg = "ОТБИТО!"
                ship.hit_t = 0.9

    while running:
        dt = min(clock.tick(FPS) / 1000.0, 0.05)
        frame += 1
        if args.frames and frame > args.frames:
            running = False
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
            elif e.type == pygame.KEYDOWN and e.key == K_ESCAPE:
                running = False
            elif e.type == pygame.KEYDOWN and e.key == K_F1:
                show_fps = not show_fps
            elif e.type == pygame.KEYDOWN and e.key == K_F2:
                shot_n += 1
                os.makedirs("shots/user", exist_ok=True)
                pygame.image.save(canvas, "shots/user/shot%02d.png" % shot_n)
            elif e.type == pygame.KEYDOWN and e.scancode in DIGIT_SCANS:
                fight.type_digit(DIGIT_SCANS[e.scancode])
            elif e.type == pygame.KEYDOWN and e.scancode == BACKSPACE_SCAN:
                fight.backspace()
            elif e.type == pygame.KEYDOWN and e.scancode == MINUS_SCAN:
                fight.type_digit("-")
            elif e.type == pygame.KEYDOWN and e.scancode == FIRE_SCAN:
                fire()
            elif inp.handle(e):
                # первый шаг/поворот — сразу, без паузы повтора
                ship.move_cool = 0.0
                ship.turn_cool = 0.0
        ship.update(dt, inp.acts(), world)
        at_war = any(getattr(p, "faction", None) is not None
                     and p.faction.at_war() for p in ships)
        for p in patrols:
            p.update(dt, (ship.fx, ship.fy), at_war)
        engage(fight, ships, (ship.fx, ship.fy), dead)
        for d in list(fight.duels):
            if d.too_far((ship.fx, ship.fy)):
                fight.drop(d.target)          # враг ушёл из зоны боя
        fight.update(dt)
        apply_events()
        t += dt
        render.draw_frame(canvas, world, ship, stars, t,
                          int(clock.get_fps()) if show_fps else None,
                          patrols=[p for p in ships if id(p) not in dead],
                          fight=fight)
        present(screen, canvas)
        pygame.display.flip()
        if args.save_frame:
            # читаем именно поверхность окна — проверка реального пути вывода
            pygame.image.save(screen, args.save_frame)
            print("кадр окна сохранён: %s (%dx%d)" % (
                args.save_frame, screen.get_width(), screen.get_height()))
            running = False
    pygame.quit()


# --- прогон со снимками (headless) --------------------------------------
def run_shots(args):
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((CANVAS_W, CANVAS_H))
    canvas = new_canvas()
    world, ship, stars, patrols, standing = build_state(args.seed)
    out = args.shots
    os.makedirs(out, exist_ok=True)
    dt = 1.0 / FPS
    frames_per_step = 10
    t = [0.0]
    rows = []
    hashes = []
    n = [0]
    fight = None                    # бой: понадобится для кадров поединка

    def draw():
        t[0] += dt
        ship.update(dt)
        at_war = any(getattr(p, "faction", None) and p.faction.at_war()
                     for p in patrols)
        for p in patrols:
            p.update(dt, (ship.fx, ship.fy), at_war)
        render.draw_frame(canvas, world, ship, stars, t[0],
                          patrols=patrols + [standing], fight=fight)

    def shot(label):
        ship.snap()
        draw()
        fn = "%02d_%s.png" % (n[0], label)
        path = os.path.join(out, fn)
        big = pygame.transform.scale(canvas, (CANVAS_W * 3, CANVAS_H * 3))
        pygame.image.save(big, path)
        with open(path, "rb") as f:
            hashes.append((fn, hashlib.md5(f.read()).hexdigest()[:10]))
        n[0] += 1
        rows.append((label, ship.gx, ship.gy, ship.yaw,
                     world.dist_to_station(ship.fx, ship.fy),
                     ship.steps, ship.blocks, len(_visible_faces(world, ship))))

    def do(kind, count):
        for _ in range(count):
            if kind == "turn_r":
                ship.turn(TURN_STEP)
            elif kind == "turn_l":
                ship.turn(-TURN_STEP)
            else:
                ship.try_move(kind, world)
            ship.snap()
            for _ in range(frames_per_step):
                draw()

    shot("01_старт")
    do("fwd", 12)
    shot("02_подлёт_5_клеток")
    do("fwd", 8)
    shot("03_контакт_со_станцией")
    do("turn_r", 2)
    do("fwd", 12)
    shot("04_полёт_вдоль_стены")
    do("turn_r", 2)
    do("fwd", 26)
    shot("05_уходим_в_космос")
    do("turn_l", 2)
    do("fwd", 9)
    do("turn_l", 2)
    do("fwd", 10)
    shot("06_вид_сбоку_на_станцию")
    # полёт по диагонали: курс 45 градусов, шаг идёт в соседнюю клетку наискось
    ship.gx, ship.gy, ship.yaw = SHIP_START_GX, SHIP_START_GY, SHIP_START_YAW
    ship.snap()
    do("turn_r", 1)
    do("fwd", 8)
    shot("07_полёт_по_диагонали")
    # издалека: проверяем, что детали есть и на мелких гранях боковой стены
    ship.gx, ship.gy, ship.yaw = SHIP_START_GX, -8, SHIP_START_YAW
    ship.snap()
    draw()
    shot("08_издали_по_курсу")
    ship.gx, ship.gy, ship.yaw = 85, 30, 315
    ship.snap()
    draw()
    shot("09_издали_сбоку")
    # патруль вблизи: встаём в 6 клетках перед первым патрулём
    p0 = patrols[0]
    ship.gx, ship.gy = int(p0.pos[0]), int(p0.pos[1]) - 6
    ship.yaw = 0
    ship.snap()
    draw()
    shot("10_патруль_вблизи")
    # широкая картинка: оба патруля выставляем на южные участки орбит,
    # чтобы они попали в кадр по курсу
    patrols[0].s = 10.0
    patrols[1].s = 10.0
    for q in patrols:
        q.update(0.0)
    ship.gx, ship.gy, ship.yaw = SHIP_START_GX, 8, SHIP_START_YAW
    ship.snap()
    draw()
    shot("11_оба_патруля_по_курсу")
    # спиной к станции — тот самый кадр, на котором фон заливался серым
    for gy_s, lab in ((46, "12_спиной_к_станции_вплотную"),
                      (45, "13_спиной_к_станции_1_клетка")):
        ship.gx, ship.gy, ship.yaw = 57, gy_s, 180
        ship.snap()
        draw()
        shot(lab)
    # стоящий корабль у станции: с курса захода и рядом с ним
    for gx_s, gy_s, yaw_s, lab in ((64, 32, 0, "14_стоящий_корабль_по_курсу"),
                                   (61, 33, 0, "15_стоящий_корабль_рядом")):
        ship.gx, ship.gy, ship.yaw = gx_s, gy_s, yaw_s
        ship.snap()
        draw()
        shot(lab)
    # упор в стоящий корабль: шаг в его клетку отбит, в кадре предупреждение
    ship.gx, ship.gy, ship.yaw = 64, 37, 0
    ship.snap()
    ship.try_move("fwd", world)
    shot("16_упор_в_стоящий_корабль")
    # поединок: игрок стреляет по стоящему кораблю, тот отбивает выстрел
    # силовым полем и задаёт задачу (генератор с фиксированным зерном)
    fight = D.Fight(rng=random.Random(3))
    ship.gx, ship.gy, ship.yaw = 64, 34, 0
    ship.snap()
    fight.start(standing)
    fight.player_fire()                 # 0.238 < 0.5 — NPC отбил выстрел
    fight.update(DUEL_PAUSE + 0.01)     # враг навёлся и задал задачу
    draw()
    shot("17_бой_задача")
    for ch in str(fight.current.problem.answer):   # верный ответ — отбито
        fight.type_digit(ch)
    draw()
    shot("18_бой_отбит_полем")
    # патрули стали врагами и идут на игрока, а не кружат вокруг станции
    war = D.Faction("патруль")
    war.angry = True
    for p in patrols:
        p.faction = war
    standing.faction = war
    ship.gx, ship.gy, ship.yaw = 57, 30, 0
    ship.snap()
    for _ in range(420):                    # 7 секунд погони
        for p in patrols:
            p.update(1.0 / FPS, (ship.fx, ship.fy), True)
    draw()
    shot("19_патрули_идут_на_игрока")

    print("каталог снимков: %s" % os.path.abspath(out))
    print("станция: %d x %d = %d клеток, квадрат=%s" % (
        world.sx1 - world.sx0, world.sy1 - world.sy0, world.area(),
        (world.sx1 - world.sx0) == (world.sy1 - world.sy0)))
    print("старт: клетка (%d,%d) курс %d, до станции %.1f кл" % (
        SHIP_START_GX, SHIP_START_GY, SHIP_START_YAW,
        world.dist_to_station(SHIP_START_GX + 0.5, SHIP_START_GY + 0.5)))
    print()
    print("%-24s %10s %6s %8s %7s %6s %9s" % (
        "снимок", "клетка", "курс", "до ст.", "шагов", "отказ", "граней"))
    for label, gx, gy, yaw, d, steps, blocks, faces in rows:
        print("%-24s %10s %6d %8.2f %7d %6d %9d" % (
            label, "(%d,%d)" % (gx, gy), yaw, d, steps, blocks, faces))
    print()
    uniq = len(set(h for _, h in hashes))
    print("кадры: %d, уникальных по md5: %d" % (len(hashes), uniq))
    for fn, h in hashes:
        print("  %-30s %s" % (fn, h))
    if uniq != len(hashes):
        print("ВНИМАНИЕ: часть кадров совпала — рисование кадра пропущено")

    print()
    for p in patrols:
        d = world.dist_to_station(*p.pos)
        ds = math.hypot(p.pos[0] - ship.fx, p.pos[1] - ship.fy)
        print("%-20s расстояние до станции %.3f кл (задано %.1f) | "
              "от корабля %.1f кл | маршрут %.1f кл" % (
                  p.name, d, p.margin, ds, p.path.total))

    if args.perf:
        print()
        for label, gx, gy, yaw in (("старт 17.5 кл", SHIP_START_GX, SHIP_START_GY, 0),
                                   ("подлёт 5.5 кл", SHIP_START_GX, 42, 0),
                                   ("в упор 0.5 кл", SHIP_START_GX, 47, 0),
                                   ("стена вбок", SHIP_START_GX + 12, 47, 90),
                                   ("издали 55 кл", SHIP_START_GX, -8, 0),
                                   ("издали сбоку 25 кл", 85, 30, 315)):
            ship.gx, ship.gy, ship.yaw = gx, gy, yaw
            ship.snap()
            for _ in range(20):
                draw()
            t0 = time.perf_counter()
            for _ in range(40):
                draw()
            ms = (time.perf_counter() - t0) * 1000.0 / 40.0
            print("кадр %-14s %.2f мс  (граней %d)" % (
                label, ms, len(_visible_faces(world, ship))))
        print("бюджет: 8-10 мс на кадр при 60 к/с")
    pygame.quit()


def _visible_faces(world, ship):
    cam = render.Camera(ship.gx + 0.5, ship.gy + 0.5, ship.yaw)
    return render.station_faces(world, cam)


def main():
    ap = argparse.ArgumentParser(description="unstoppable_search")
    ap.add_argument("--shots", metavar="КАТАЛОГ", help="headless-прогон со снимками")
    ap.add_argument("--frames", type=int, default=0,
                    help="выйти через N кадров (0 — без ограничения)")
    ap.add_argument("--scale", type=int, default=0, help="масштаб окна вручную")
    ap.add_argument("--save-frame", metavar="ФАЙЛ",
                    help="сохранить первый кадр окна и выйти")
    ap.add_argument("--seed", type=int, default=20261007)
    ap.add_argument("--fps", action="store_true", help="показывать к/с (или --perf)")
    ap.add_argument("--perf", action="store_true", help="замерить время кадра")
    args = ap.parse_args()
    if args.shots:
        run_shots(args)
    else:
        run_window(args)


if __name__ == "__main__":
    main()
