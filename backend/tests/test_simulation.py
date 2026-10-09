"""Unit tests for the simulation engine and metric definitions."""
import numpy as np
import pytest

from app.config import SimConfig, world_config
from app.experiments.stats import describe, paired
from app.metrics import compute_metrics, ratio, traffic_concentration, window_deliveries
from app.simulation.agents import EXPLORING, FOLLOWING, RETURNING, Observation, decide
from app.simulation.world import World


def make(mode="collective", **kw) -> World:
    return World(world_config(SimConfig(**kw), mode, kw.pop("interruption", 1500)))


def open_world(mode="collective", **kw) -> World:
    """A world without walls, with a single agent we can place by hand."""
    return make(mode, obstacle_count=0, agent_count=1, **kw)


def place(world: World, x, y, heading=0.0, carrying=False):
    world.x[:], world.y[:], world.heading[:], world.carrying[:] = x, y, heading, carrying


# ------------------------------------------------------------------ movement
def test_agents_move_one_speed_unit_when_unblocked():
    w = open_world()
    place(w, 20.0, 20.0)
    w.step()
    assert np.hypot(w.x[0] - 20.0, w.y[0] - 20.0) == pytest.approx(w.cfg.speed)
    assert w.distance_travelled == pytest.approx(w.cfg.speed)


def test_agents_never_enter_obstacles_or_leave_the_arena():
    w = make(seed=3)
    for _ in range(400):
        w.step()
        ix, iy = np.floor(w.x).astype(int), np.floor(w.y).astype(int)
        assert ((ix >= 0) & (ix < w.cfg.width) & (iy >= 0) & (iy < w.cfg.height)).all()
        assert not w.obstacles[iy, ix].any()


def test_agents_do_not_tunnel_through_walls():
    """Walking distance to the nest can only change by about one step per step."""
    w = make(seed=5)
    cell = lambda: w.geo[np.floor(w.y).astype(int), np.floor(w.x).astype(int)]
    before = cell()
    for _ in range(400):
        w.step()
        after = cell()
        assert np.abs(after - before).max() <= 3.0
        before = after


def test_blocked_agent_stays_put_and_turns():
    w = open_world()
    place(w, w.cfg.width - 0.5, 20.0, heading=0.0)  # facing the east border
    w.step()
    assert w.x[0] <= w.cfg.width
    assert w.distance_travelled in (0.0, w.cfg.speed)


# ---------------------------------------------------------------- perception
def test_food_is_only_perceived_within_local_range():
    w = open_world()
    fx, fy = w.food_x[0], w.food_y[0]
    limit = w.cfg.food_radius + w.cfg.perception_radius
    place(w, fx - (limit + 2.0), fy)
    assert not w.observe().food_visible[0]
    place(w, fx - (limit - 0.5), fy)
    obs = w.observe()
    assert obs.food_visible[0]
    assert np.cos(obs.food_bearing[0]) == pytest.approx(1.0)


def test_food_behind_a_wall_is_not_perceived():
    w = open_world()
    fx, fy = w.food_x[0], w.food_y[0]
    place(w, fx - 6.0, fy)
    assert w.observe().food_visible[0]
    w.obstacles[:, int(fx - 4.5)] = True
    assert not w.observe().food_visible[0]


def test_antenna_rays_report_obstacles_and_never_read_through_them():
    w = open_world()
    place(w, 20.5, 20.5, heading=0.0)
    w.pheromone[:] = 5.0
    w.obstacles[:, 22] = True  # wall two cells ahead, pheromone beyond it
    obs = w.observe()
    assert not obs.ray_free[0].any()
    assert (obs.pheromone[0] == 0).all()
    assert np.isinf(obs.nest_scent[0]).all()


# ------------------------------------------------------- pickup and delivery
def test_food_pickup_decrements_source_and_turns_agent_around():
    w = open_world()
    place(w, w.food_x[0] - 1.0, w.food_y[0], heading=0.0)
    w.step()
    assert w.carrying[0]
    assert w.food_amount[0] == w.cfg.food_capacity - 1
    assert np.cos(w.heading[0]) < 0  # reversed


def test_food_delivery_counts_once_and_records_first_delivery():
    w = open_world()
    place(w, w.nest[0] + w.cfg.nest_radius + 0.5, w.nest[1], heading=np.pi, carrying=True)
    w.pickup_geo[:] = 30.0
    w.step()
    assert w.delivered == 1 and not w.carrying[0]
    assert w.first_delivery_step == 1
    assert w.necessary_distance == pytest.approx(60.0)
    w.step()
    assert w.delivered == 1


def test_nearly_empty_source_is_not_over_harvested_and_relocates():
    w = make(obstacle_count=0, agent_count=5, food_capacity=2)
    fx, fy = w.food_x[0], w.food_y[0]
    place(w, fx - 1.0, fy)
    w.step()
    assert w.carrying.sum() == 2
    assert w.respawns == 1 and w.food_amount[0] == 2
    assert (w.food_x[0], w.food_y[0]) != (fx, fy)


# ------------------------------------------------------------------ pheromone
def test_carriers_deposit_pheromone_only_when_communicating():
    for mode, expect in (("collective", True), ("independent", False)):
        w = open_world(mode)
        place(w, 20.0, 20.0, carrying=True)
        w.step()
        assert bool(w.pheromone.sum() > 0) is expect
        assert (w.deposit_events == 1) is expect


def test_searchers_do_not_deposit():
    w = open_world()
    place(w, 20.0, 20.0, carrying=False)
    w.step()
    assert w.pheromone.sum() == 0 and w.deposit_events == 0


def test_deposit_is_strongest_right_after_pickup():
    w = open_world()
    place(w, 20.0, 20.0, carrying=True)
    w.step()
    first = w.pheromone.max()
    w.pheromone[:] = 0
    w.steps_since_pickup[:] = 200
    w.step()
    assert 0 < w.pheromone.max() < first * 0.1


def test_evaporation_decays_and_caps_the_field():
    w = open_world(diffusion=0.0, evaporation=0.1)
    w.pheromone[10, 10] = 2.0
    w.pheromone[11, 11] = 1e9
    w._evaporate()
    assert w.pheromone[10, 10] == pytest.approx(1.8)
    assert w.pheromone[11, 11] == w.cfg.pheromone_max


def test_diffusion_spreads_without_creating_pheromone():
    w = open_world(diffusion=0.2, evaporation=0.0)
    w.pheromone[10, 10] = 4.0
    w._evaporate()
    assert w.pheromone[10, 11] > 0
    assert w.pheromone.sum() == pytest.approx(4.0)


def _obs(pheromone, n=6000, free=(True, True, True), scent=(3.0, 2.0, 1.0)):
    return Observation(
        ray_free=np.tile(np.array(free), (n, 1)),
        pheromone=np.tile(np.array(pheromone, dtype=float), (n, 1)),
        nest_scent=np.tile(np.array(scent), (n, 1)),
        food_visible=np.zeros(n, dtype=bool),
        food_bearing=np.zeros(n),
    )


def _turns(obs, carrying=False):
    cfg, n = SimConfig(), obs.ray_free.shape[0]
    rng = np.random.default_rng(0)
    heading, _ = decide(obs, np.full(n, carrying), np.zeros(n), rng.random(n), np.zeros(n), rng.random(n), cfg)
    signed = np.mod(heading + np.pi, 2 * np.pi) - np.pi
    return np.round(signed / cfg.turn_angle).astype(int)  # -1 left ray, 0 centre, +1 right ray


def test_without_pheromone_the_choice_is_uniform():
    turns = _turns(_obs([0, 0, 0]))
    for ray in (-1, 0, 1):
        assert (turns == ray).mean() == pytest.approx(1 / 3, abs=0.03)


def test_pheromone_biases_the_choice_probabilistically():
    turns = _turns(_obs([1.0, 0.0, 0.0]))
    share = (turns == -1).mean()
    assert 0.95 < share < 1.0  # strongly preferred, but not deterministic


def test_blocked_rays_are_never_chosen():
    turns = _turns(_obs([0, 0, 0], free=(False, True, False)))
    assert (turns == 0).all()


def test_carriers_follow_the_nest_scent_and_ignore_pheromone():
    turns = _turns(_obs([9.0, 0.0, 0.0], scent=(3.0, 2.0, 1.0)), carrying=True)
    assert (turns == 1).all()


def test_behaviour_labels():
    cfg = SimConfig()
    z, u = np.zeros(1), np.full(1, 0.5)
    label = lambda obs, carrying: decide(obs, np.array([carrying]), z, u, z, u, cfg)[1][0]
    assert label(_obs([0, 0, 0], n=1), False) == EXPLORING
    assert label(_obs([1, 1, 1], n=1), False) == FOLLOWING
    assert label(_obs([1, 1, 1], n=1), True) == RETURNING


# ------------------------------------------------------ communication cut-off
def test_disabled_communication_stops_sensing_and_deposition():
    w = open_world()
    place(w, 20.0, 20.0, carrying=True)
    w.step()
    w.pheromone[:] = 3.0
    assert w.observe().pheromone.sum() > 0
    deposits = w.deposit_events
    assert w.disable_communication() is True
    assert w.disable_communication() is False  # already off
    assert w.observe().pheromone.sum() == 0
    w.step()
    assert w.deposit_events == deposits
    assert w.events[-1]["type"] == "communication_disabled"


# -------------------------------------------------------------------- obstacle
def test_dynamic_obstacle_blocks_cells_and_keeps_everything_reachable():
    w = make(seed=2, food_capacity=10**6).run(200)
    blocked_before = w.obstacles.sum()
    assert w.add_default_obstacle() is True
    assert w.obstacles.sum() > blocked_before
    assert w.events[-1]["type"] == "obstacle_added" and w.events[-1]["step"] == 200
    ax, ay = np.floor(w.x).astype(int), np.floor(w.y).astype(int)
    assert np.isfinite(w.geo[ay, ax]).all()
    assert np.isfinite(w.geo[np.floor(w.food_y).astype(int), np.floor(w.food_x).astype(int)]).all()
    assert w.pheromone[w.obstacles].sum() == 0


def test_obstacle_on_the_nest_is_refused():
    w = make()
    assert w.add_obstacle_segment(w.nest[0] - 1, w.nest[1], w.nest[0] + 1, w.nest[1]) is False
    assert not w.events


# --------------------------------------------------------------------- metrics
def test_undefined_metrics_are_none_not_zero():
    m = compute_metrics(make())
    assert m["first_delivery_step"] is None
    assert m["travel_efficiency"] is None
    assert m["delivery_rate_per_100"] is None
    assert m["food_delivered"] == 0  # a true zero stays a zero
    assert ratio(5, 0) is None and ratio(None, 2) is None and ratio(6, 3) == 2


def test_metric_values_after_a_run():
    w = make(seed=1).run(600)
    m = compute_metrics(w)
    assert m["food_delivered"] == w.delivered_history[-1] > 0
    assert m["delivery_rate_per_100"] == pytest.approx(100 * w.delivered / 600)
    assert 0 < m["exploration_coverage"] <= 1
    assert 0 < m["travel_efficiency"] <= 1
    assert window_deliveries(w, 0, 600) == w.delivered
    assert window_deliveries(w, 200, 400) == w.delivered_history[400] - w.delivered_history[200]
    assert window_deliveries(w, 0, 601) is None


def test_traffic_concentration_bounds():
    w = make()
    assert traffic_concentration(np.zeros_like(w.visits), w) is None
    assert traffic_concentration(np.ones_like(w.visits), w) == pytest.approx(0.05, abs=0.001)
    one_cell = np.zeros_like(w.visits)
    one_cell[5, 5] = 100
    assert traffic_concentration(one_cell, w) == 1.0


def test_describe_and_paired_handle_undefined_values():
    d = describe([1.0, None, 3.0])
    assert (d["n"], d["n_undefined"], d["mean"]) == (3, 1, 2.0)
    assert describe([None])["mean"] is None
    p = paired([12, 14, None], [10, 10, 10], "b", "a")
    assert p["n_pairs"] == 2 and p["mean_difference"] == 3.0
    assert p["relative_difference_pct"] == pytest.approx(30.0)
    assert p["ci95"][0] <= 3.0 <= p["ci95"][1]
    assert paired([None], [1], "b", "a")["mean_difference"] is None


# --------------------------------------------------------------- reproducibility
@pytest.mark.parametrize("mode", ["independent", "collective", "interrupted"])
def test_same_seed_reproduces_the_same_trajectory(mode):
    a = World(world_config(SimConfig(seed=11), mode, 150)).run(300)
    b = World(world_config(SimConfig(seed=11), mode, 150)).run(300)
    assert a.digest() == b.digest()
    assert a.delivered_history == b.delivered_history


def test_different_seeds_differ():
    assert make(seed=1).run(50).digest() != make(seed=2).run(50).digest()
