"""Local agent decision rule.

`decide` is the ONLY place where agents choose a direction. It receives an
`Observation` (what each agent can sense within a few cells of itself) plus
pre-drawn random numbers. It never sees the world object, the map, the food
list or other agents, so it cannot plan globally by construction.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.config import SimConfig

EXPLORING, FOLLOWING, RETURNING = 0, 1, 2
FOLLOW_THRESHOLD = 0.05  # pheromone level above which a searcher is shown as "following"


@dataclass(frozen=True)
class Observation:
    """Per-agent local percepts. Arrays are [agents] or [agents, 3 rays]."""

    ray_free: np.ndarray  # bool  — left/centre/right antenna ray is unobstructed
    pheromone: np.ndarray  # float — pheromone at each ray tip (all zeros without communication)
    nest_scent: np.ndarray  # float — walkable distance-to-nest at each ray tip (inf if blocked)
    food_visible: np.ndarray  # bool  — a food patch is within perception range and in line of sight
    food_bearing: np.ndarray  # float — direction to that patch (meaningless if not visible)


def decide(
    obs: Observation,
    carrying: np.ndarray,
    heading: np.ndarray,
    u_choice: np.ndarray,
    noise: np.ndarray,
    u_escape: np.ndarray,
    cfg: SimConfig,
) -> tuple[np.ndarray, np.ndarray]:
    """Returns (new_heading, behaviour) for every agent.

    Searchers pick one of three forward rays with probability proportional to
    (k + pheromone)^n — with no pheromone signal this is a uniform choice, i.e.
    a correlated random walk. Seen food overrides the choice. Carriers pick the
    ray that smells closest to the nest. A fully blocked agent turns around.
    """
    n = heading.shape[0]
    rows = np.arange(n)

    # Searchers: probabilistic ray choice.
    weights = np.where(obs.ray_free, (cfg.choice_k + obs.pheromone) ** cfg.choice_n, 0.0)
    total = weights.sum(axis=1)
    cumulative = np.cumsum(weights, axis=1)
    search_ray = ((u_choice * total)[:, None] >= cumulative).sum(axis=1).clip(max=2)
    search_heading = heading + (search_ray - 1) * cfg.turn_angle + noise
    search_heading = np.where(obs.food_visible, obs.food_bearing, search_heading)

    # Carriers: descend the nest scent.
    home_ray = np.argmin(obs.nest_scent, axis=1)
    home_heading = heading + (home_ray - 1) * cfg.turn_angle + 0.5 * noise

    new_heading = np.where(carrying, home_heading, search_heading)

    blocked = ~obs.ray_free.any(axis=1) & ~(obs.food_visible & ~carrying)
    new_heading = np.where(blocked, heading + np.pi + (u_escape - 0.5) * np.pi, new_heading)

    sensed = obs.pheromone[rows, search_ray.clip(0, 2)] > FOLLOW_THRESHOLD
    behaviour = np.where(carrying, RETURNING, np.where(sensed & ~obs.food_visible, FOLLOWING, EXPLORING))
    return np.mod(new_heading, 2 * np.pi), behaviour.astype(np.int8)
