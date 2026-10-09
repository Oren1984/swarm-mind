"""An interactive three-world session driven by the dashboard.

The client asks for N fixed steps at a time; rendering speed therefore only
changes how fast steps are requested, never what a step computes.
"""
from __future__ import annotations

import base64
import threading
import uuid

import numpy as np

from app import __version__
from app.config import WORLD_MODES, SimConfig, world_config
from app.metrics import compute_metrics
from app.simulation.world import World

DEFAULT_INTERRUPTION_STEP = 1500
MAX_SERIES_POINTS = 400
# Parameters the dashboard may change; anything away from its default makes the session exploratory.
TUNABLE = ("agent_count", "deposit")


class Session:
    def __init__(self, base: SimConfig, interruption_step: int = DEFAULT_INTERRUPTION_STEP):
        self.id = uuid.uuid4().hex[:12]
        self.base = base
        self.interruption_step = interruption_step
        self.worlds: dict[str, World] = {
            mode: World(world_config(base, mode, interruption_step)) for mode in WORLD_MODES
        }
        self.lock = threading.Lock()
        defaults = SimConfig()
        self.exploratory_reasons: list[str] = [
            f"{name} changed from default {getattr(defaults, name)} to {getattr(base, name)}"
            for name in TUNABLE if getattr(base, name) != getattr(defaults, name)
        ]
        if interruption_step != DEFAULT_INTERRUPTION_STEP:
            self.exploratory_reasons.append(
                f"interruption step changed from default {DEFAULT_INTERRUPTION_STEP} to {interruption_step}")

    @property
    def step_count(self) -> int:
        return self.worlds["collective"].t

    def step(self, n: int) -> None:
        for _ in range(n):
            for world in self.worlds.values():
                world.step()

    def interrupt_now(self) -> bool:
        """Manually cut communication in the interrupted world only."""
        done = self.worlds["interrupted"].disable_communication(source="manual")
        if done:
            self.exploratory_reasons.append(f"manual communication interruption at step {self.step_count}")
        return done

    def inject_obstacle(self, x: float | None, y: float | None) -> bool:
        """Adds the same wall to all three worlds, or to none of them."""
        reference = self.worlds["collective"]
        if x is None or y is None:
            segment = reference.default_obstacle_segment()
        else:
            half = reference.cfg.dynamic_obstacle_length / 2
            dx, dy = x - reference.nest[0], y - reference.nest[1]
            norm = float(np.hypot(dx, dy)) or 1.0
            px, py = -dy / norm * half, dx / norm * half  # perpendicular to the nest direction
            segment = (x - px, y - py, x + px, y + py)
        snapshots = {m: (w.obstacles, w.geo, w.x.copy(), w.y.copy(), w.pheromone.copy(), len(w.events))
                     for m, w in self.worlds.items()}
        if all(w.add_obstacle_segment(*segment, source="manual") for w in self.worlds.values()):
            self.exploratory_reasons.append(f"manual obstacle at step {self.step_count}")
            return True
        for m, w in self.worlds.items():  # roll back so the worlds keep identical geometry
            w.obstacles, w.geo, w.x, w.y, w.pheromone, n_events = snapshots[m]
            del w.events[n_events:]
        return False

    # ------------------------------------------------------------ serialisation
    def static(self) -> dict:
        cfg = self.base
        return {
            "session_id": self.id,
            "version": __version__,
            "config": cfg.model_dump(),
            "interruption_step": self.interruption_step,
            "width": cfg.width,
            "height": cfg.height,
            "nest": {"x": cfg.width / 2, "y": cfg.height / 2, "r": cfg.nest_radius},
            "pheromone_max": cfg.pheromone_max,
        }

    def state(self) -> dict:
        return {
            **self.static(),
            "step": self.step_count,
            "mode": "exploratory" if self.exploratory_reasons else "controlled",
            "exploratory_reasons": self.exploratory_reasons,
            "worlds": {mode: _world_state(mode, world) for mode, world in self.worlds.items()},
        }


def _b64(arr: np.ndarray) -> str:
    return base64.b64encode(arr.tobytes()).decode("ascii")


def _world_state(mode: str, world: World) -> dict:
    cfg = world.cfg
    stride = max(1, -(-world.t // MAX_SERIES_POINTS))
    steps = list(range(0, world.t + 1, stride))
    if steps[-1] != world.t:
        steps.append(world.t)
    has_field = cfg.communication
    return {
        "mode": mode,
        "agents": {
            "x": np.round(world.x, 2).tolist(),
            "y": np.round(world.y, 2).tolist(),
            "heading": np.round(world.heading, 2).tolist(),
            "behaviour": world.behaviour.tolist(),  # 0 exploring, 1 following a trail, 2 returning with food
        },
        "food": [{"x": round(float(x), 2), "y": round(float(y), 2), "amount": int(a), "r": cfg.food_radius}
                 for x, y, a in zip(world.food_x, world.food_y, world.food_amount)],
        "obstacles": _b64(np.packbits(world.obstacles)),
        # uint8 field, row-major [height, width]; null for a world that never communicates
        "pheromone": _b64((world.pheromone / cfg.pheromone_max * 255).round().astype(np.uint8)) if has_field else None,
        "metrics": compute_metrics(world),
        "series": {"steps": steps, "delivered": [world.delivered_history[s] for s in steps]},
        "events": world.events,
    }


class SessionStore:
    """A handful of in-memory sessions; the oldest is dropped when full."""

    def __init__(self, capacity: int = 16):
        self.capacity = capacity
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def add(self, session: Session) -> Session:
        with self._lock:
            while len(self._sessions) >= self.capacity:
                self._sessions.pop(next(iter(self._sessions)))
            self._sessions[session.id] = session
        return session

    def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)
