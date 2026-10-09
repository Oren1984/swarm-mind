"""Scientific integrity tests: the three worlds differ only as declared."""
import inspect

import numpy as np

from app.config import WORLD_MODES, SimConfig, world_config, world_overrides
from app.session import Session
from app.simulation import agents
from app.simulation.world import World

STEPS = 700
CUT = 400


def world(mode, seed=4, cut=CUT, **kw) -> World:
    return World(world_config(SimConfig(seed=seed, **kw), mode, cut))


def test_world_configs_differ_only_in_declared_communication_fields():
    dumps = {m: world_config(SimConfig(seed=9), m, CUT).model_dump() for m in WORLD_MODES}
    differing = {k for k in dumps["independent"] if len({str(d[k]) for d in dumps.values()}) > 1}
    assert differing == {"communication", "interruption_step"}
    assert set(world_overrides("collective", CUT)) == {"communication", "interruption_step"}


def test_worlds_start_from_the_identical_map_food_and_agents():
    worlds = [world(m) for m in WORLD_MODES]
    ref = worlds[0]
    for w in worlds[1:]:
        for attr in ("obstacles", "geo", "food_x", "food_y", "food_amount", "x", "y", "heading"):
            assert np.array_equal(getattr(ref, attr), getattr(w, attr)), attr
        assert w.nest == ref.nest


def test_independent_world_never_deposits_or_senses_pheromone():
    w = world("independent").run(STEPS)
    assert w.delivered > 0  # the baseline is functional, not crippled
    assert w.deposit_events == 0
    assert w.pheromone.sum() == 0
    assert w.pheromone_sensed_total == 0


def test_independent_world_ignores_a_pheromone_field_even_if_one_existed():
    a, b = world("independent"), world("independent")
    b.pheromone[:] = 5.0  # plant a field by hand; agents must not react to it
    for _ in range(100):
        a.step(), b.step()
        b.pheromone[:] = 5.0
    assert np.array_equal(a.x, b.x) and np.array_equal(a.y, b.y) and a.delivered == b.delivered


def test_collective_world_uses_the_declared_mechanism():
    w = world("collective").run(STEPS)
    assert w.deposit_events > 0
    assert w.pheromone.sum() > 0
    assert w.pheromone_sensed_total > 0
    assert w.comm_active and w.comm_disabled_step is None


def test_collective_equals_independent_until_the_first_deposit():
    """Before any pheromone exists, the two worlds must be the same simulation."""
    a, b = world("independent"), world("collective")
    compared = 0
    while b.deposit_events == 0 and b.t < 2000:
        assert np.array_equal(a.x, b.x) and np.array_equal(a.y, b.y) and np.array_equal(a.carrying, b.carrying)
        a.step(), b.step()
        compared += 1
    assert compared > 5 and b.deposit_events > 0


def test_advantage_can_only_come_through_the_pheromone_field():
    """With zero deposit strength the collective world IS the independent world:
    there is no hidden route, memory or bonus attached to the collective mode."""
    a = world("independent", deposit=0.0).run(STEPS)
    b = world("collective", deposit=0.0).run(STEPS)
    assert a.delivered_history == b.delivered_history
    assert np.array_equal(a.x, b.x) and np.array_equal(a.visits, b.visits)


def test_interrupted_world_matches_collective_exactly_until_the_cut():
    b, c = world("collective").run(CUT), world("interrupted").run(CUT)
    assert b.digest() == c.digest()
    assert c.comm_active  # the cut applies from step CUT onward
    b.step(), c.step()
    assert not c.comm_active and c.comm_disabled_step == CUT


def test_interrupted_world_stops_all_communication_at_the_configured_step():
    c = world("interrupted").run(CUT)
    deposits, sensed = c.deposit_events, c.pheromone_sensed_total
    assert deposits > 0 and sensed > 0
    c.step()
    field_after_cut = c.pheromone.sum()
    assert field_after_cut > 0  # old trails remain visible for a while ...
    c.run(STEPS - CUT - 1)
    assert c.deposit_events == deposits  # ... but nothing is added
    assert c.pheromone_sensed_total == sensed  # ... and nothing is read
    assert c.pheromone.sum() < field_after_cut * 0.2  # they only fade
    assert c.events == [{"type": "communication_disabled", "step": CUT, "source": "scheduled"}]


def test_decision_function_cannot_see_the_world():
    """`decide` takes local observations only — no world, map, food list or other agents."""
    params = list(inspect.signature(agents.decide).parameters)
    assert params == ["obs", "carrying", "heading", "u_choice", "noise", "u_escape", "cfg"]
    assert set(agents.Observation.__dataclass_fields__) == {
        "ray_free", "pheromone", "nest_scent", "food_visible", "food_bearing"}
    source = inspect.getsource(agents)
    for forbidden in ("World", "scenario", "food_x", "geodesic", "obstacles"):
        assert forbidden not in source, forbidden


def _share_near_routes(field, w_routes, tolerance=8.0):
    """Share of pheromone mass within `tolerance` of a straight nest-to-food line of world w_routes."""
    from app.simulation.scenario import rasterize_segment
    near = np.zeros(field.shape, dtype=bool)
    for fx, fy in zip(w_routes.food_x, w_routes.food_y):
        near |= rasterize_segment(field.shape, w_routes.nest[0], w_routes.nest[1], fx, fy, tolerance)
    return field[near].sum() / field.sum()


def test_trails_are_not_hardcoded_they_follow_the_food():
    """Pheromone accumulates between the nest and wherever this map's food
    happens to be: each map's field fits its own food layout much better than
    the other map's layout."""
    a = world("collective", seed=4, food_capacity=10**6).run(STEPS)
    b = world("collective", seed=5, food_capacity=10**6).run(STEPS)
    for own, other in ((a, b), (b, a)):
        fit_own, fit_other = _share_near_routes(own.pheromone, own), _share_near_routes(own.pheromone, other)
        assert fit_own > 0.9
        assert fit_own > fit_other + 0.15


def test_step_batching_does_not_change_the_outcome():
    """Rendering speed only changes how many steps are requested per call."""
    one, many = Session(SimConfig(seed=6), 60), Session(SimConfig(seed=6), 60)
    for _ in range(120):
        one.step(1)
    many.step(50), many.step(70)
    for mode in WORLD_MODES:
        assert one.worlds[mode].digest() == many.worlds[mode].digest()
