"""Metric definitions. Every metric is computed from measured world state.

Undefined values are returned as None (never silently replaced by zero).
Formal definitions: docs/experiment-design.md.
"""
from __future__ import annotations

import numpy as np

from app.simulation.world import World

RECENT_WINDOW = 200
TOP_TRAFFIC_SHARE = 0.05


def window_deliveries(world: World, start: int, end: int) -> int | None:
    """Deliveries completed during steps [start, end). None if not simulated yet."""
    if start < 0 or end > world.t or end < start:
        return None
    return world.delivered_history[end] - world.delivered_history[start]


def rate_per_100(deliveries: int | None, steps: int) -> float | None:
    if deliveries is None or steps <= 0:
        return None
    return 100.0 * deliveries / steps


def ratio(numerator: float | None, denominator: float | None) -> float | None:
    """numerator / denominator, or None when undefined."""
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def coverage(world: World) -> float:
    """Share of currently reachable cells that at least one agent has stood on."""
    reachable = np.isfinite(world.geo)
    return float(((world.visits > 0) & reachable).sum() / reachable.sum())


def traffic_concentration(visits: np.ndarray, world: World, top: float = TOP_TRAFFIC_SHARE) -> float | None:
    """Share of all agent position samples that fall on the `top` most-visited
    fraction of reachable cells, excluding the nest area (where every agent must
    pass in every world). Uniform traffic gives `top`; a few narrow trails give
    values near 1. Computed from where agents walk, not from the pheromone
    field, so it is defined identically for worlds with and without pheromone."""
    mask = np.isfinite(world.geo)
    mask &= np.hypot(world._cx - world.nest[0], world._cy - world.nest[1]) > world.cfg.nest_radius + 2
    counts = np.sort(visits[mask])[::-1]
    total = counts.sum()
    if total == 0:
        return None
    k = max(1, int(round(top * counts.size)))
    return float(counts[:k].sum() / total)


def compute_metrics(world: World) -> dict:
    t = world.t
    recent_start = max(0, t - RECENT_WINDOW)
    return {
        "step": t,
        "food_delivered": world.delivered,
        "first_delivery_step": world.first_delivery_step,
        "exploration_coverage": coverage(world),
        # distance strictly needed for the completed round trips / distance actually walked
        "travel_efficiency": ratio(world.necessary_distance, world.distance_travelled),
        "delivery_rate_per_100": rate_per_100(world.delivered, t),
        "recent_rate_per_100": rate_per_100(window_deliveries(world, recent_start, t), t - recent_start),
        "food_relocations": world.respawns,
        "deposit_events": world.deposit_events,
        "pheromone_sensed_total": world.pheromone_sensed_total,
        "pheromone_field_total": float(world.pheromone.sum()),
        "communication_active": world.comm_active,
        "communication_disabled_step": world.comm_disabled_step,
    }
