# -*- coding: utf-8 -*-
"""Корабль: логика — в клетках сетки, визуал — сглаженный.

Клавиши приходят сюда готовыми действиями ("fwd"/"back"/"left"/"right"/
"turn_l"/"turn_r"). Раскладку разбирает main.py по СКАН-КОДАМ физических
клавиш: при русской раскладке SDL отдаёт на клавишу W символ «ц» (1094), и
проверка по `K_w` молча не срабатывает — WASD «не работает», а стрелки живы.

Курс кратен TURN_STEP (45 градусов, 8 направлений). Шаг идёт в соседнюю
клетку: по прямой — на 1 клетку, по диагонали — на 1,41; время шага
пропорционально длине, поэтому скорость не зависит от направления.
"""

import math

from config import (LERP_POS, LERP_YAW, STEP_REPEAT, TURN_REPEAT, TURN_STEP,
                    WARN_TIME)

STEP_ACTIONS = ("fwd", "back", "left", "right")


class Ship:
    """Позиция логически привязана к клетке сетки, курс — к шагу поворота."""

    def __init__(self, gx, gy, yaw=0):
        self.gx, self.gy = gx, gy
        self.yaw = yaw % 360
        self.fx = gx + 0.5           # визуальная позиция (мировые координаты)
        self.fy = gy + 0.5
        self.fyaw = float(self.yaw)  # визуальный курс
        self.move_cool = 0.0         # таймер повторов шага
        self.turn_cool = 0.0         # таймер повторов поворота
        self.warn_t = 0.0            # таймер надписи о столкновении
        self.steps = 0               # сколько шагов сделано
        self.blocks = 0              # сколько шагов отбито станцией
        self.turns = 0               # сколько поворотов сделано
        self.step_time = STEP_REPEAT  # сколько «стоил» последний шаг
        self.lit = 0.0               # счётчик времени для мигалок
        self.hit_t = 0.0             # сколько ещё показывать «меня сбили»
        self.hit_msg = ""            # что написать на экране после гибели

    # --- логика ---------------------------------------------------------
    def world(self):
        return self.gx + 0.5, self.gy + 0.5

    def forward_xy(self):
        a = math.radians(self.yaw)
        return math.sin(a), math.cos(a)

    def right_xy(self):
        a = math.radians(self.yaw)
        return math.cos(a), -math.sin(a)

    def target_cell(self, kind):
        """Клетка, в которую ведёт шаг. На 45 градусах это диагональ."""
        fx, fy = self.forward_xy()
        rx, ry = self.right_xy()
        if kind == "fwd":
            d = (fx, fy)
        elif kind == "back":
            d = (-fx, -fy)
        elif kind == "left":
            d = (-rx, -ry)
        elif kind == "right":
            d = (rx, ry)
        else:
            raise ValueError(kind)
        return self.gx + int(round(d[0])), self.gy + int(round(d[1]))

    def try_move(self, kind, world):
        """Шаг на соседнюю клетку. True, если шаг состоялся."""
        tx, ty = self.target_cell(kind)
        dx, dy = tx - self.gx, ty - self.gy
        ok = not world.solid(tx, ty)
        if ok and dx and dy:
            # по диагонали не срезаем угол между двумя занятыми клетками
            if world.solid(self.gx + dx, self.gy) or world.solid(self.gx, self.gy + dy):
                ok = False
        if not ok:
            self.blocks += 1
            self.warn_t = WARN_TIME
            self.step_time = STEP_REPEAT
            return False
        self.step_time = STEP_REPEAT * math.hypot(dx, dy)
        self.gx, self.gy = tx, ty
        self.steps += 1
        return True

    def turn(self, delta):
        self.yaw = (self.yaw + delta) % 360
        self.turns += 1

    # --- кадр -----------------------------------------------------------
    def update(self, dt, acts=None, world=None):
        if self.warn_t > 0.0:
            self.warn_t = max(0.0, self.warn_t - dt)
        if self.hit_t > 0.0:
            self.hit_t = max(0.0, self.hit_t - dt)
        self.lit += dt

        if acts is not None and world is not None:
            if "turn_l" in acts or "turn_r" in acts:
                self.turn_cool -= dt
                if self.turn_cool <= 0.0:
                    self.turn(-TURN_STEP if "turn_l" in acts else TURN_STEP)
                    self.turn_cool = TURN_REPEAT
            else:
                self.turn_cool = 0.0
            self.move_cool -= dt
            if self.move_cool <= 0.0:
                for kind in STEP_ACTIONS:
                    if kind in acts:
                        moved = self.try_move(kind, world)
                        self.move_cool = self.step_time if moved else STEP_REPEAT
                        break

        k = min(1.0, dt * LERP_POS)
        self.fx += (self.gx + 0.5 - self.fx) * k
        self.fy += (self.gy + 0.5 - self.fy) * k

        dyaw = ((self.yaw - self.fyaw + 180.0) % 360.0) - 180.0
        self.fyaw = (self.fyaw + dyaw * min(1.0, dt * LERP_YAW)) % 360.0

    def snap(self):
        """Мгновенно догнать логику (для снимков без анимации)."""
        self.fx, self.fy = self.gx + 0.5, self.gy + 0.5
        self.fyaw = float(self.yaw)
