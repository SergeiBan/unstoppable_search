# -*- coding: utf-8 -*-
"""Мир: невидимая сетка + сплошная квадратная станция. Плоскость, 2 измерения."""

import math

from config import (STATION_H, STATION_H_TOWER, STATION_SIZE, STATION_X0,
                    STATION_Y0, TOWER_HALF)


class World:
    def __init__(self, sx0=STATION_X0, sy0=STATION_Y0, size=STATION_SIZE):
        self.sx0, self.sy0 = sx0, sy0
        self.sx1, self.sy1 = sx0 + size, sy0 + size
        self.cx = (self.sx0 + self.sx1) * 0.5
        self.cy = (self.sy0 + self.sy1) * 0.5
        self.blockers = set()        # клетки, занятые кораблями (не станцией)

    def height(self, gx, gy):
        """Высота клетки: базовая или надстройка-«хребет» вдоль оси Y.

        Хребет идёт по центру на всю глубину станции — он даёт ступенчатый
        силуэт и виден с любого ракурса (а стыковочный док как раз на нём).
        """
        if abs(gx + 0.5 - self.cx) <= TOWER_HALF:
            return STATION_H_TOWER
        return STATION_H

    def max_height(self):
        return STATION_H_TOWER

    def block_cells(self, cells):
        """Отметить клетки занятыми кораблями: в них входа нет."""
        for c in cells:
            self.blockers.add((int(c[0]), int(c[1])))

    def unblock_cells(self, cells):
        """Освободить клетки — например, когда стоящий корабль уничтожен."""
        for c in cells:
            self.blockers.discard((int(c[0]), int(c[1])))

    def solid(self, gx, gy):
        """Занята ли клетка: корпусом станции или стоящим кораблём."""
        if (gx, gy) in self.blockers:
            return True
        return self.sx0 <= gx < self.sx1 and self.sy0 <= gy < self.sy1

    def dist_to_station(self, wx, wy):
        """Расстояние от точки мира до ближайшей кромки станции, в клетках."""
        dx = max(self.sx0 - wx, 0.0, wx - self.sx1)
        dy = max(self.sy0 - wy, 0.0, wy - self.sy1)
        return math.hypot(dx, dy)

    def station_corners(self):
        """Четыре угла квадрата станции в мировых координатах (для радара)."""
        return [(self.sx0, self.sy0), (self.sx1, self.sy0),
                (self.sx1, self.sy1), (self.sx0, self.sy1)]

    def cells(self):
        for gy in range(self.sy0, self.sy1):
            for gx in range(self.sx0, self.sx1):
                yield gx, gy

    def area(self):
        return (self.sx1 - self.sx0) * (self.sy1 - self.sy0)
