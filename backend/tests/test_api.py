"""Integration tests through the HTTP API."""
import base64
import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import main
from app.config import SimConfig, world_config
from app.experiments import run as runner
from app.metrics import compute_metrics
from app.simulation.world import World

client = TestClient(main.app)
MODES = ("independent", "collective", "interrupted")


def new_session(**body) -> dict:
    res = client.post("/api/session", json=body)
    assert res.status_code == 200, res.text
    return res.json()


def step(sid, n) -> dict:
    res = client.post(f"/api/session/{sid}/step", json={"n": n})
    assert res.status_code == 200, res.text
    return res.json()


def test_health_and_defaults():
    assert client.get("/api/health").json()["status"] == "ok"
    d = client.get("/api/defaults").json()
    assert d["config"]["agent_count"] == 60
    assert d["world_differences"]["independent"] == {"communication": False, "interruption_step": None}


def test_session_creates_three_matched_worlds():
    s = new_session(seed=3)
    assert s["step"] == 0 and s["mode"] == "controlled"
    assert set(s["worlds"]) == set(MODES)
    a, b, c = (s["worlds"][m] for m in MODES)
    assert a["agents"] == b["agents"] == c["agents"]
    assert a["food"] == b["food"] == c["food"] and a["obstacles"] == b["obstacles"]
    assert a["pheromone"] is None and b["pheromone"] is not None
    assert len(a["agents"]["x"]) == 60


def test_stepping_advances_all_worlds_and_matches_the_engine():
    """What the dashboard receives equals what the engine measures directly."""
    s = new_session(seed=5)
    state = step(s["session_id"], 150)
    state = step(s["session_id"], 150)
    assert state["step"] == 300
    for mode in MODES:
        direct = World(world_config(SimConfig(seed=5), mode, 1500)).run(300)
        got = state["worlds"][mode]
        assert got["metrics"] == json.loads(json.dumps(compute_metrics(direct)))
        assert got["series"]["steps"][-1] == 300
        assert got["series"]["delivered"] == [direct.delivered_history[i] for i in got["series"]["steps"]]
        assert got["agents"]["x"] == np.round(direct.x, 2).tolist()
    field = np.frombuffer(base64.b64decode(state["worlds"]["collective"]["pheromone"]), dtype=np.uint8)
    assert field.size == 120 * 80 and field.max() > 0
    assert client.get(f"/api/session/{s['session_id']}").json()["step"] == 300


def test_scheduled_interruption_is_reported():
    s = new_session(seed=2, interruption_step=40)
    assert s["mode"] == "exploratory"  # non-default interruption step
    state = step(s["session_id"], 60)
    c = state["worlds"]["interrupted"]
    assert c["metrics"]["communication_active"] is False
    assert c["metrics"]["communication_disabled_step"] == 40
    assert c["events"][0] == {"type": "communication_disabled", "step": 40, "source": "scheduled"}
    assert state["worlds"]["collective"]["metrics"]["communication_active"] is True


def test_manual_interruption_only_affects_the_breakdown_world():
    s = new_session(seed=2)
    step(s["session_id"], 30)
    res = client.post(f"/api/session/{s['session_id']}/interrupt").json()
    assert res["applied"] is True and res["mode"] == "exploratory"
    assert res["worlds"]["interrupted"]["metrics"]["communication_active"] is False
    assert res["worlds"]["collective"]["metrics"]["communication_active"] is True
    assert client.post(f"/api/session/{s['session_id']}/interrupt").json()["applied"] is False


def test_obstacle_injection_applies_to_every_world():
    s = new_session(seed=2)
    before = step(s["session_id"], 20)
    res = client.post(f"/api/session/{s['session_id']}/obstacle", json={}).json()
    assert res["applied"] is True and res["mode"] == "exploratory"
    for mode in MODES:
        assert res["worlds"][mode]["obstacles"] != before["worlds"][mode]["obstacles"]
        assert res["worlds"][mode]["events"][-1]["type"] == "obstacle_added"
    assert step(s["session_id"], 50)["step"] == 70


def test_obstacle_at_a_chosen_point_and_refusal_on_the_nest():
    s = new_session(seed=2)
    sid = s["session_id"]
    assert client.post(f"/api/session/{sid}/obstacle", json={"x": 30, "y": 20}).json()["applied"] is True
    refused = client.post(f"/api/session/{sid}/obstacle", json={"x": 60, "y": 40}).json()
    assert refused["applied"] is False
    assert all(len(refused["worlds"][m]["events"]) == 1 for m in MODES)


def test_custom_parameters_mark_the_session_exploratory():
    s = new_session(seed=1, agent_count=30, deposit=2.0)
    assert s["mode"] == "exploratory" and len(s["exploratory_reasons"]) == 2
    assert len(s["worlds"]["collective"]["agents"]["x"]) == 30


def test_validation_and_unknown_session():
    assert client.post("/api/session", json={"agent_count": 100000}).status_code == 422
    assert client.post("/api/session/nope/step", json={"n": 1}).status_code == 404
    s = new_session()
    assert client.post(f"/api/session/{s['session_id']}/step", json={"n": 100000}).status_code == 422


def test_quick_experiment_runs_real_simulations():
    res = client.post("/api/experiments/quick", json={"seeds": 2, "steps": 300, "first_seed": 7})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["seeds"] == [7, 8]
    expected = World(world_config(SimConfig(seed=7), "collective", 150)).run(300).delivered
    assert body["per_seed"]["collective"][0] == expected
    assert body["collective_vs_independent"]["n_pairs"] == 2


def test_stored_results_endpoint(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "EXPERIMENTS_DIR", tmp_path)
    assert client.get("/api/experiments/results").json()["available"] is False
    runner.main(["--seeds", "2", "--steps", "400", "--out", str(tmp_path / "results"), "--no-charts", "--workers", "1"])
    body = client.get("/api/experiments/results").json()
    assert body["available"] is True and body["manifest"]["spec"]["seeds"] == [1, 2]
    assert "core/default/collective" in body["series"]["series"]


@pytest.mark.parametrize("workers", ["1", "2"])
def test_experiment_runner_is_reproducible_and_complete(tmp_path, workers):
    outs = []
    for name in ("a", "b"):
        out = tmp_path / name
        runner.main(["--seeds", "2", "--steps", "400", "--out", str(out), "--workers", workers])
        outs.append(out)
    first, second = (json.loads((o / "summary.json").read_text()) for o in outs)
    assert first["results"] == second["results"]
    assert (outs[0] / "runs.csv").read_text() == (outs[1] / "runs.csv").read_text()
    for chart in ("food_delivered_curves", "food_delivered_by_seed", "interruption_windows",
                  "obstacle_recovery", "sensitivity", "traffic_maps"):
        assert (outs[0] / f"{chart}.png").stat().st_size > 5000
    r = first["results"]
    assert r["exp3_communication_failure"]["pre_interruption_trajectories_identical"] is True
    assert r["exp5_multiple_seeds"]["total_runs"] == len((outs[0] / "runs.csv").read_text().splitlines()) - 1
    assert first["manifest"]["data"].startswith("synthetic")
