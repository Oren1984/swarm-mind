"""Synthetic map generation: obstacles, nest, food sites, homing field.

Everything here is derived from the scenario seed only, so every world built
from the same config starts from the identical map.
"""
from __future__ import annotations

import heapq
import math

import numpy as np

from app.config import SimConfig

# Independent random streams (combined with the seed via SeedSequence).
STREAM_MAP = 101
STREAM_RESPAWN = 202
STREAM_AGENT_INIT = 303
STREAM_AGENT_DECISIONS = 404

WALL_HALF_WIDTH = 1.2


def cell_centers(shape: tuple[int, int]) -> tuple[np.ndarray, np.ndarray]:
    ys, xs = np.mgrid[0 : shape[0], 0 : shape[1]]
    return xs + 0.5, ys + 0.5


def rasterize_segment(shape, x0, y0, x1, y1, half_width=WALL_HALF_WIDTH) -> np.ndarray:
    """Boolean mask of grid cells whose centre lies within half_width of a segment."""
    cx, cy = cell_centers(shape)
    dx, dy = x1 - x0, y1 - y0
    length2 = dx * dx + dy * dy
    t = np.clip(((cx - x0) * dx + (cy - y0) * dy) / length2, 0.0, 1.0) if length2 > 0 else 0.0
    return np.hypot(cx - (x0 + t * dx), cy - (y0 + t * dy)) <= half_width


def geodesic_field(obstacles: np.ndarray, nest: tuple[float, float]) -> np.ndarray:
    """Shortest walkable distance from every free cell to the nest (inf if cut off).

    Dijkstra on the 8-connected grid without corner cutting. This is the
    "nest scent" all agents can smell locally; see docs/architecture.md.
    """
    h, w = obstacles.shape
    blocked = obstacles.tolist()
    dist = [[math.inf] * w for _ in range(h)]
    sx, sy = int(nest[0]), int(nest[1])
    dist[sy][sx] = 0.0
    heap = [(0.0, sx, sy)]
    diag = math.sqrt(2.0)
    steps = [(1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
             (1, 1, diag), (1, -1, diag), (-1, 1, diag), (-1, -1, diag)]
    while heap:
        d, x, y = heapq.heappop(heap)
        if d > dist[y][x]:
            continue
        for dx, dy, cost in steps:
            nx, ny = x + dx, y + dy
            if not (0 <= nx < w and 0 <= ny < h) or blocked[ny][nx]:
                continue
            if dx and dy and (blocked[y][nx] or blocked[ny][x]):
                continue
            nd = d + cost
            if nd < dist[ny][nx]:
                dist[ny][nx] = nd
                heapq.heappush(heap, (nd, nx, ny))
    return np.array(dist)


def sample_food_site(rng, obstacles, geo, nest, existing, cfg: SimConfig) -> tuple[float, float]:
    """A free, reachable site far enough from the nest and from other sources."""
    cx, cy = cell_centers(obstacles.shape)
    r = cfg.food_radius
    for _ in range(5000):
        x = rng.uniform(r + 1, cfg.width - r - 1)
        y = rng.uniform(r + 1, cfg.height - r - 1)
        if math.hypot(x - nest[0], y - nest[1]) < cfg.food_min_nest_distance:
            continue
        if any(math.hypot(x - ex, y - ey) < 4 * r for ex, ey in existing):
            continue
        if obstacles[(cx - x) ** 2 + (cy - y) ** 2 <= (r + 1) ** 2].any():
            continue
        if not math.isfinite(geo[int(y), int(x)]):
            continue
        return x, y
    raise RuntimeError("could not place a food source; map is too crowded")


def respawn_rng(seed: int, respawn_index: int) -> np.random.Generator:
    """The n-th relocation of a food source uses its own stream, so the n-th
    relocation is drawn from the same generator state in every world."""
    return np.random.default_rng([seed, STREAM_RESPAWN, respawn_index])


def build_map(cfg: SimConfig):
    """Returns (obstacles[h,w] bool, nest(x,y), geo[h,w], food[(x,y), ...])."""
    rng = np.random.default_rng([cfg.seed, STREAM_MAP])
    shape = (cfg.height, cfg.width)
    nest = (cfg.width / 2.0, cfg.height / 2.0)
    cx, cy = cell_centers(shape)
    keep_clear = np.hypot(cx - nest[0], cy - nest[1]) <= cfg.nest_radius + 6

    obstacles = np.zeros(shape, dtype=bool)
    placed = attempts = 0
    while placed < cfg.obstacle_count and attempts < 500:
        attempts += 1
        mx, my = rng.uniform(8, cfg.width - 8), rng.uniform(8, cfg.height - 8)
        angle, half = rng.uniform(0, math.pi), rng.uniform(5, 12)
        wall = rasterize_segment(shape, mx - math.cos(angle) * half, my - math.sin(angle) * half,
                                 mx + math.cos(angle) * half, my + math.sin(angle) * half)
        if (wall & keep_clear).any():
            continue
        obstacles |= wall
        placed += 1

    geo = geodesic_field(obstacles, nest)
    food: list[tuple[float, float]] = []
    for _ in range(cfg.food_sources):
        food.append(sample_food_site(rng, obstacles, geo, nest, food, cfg))
    return obstacles, nest, geo, food
