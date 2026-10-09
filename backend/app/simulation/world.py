"""The authoritative fixed-step simulation of one world.

All three experimental worlds are instances of this single class; only the
communication fields of their `SimConfig` differ.
"""
from __future__ import annotations

import hashlib
import math

import numpy as np

from app.config import SimConfig
from app.simulation import scenario
from app.simulation.agents import EXPLORING, Observation, decide


class World:
    def __init__(self, cfg: SimConfig):
        self.cfg = cfg
        self.t = 0
        self.obstacles, self.nest, self.geo, food = scenario.build_map(cfg)
        self.initial_obstacles = self.obstacles.copy()
        self._cx, self._cy = scenario.cell_centers(self.obstacles.shape)

        k = len(food)
        self.food_x = np.array([f[0] for f in food])
        self.food_y = np.array([f[1] for f in food])
        self.food_amount = np.full(k, cfg.food_capacity, dtype=np.int64)
        self.respawns = 0

        n = cfg.agent_count
        init = np.random.default_rng([cfg.seed, scenario.STREAM_AGENT_INIT])
        r = cfg.nest_radius * 0.8 * np.sqrt(init.random(n))
        a = init.uniform(0, 2 * np.pi, n)
        self.x = self.nest[0] + r * np.cos(a)
        self.y = self.nest[1] + r * np.sin(a)
        self.heading = init.uniform(0, 2 * np.pi, n)
        self.carrying = np.zeros(n, dtype=bool)
        self.behaviour = np.full(n, EXPLORING, dtype=np.int8)
        self.steps_since_pickup = np.zeros(n, dtype=np.int64)
        self.pickup_geo = np.zeros(n)
        self.rng = np.random.default_rng([cfg.seed, scenario.STREAM_AGENT_DECISIONS])

        self.pheromone = np.zeros(self.obstacles.shape)
        self.comm_active = cfg.communication
        self.comm_disabled_step: int | None = None

        # measurement state
        self.visits = np.zeros(self.obstacles.shape, dtype=np.int64)
        self.delivered = 0
        self.delivered_history = [0]  # index = step
        self.first_delivery_step: int | None = None
        self.distance_travelled = 0.0
        self.necessary_distance = 0.0
        self.deposit_events = 0
        self.pheromone_sensed_total = 0.0  # sum of pheromone values handed to agents
        self.events: list[dict] = []

    # ------------------------------------------------------------------ sensing
    def _cells(self, px, py):
        ix, iy = np.floor(px).astype(np.int64), np.floor(py).astype(np.int64)
        inside = (ix >= 0) & (ix < self.cfg.width) & (iy >= 0) & (iy < self.cfg.height)
        return ix.clip(0, self.cfg.width - 1), iy.clip(0, self.cfg.height - 1), inside

    def observe(self) -> Observation:
        """Builds each agent's local percepts. Pheromone readings are zero
        whenever communication is inactive — the field is then never read."""
        cfg = self.cfg
        angles = self.heading[:, None] + np.array([-cfg.sensor_angle, 0.0, cfg.sensor_angle])
        reach = np.arange(1, cfg.sensor_distance + 1)
        px = self.x[:, None, None] + np.cos(angles)[:, :, None] * reach
        py = self.y[:, None, None] + np.sin(angles)[:, :, None] * reach
        ix, iy, inside = self._cells(px, py)
        ray_free = (inside & ~self.obstacles[iy, ix]).all(axis=2)
        tip_x, tip_y = ix[:, :, -1], iy[:, :, -1]

        if self.comm_active:
            pheromone = np.where(ray_free, self.pheromone[tip_y, tip_x], 0.0)
        else:
            pheromone = np.zeros(ray_free.shape)
        nest_scent = np.where(ray_free, self.geo[tip_y, tip_x], np.inf)

        dx = self.food_x[None, :] - self.x[:, None]
        dy = self.food_y[None, :] - self.y[:, None]
        dist = np.hypot(dx, dy)
        in_range = (self.food_amount > 0)[None, :] & (dist <= cfg.food_radius + cfg.perception_radius)
        dist = np.where(in_range, dist, np.inf)
        nearest = np.argmin(dist, axis=1)
        rows = np.arange(len(self.x))
        visible = np.isfinite(dist[rows, nearest])
        ndx, ndy = dx[rows, nearest], dy[rows, nearest]
        fractions = np.linspace(0.2, 1.0, 5)
        lx, ly, linside = self._cells(self.x[:, None] + ndx[:, None] * fractions,
                                      self.y[:, None] + ndy[:, None] * fractions)
        visible &= (linside & ~self.obstacles[ly, lx]).all(axis=1)
        return Observation(ray_free, pheromone, nest_scent, visible, np.arctan2(ndy, ndx))

    # --------------------------------------------------------------------- step
    def step(self) -> None:
        cfg = self.cfg
        if cfg.obstacle_step is not None and self.t == cfg.obstacle_step:
            self.add_default_obstacle(source="scheduled")
        if self.comm_active and cfg.interruption_step is not None and self.t >= cfg.interruption_step:
            self.disable_communication(source="scheduled")

        n = len(self.x)
        # A fixed number of draws per step keeps matched worlds on the same random stream.
        u_choice, u_escape, u_bump = self.rng.random(n), self.rng.random(n), self.rng.random(n)
        noise = self.rng.normal(0.0, cfg.heading_noise, n)

        obs = self.observe()
        self.pheromone_sensed_total += float(obs.pheromone.sum())
        self.heading, self.behaviour = decide(obs, self.carrying, self.heading, u_choice, noise, u_escape, cfg)

        # Move; a blocked move becomes a random turn-around instead.
        nx = self.x + np.cos(self.heading) * cfg.speed
        ny = self.y + np.sin(self.heading) * cfg.speed
        ix, iy, inside = self._cells(nx, ny)
        ok = inside & ~self.obstacles[iy, ix]
        self.x = np.where(ok, nx, self.x)
        self.y = np.where(ok, ny, self.y)
        self.heading = np.where(ok, self.heading, np.mod(self.heading + np.pi + (u_bump - 0.5) * np.pi, 2 * np.pi))
        self.distance_travelled += float(ok.sum()) * cfg.speed
        cx, cy, _ = self._cells(self.x, self.y)
        np.add.at(self.visits, (cy, cx), 1)

        # Deliveries.
        at_nest = self.carrying & (np.hypot(self.x - self.nest[0], self.y - self.nest[1]) <= cfg.nest_radius)
        count = int(at_nest.sum())
        if count:
            self.delivered += count
            self.necessary_distance += float(2.0 * self.pickup_geo[at_nest].sum())
            self.carrying[at_nest] = False
            self.heading[at_nest] = np.mod(self.heading[at_nest] + np.pi, 2 * np.pi)
            if self.first_delivery_step is None:
                self.first_delivery_step = self.t + 1

        # Pickups (lowest agent index first when a patch is nearly empty).
        for j in range(len(self.food_x)):
            if self.food_amount[j] <= 0:
                continue
            on_patch = ~self.carrying & (np.hypot(self.x - self.food_x[j], self.y - self.food_y[j]) <= cfg.food_radius)
            takers = np.flatnonzero(on_patch)[: int(self.food_amount[j])]
            if len(takers) == 0:
                continue
            self.carrying[takers] = True
            self.steps_since_pickup[takers] = 0
            self.pickup_geo[takers] = self.geo[cy[takers], cx[takers]]
            self.heading[takers] = np.mod(self.heading[takers] + np.pi, 2 * np.pi)
            self.food_amount[j] -= len(takers)
            if self.food_amount[j] == 0:
                self._relocate_food(j)

        # Pheromone: carriers mark their way home, strongest near the food.
        if self.comm_active and cfg.deposit > 0:
            carriers = np.flatnonzero(self.carrying)
            if len(carriers):
                amount = cfg.deposit * np.exp(-self.steps_since_pickup[carriers] / cfg.deposit_decay)
                np.add.at(self.pheromone, (cy[carriers], cx[carriers]), amount)
                self.deposit_events += len(carriers)
        self.steps_since_pickup[self.carrying] += 1
        self._evaporate()

        self.t += 1
        self.delivered_history.append(self.delivered)

    def run(self, steps: int) -> "World":
        for _ in range(steps):
            self.step()
        return self

    def _evaporate(self) -> None:
        p = self.pheromone
        if not p.any():
            return
        p *= 1.0 - self.cfg.evaporation
        if self.cfg.diffusion > 0:
            pad = np.pad(p, 1, mode="edge")
            neighbours = (pad[:-2, 1:-1] + pad[2:, 1:-1] + pad[1:-1, :-2] + pad[1:-1, 2:]) * 0.25
            p += self.cfg.diffusion * (neighbours - p)
        p[self.obstacles] = 0.0
        np.minimum(p, self.cfg.pheromone_max, out=p)
        p[p < 1e-6] = 0.0

    def _relocate_food(self, j: int) -> None:
        others = [(self.food_x[i], self.food_y[i]) for i in range(len(self.food_x)) if i != j]
        rng = scenario.respawn_rng(self.cfg.seed, self.respawns)
        self.food_x[j], self.food_y[j] = scenario.sample_food_site(
            rng, self.obstacles, self.geo, self.nest, others, self.cfg)
        self.food_amount[j] = self.cfg.food_capacity
        self.respawns += 1

    # ------------------------------------------------------------ interventions
    def disable_communication(self, source: str = "manual") -> bool:
        """Stops deposition AND sensing. The existing field keeps evaporating
        (and stays visible) but no agent reads it again."""
        if not self.comm_active:
            return False
        self.comm_active = False
        self.comm_disabled_step = self.t
        self.events.append({"type": "communication_disabled", "step": self.t, "source": source})
        return True

    def default_obstacle_segment(self) -> tuple[float, float, float, float]:
        """A wall across the straight line from the nest to the food source
        that is currently closest to the nest by walking distance."""
        ix, iy, _ = self._cells(self.food_x, self.food_y)
        j = int(np.argmin(self.geo[iy, ix]))
        mx, my = (self.nest[0] + self.food_x[j]) / 2, (self.nest[1] + self.food_y[j]) / 2
        angle = math.atan2(self.food_y[j] - self.nest[1], self.food_x[j] - self.nest[0]) + math.pi / 2
        half = self.cfg.dynamic_obstacle_length / 2
        return (mx - math.cos(angle) * half, my - math.sin(angle) * half,
                mx + math.cos(angle) * half, my + math.sin(angle) * half)

    def add_default_obstacle(self, source: str = "manual") -> bool:
        return self.add_obstacle_segment(*self.default_obstacle_segment(), source=source)

    def add_obstacle_segment(self, x0, y0, x1, y1, source: str = "manual") -> bool:
        """Inserts a wall. Refused (returns False) if it would cut a food source
        off from the nest. Agents caught inside move to the nearest free cell."""
        cfg = self.cfg
        protected = np.hypot(self._cx - self.nest[0], self._cy - self.nest[1]) <= cfg.nest_radius + 2
        for fx, fy in zip(self.food_x, self.food_y):
            protected |= np.hypot(self._cx - fx, self._cy - fy) <= cfg.food_radius + 1
        mask = scenario.rasterize_segment(self.obstacles.shape, x0, y0, x1, y1) & ~self.obstacles & ~protected
        if not mask.any():
            return False
        obstacles = self.obstacles | mask
        geo = scenario.geodesic_field(obstacles, self.nest)
        fx, fy, _ = self._cells(self.food_x, self.food_y)
        if not np.isfinite(geo[fy, fx]).all():
            return False

        ax, ay, _ = self._cells(self.x, self.y)
        stranded = np.flatnonzero(~np.isfinite(geo[ay, ax]))
        if len(stranded):
            free_y, free_x = np.nonzero(np.isfinite(geo))
            for i in stranded:
                nearest = np.argmin((free_x + 0.5 - self.x[i]) ** 2 + (free_y + 0.5 - self.y[i]) ** 2)
                self.x[i], self.y[i] = free_x[nearest] + 0.5, free_y[nearest] + 0.5

        self.obstacles, self.geo = obstacles, geo
        self.pheromone[obstacles] = 0.0
        self.events.append({"type": "obstacle_added", "step": self.t, "source": source,
                            "segment": [round(float(v), 2) for v in (x0, y0, x1, y1)],
                            "cells": int(mask.sum())})
        return True

    # ---------------------------------------------------------------- utilities
    def digest(self) -> str:
        """Hash of the full dynamic state, for reproducibility checks."""
        h = hashlib.sha256()
        for arr in (self.x, self.y, self.heading, self.carrying, self.pheromone, self.obstacles,
                    self.food_x, self.food_y, self.food_amount, self.visits):
            h.update(np.ascontiguousarray(arr).tobytes())
        h.update(str((self.t, self.delivered, self.comm_active)).encode())
        return h.hexdigest()
