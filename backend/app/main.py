"""FastAPI layer: a thin wrapper around the simulation engine. No simulation
logic lives here."""
from __future__ import annotations

import json

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app import __version__
from app.config import SimConfig, world_overrides
from app.experiments.run import EXPERIMENTS_DIR, quick_comparison
from app.session import DEFAULT_INTERRUPTION_STEP, Session, SessionStore

app = FastAPI(title="Swarm Mind simulation API", version=__version__)
store = SessionStore()

MAX_STEPS_PER_REQUEST = 200


class SessionRequest(BaseModel):
    seed: int = Field(1, ge=0, le=2**31 - 1)
    agent_count: int = Field(60, ge=5, le=200)
    deposit: float = Field(1.0, ge=0.0, le=5.0)
    interruption_step: int = Field(DEFAULT_INTERRUPTION_STEP, ge=0, le=1_000_000)


class StepRequest(BaseModel):
    n: int = Field(1, ge=1, le=MAX_STEPS_PER_REQUEST)


class ObstacleRequest(BaseModel):
    x: float | None = None
    y: float | None = None


class QuickExperimentRequest(BaseModel):
    seeds: int = Field(4, ge=2, le=10)
    steps: int = Field(1000, ge=200, le=3000)
    first_seed: int = Field(1, ge=0, le=2**31 - 100)


def _session(session_id: str) -> Session:
    session = store.get(session_id)
    if session is None:
        raise HTTPException(404, "unknown or expired session; create a new one")
    return session


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "version": __version__}


@app.get("/api/defaults")
def defaults() -> dict:
    return {
        "version": __version__,
        "config": SimConfig().model_dump(),
        "interruption_step": DEFAULT_INTERRUPTION_STEP,
        "world_differences": {m: world_overrides(m, DEFAULT_INTERRUPTION_STEP)
                              for m in ("independent", "collective", "interrupted")},
        "limits": {"agent_count": [5, 200], "deposit": [0.0, 5.0], "max_steps_per_request": MAX_STEPS_PER_REQUEST},
    }


@app.post("/api/session")
def create_session(req: SessionRequest) -> dict:
    base = SimConfig(seed=req.seed, agent_count=req.agent_count, deposit=req.deposit)
    return store.add(Session(base, req.interruption_step)).state()


@app.get("/api/session/{session_id}")
def get_state(session_id: str) -> dict:
    session = _session(session_id)
    with session.lock:
        return session.state()


@app.post("/api/session/{session_id}/step")
def step(session_id: str, req: StepRequest) -> dict:
    session = _session(session_id)
    with session.lock:
        session.step(req.n)
        return session.state()


@app.post("/api/session/{session_id}/interrupt")
def interrupt(session_id: str) -> dict:
    session = _session(session_id)
    with session.lock:
        applied = session.interrupt_now()
        return {"applied": applied, **session.state()}


@app.post("/api/session/{session_id}/obstacle")
def obstacle(session_id: str, req: ObstacleRequest) -> dict:
    session = _session(session_id)
    with session.lock:
        applied = session.inject_obstacle(req.x, req.y)
        return {"applied": applied, **session.state()}


@app.post("/api/experiments/quick")
def run_quick_experiment(req: QuickExperimentRequest) -> dict:
    """Runs a small fresh multi-seed comparison (takes a few seconds)."""
    seeds = list(range(req.first_seed, req.first_seed + req.seeds))
    return quick_comparison(seeds, req.steps, interruption_step=req.steps // 2)


@app.get("/api/experiments/results")
def stored_results() -> dict:
    """The stored full experiment (experiments/results/summary.json + mean curves)."""
    summary = EXPERIMENTS_DIR / "results" / "summary.json"
    series = EXPERIMENTS_DIR / "results" / "series.json"
    if not summary.exists():
        return {"available": False, "hint": "run `python -m app.experiments.run` to generate results"}
    out = {"available": True, **json.loads(summary.read_text(encoding="utf-8"))}
    if series.exists():
        out["series"] = json.loads(series.read_text(encoding="utf-8"))
    return out
