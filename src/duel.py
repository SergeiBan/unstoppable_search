# -*- coding: utf-8 -*-
"""Поединки: перестрелка, где защита — это быстро решённая задача.

Правила первого уровня:
- Поединок начинается, когда игрок стреляет по кораблю. Корабли одной фракции
  заступаются друг за друга: атаковал одного — воюешь со всей фракцией.
- Кто выстрелил первым, тот и стреляет первым; дальше ход переходит по кругу.
- Когда стреляет NPC, над ним появляется арифметическая задача, и у игрока есть
  DUEL_TIME секунд, чтобы набрать ответ. Верный ответ — выстрел отбит силовым
  полем; неверный или просроченный — игрок гибнет и возрождается у станции.
- Когда стреляет игрок, NPC защищается с вероятностью NPC_DEFEND (у первого
  уровня 0,5): отбил — ход уходит к нему, не отбил — корабль уничтожен.

Модуль ничего не знает про отрисовку: он ведёт состояние поединка и выдаёт
события («отбит», «корабль уничтожен», «игрок погиб»), а применяет их main.
Так логику можно проверить тестом, не поднимая окно.
"""

import math
import random

from config import (DEATH_PAUSE, DUEL_PATIENCE, DUEL_PAUSE, DUEL_RANGE,
                    DUEL_TIME, NPC_DEFEND, TASK_MAX, TASK_MIN)


class Faction:
    """Фракция: у кого с кем война.

    Пока достаточно одного признака — враждебна ли фракция игроку. Он и решает,
    кто откроет огонь первым: пираты или стража запретной зоны стреляют сами, а
    нейтралы (например, патруль у своей станции) — только в ответ.
    """

    def __init__(self, name, hostile=False):
        self.name = name
        self.hostile = hostile      # стреляет без повода
        self.angry = False          # разозлилась после выстрела игрока

    def player_fired(self):
        """Игрок выстрелил по члену фракции. True — вражда началась только что."""
        was = self.at_war()
        self.angry = True
        return not was

    def at_war(self):
        return self.hostile or self.angry


class Problem:
    """Арифметическая задача. Первый уровень — сложение двух чисел."""

    def __init__(self, a, b):
        self.a, self.b = a, b
        self.answer = a + b

    def text(self):
        return "%d+%d" % (self.a, self.b)

    @staticmethod
    def make(level, rng):
        if level <= 1:
            return Problem(rng.randint(TASK_MIN, TASK_MAX),
                           rng.randint(TASK_MIN, TASK_MAX))
        raise ValueError("нет задач для уровня %r" % (level,))


class Duel:
    """Поединок с одним кораблём: ходы, задача врага, таймеры.

    Состояния:
      player_turn   — ход игрока: ждём выстрела (или он затянул и враг сам
                      начинает — иначе можно было бы тянуть вечно);
      enemy_windup  — враг наводится: короткая пауза перед его выстрелом;
      enemy_asking  — враг выстрелил: над ним задача, у игрока DUEL_TIME секунд;
      done          — поединок кончился (кто-то уничтожен).
    """

    def __init__(self, target, level=1, rng=None):
        self.target = target
        self.level = level
        self.rng = rng or random.Random()
        self.state = "player_turn"
        self.timer = DUEL_PATIENCE
        self.problem = None
        self.answer = ""
        self.events = []            # очередь событий, её забирает main
        self.flash = ""             # "repelled" | "hit" — для отрисовки
        self.flash_t = 0.0
        self.range_limit = DUEL_RANGE
        self.shots = 0              # сколько выстрелов сделано
        self.solved = 0             # сколько задач решено
        self.missed = 0             # сколько задач провалено

    # --- ход игрока ---------------------------------------------------
    def player_fire(self):
        """Игрок выстрелил. Работает только на его ходу. Возвращает итог."""
        if self.state != "player_turn":
            return None
        self.shots += 1
        if self.rng.random() < NPC_DEFEND:
            self._flash("repelled")
            self.events.append(("repelled", self.target))
            self._to_windup()
            return "repelled"
        self._flash("hit")
        self.events.append(("enemy_down", self.target))
        self.state = "done"
        return "enemy_down"

    def type_digit(self, ch):
        """Игрок набрал символ ответа. True — ответ оказался верным."""
        if self.state != "enemy_asking" or self.problem is None:
            return False
        if ch == "-" and self.answer:
            return False
        if len(self.answer) >= 4:
            return False
        self.answer += ch
        try:
            got = int(self.answer)
        except ValueError:
            return False
        if got == self.problem.answer:
            self.solved += 1
            self._flash("repelled")
            self.events.append(("shot_repelled", self.target))
            self._to_player()
            return True
        return False

    def backspace(self):
        if self.state == "enemy_asking" and self.answer:
            self.answer = self.answer[:-1]
            return True
        return False

    # --- время --------------------------------------------------------
    def update(self, dt):
        if self.flash_t > 0.0:
            self.flash_t = max(0.0, self.flash_t - dt)
        if self.state == "done":
            return
        self.timer -= dt
        if self.timer > 0.0:
            return
        if self.state == "player_turn":
            self._to_windup()           # игрок затянул — враг стреляет сам
        elif self.state == "enemy_windup":
            self._enemy_fire()
        elif self.state == "enemy_asking":
            self.missed += 1
            self.events.append(("player_down", self.target))
            self._flash("hit")
            self._to_windup()

    def too_far(self, pos):
        """Поединок распадается, если противник ушёл из зоны боя."""
        return math.hypot(self.target.pos[0] - pos[0],
                          self.target.pos[1] - pos[1]) > self.range_limit

    def take_events(self):
        out = self.events
        self.events = []
        return out

    # --- внутреннее ---------------------------------------------------
    def _enemy_fire(self):
        """Враг стреляет: над ним встаёт задача, включается таймер ответа."""
        self.problem = Problem.make(self.level, self.rng)
        self.answer = ""
        self.state = "enemy_asking"
        self.timer = DUEL_TIME
        self.events.append(("enemy_shot", self.target))

    def _to_player(self):
        self.state = "player_turn"
        self.timer = DUEL_PATIENCE
        self.problem = None
        self.answer = ""

    def _to_windup(self):
        """Враг наводится: пауза, после которой он выстрелит."""
        self.state = "enemy_windup"
        self.timer = DUEL_PAUSE
        self.problem = None
        self.answer = ""

    def _flash(self, kind):
        self.flash = kind
        self.flash_t = 0.8


class Fight:
    """Бой целиком: несколько врагов, но игрок отвечает по одному.

    Патрульные — одна фракция, поэтому после выстрела по одному воюют все. Но
    стрелять одновременно всем нельзя: игрок физически не успеет решить три
    задачи за две секунды. Поэтому активен всегда ровно один поединок, а
    остальные ждут очереди. После того как игрок отбил выстрел, очередь
    переходит к следующему живому врагу — получается бой по раундам.
    """

    def __init__(self, rng=None, level=1):
        self.rng = rng or random.Random()
        self.level = level
        self.duels = []                 # поединки, в порядке завязки
        self.active = 0
        self.events = []                # события боя для main

    # --- состояние ----------------------------------------------------
    @property
    def current(self):
        return self.duels[self.active] if self.duels else None

    def hot(self):
        return bool(self.duels)

    def start(self, target, make_active=True):
        """Игрок выстрелил по кораблю — завязываем поединок с ним.

        make_active=False нужен для подмоги: когда на игрока ополчается вся
        фракция, поединки заводят всем, но активным остаётся тот, по кому он
        выстрелил, — иначе ход мгновенно уехал бы к другому кораблю.
        """
        for i, d in enumerate(self.duels):
            if d.target is target:
                if make_active:
                    self.active = i
                return d
        d = Duel(target, level=self.level, rng=self.rng)
        self.duels.append(d)
        if make_active:
            self.active = len(self.duels) - 1
        return d

    def drop(self, target):
        """Корабль уничтожен: убираем его из очереди."""
        for i, d in enumerate(self.duels):
            if d.target is target:
                self.duels.pop(i)
                if self.active >= len(self.duels):
                    self.active = 0
                return True
        return False

    def next_turn(self):
        """Передать ход следующему живому врагу (бой идёт по раундам)."""
        if self.duels:
            self.active = (self.active + 1) % len(self.duels)
            self.duels[self.active].timer = DUEL_PATIENCE

    def calm(self):
        """Пауза после гибели игрока: враги не стреляют, пока он не очухается."""
        for d in self.duels:
            d.timer = max(d.timer, DEATH_PAUSE)
            d.state = "player_turn"
            d.problem = None
            d.answer = ""

    # --- действия игрока ----------------------------------------------
    def player_fire(self):
        d = self.current
        return d.player_fire() if d else None

    def type_digit(self, ch):
        d = self.current
        return d.type_digit(ch) if d else False

    def backspace(self):
        d = self.current
        return d.backspace() if d else False

    # --- время --------------------------------------------------------
    def update(self, dt):
        d = self.current
        if d is None:
            return
        d.update(dt)
        for e in d.take_events():
            self.events.append(e)
            if e[0] == "shot_repelled":
                # отбился — стреляет следующий враг, а не тот же самый
                self.next_turn()
            elif e[0] == "enemy_down":
                self.drop(d.target)
            elif e[0] == "player_down":
                self.calm()

    def take_events(self):
        out = self.events
        self.events = []
        return out
