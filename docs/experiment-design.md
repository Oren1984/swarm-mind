# Experiment design

Configuration: [`experiments/configs/default.json`](../experiments/configs/default.json). Runner: `backend/app/experiments/run.py`. All data is synthetic.

## Hypotheses

Stated before looking at results, so they can fail.

| # | Hypothesis | Outcome |
|---|---|---|
| H1 | Collective agents deliver more food than independent agents under default conditions. | Supported in this simulation. |
| H2 | Agent traffic is more spatially concentrated in the collective world. | Supported. |
| H3 | After communication is cut, the cut world delivers less than an uninterrupted collective world. | Supported. |
| H4 | After a wall is inserted, delivery rate returns to its pre-wall level. | **Not supported** for either world. |
| H5 | There are conditions under which communication gives no advantage. | Supported: one tested condition reversed the effect. |

## Conditions

| World | `communication` | `interruption_step` |
|---|---|---|
| A · Independent | `false` | — |
| B · Collective | `true` | — |
| C · Communication Breakdown | `true` | 1500 |

These two fields are the complete list of differences. `test_world_configs_differ_only_in_declared_communication_fields` fails if any other field differs.

## Controlled variables

Identical in every world of a seed, and verified by test:

- map geometry (120 × 80 cells, 6 random walls, nest at the centre),
- initial food sites (4), capacity (80 units) and relocation rule,
- number of agents (60), their start positions and headings,
- speed, sensing ranges, turning, noise,
- the nest-scent homing cue,
- the random stream that drives agent decisions,
- run length (3,000 steps) and every metric definition.

**Food relocation policy.** When a source is emptied it reappears at a new free site with full capacity. The *n*-th relocation in a run draws its site from its own generator seeded by `(seed, n)`, so every world draws the *n*-th site from the same generator state.

**Default parameters** are recorded in `summary.json` under `manifest.default_config`.

## Interventions

**Communication cut (World C).** From step 1500 onward, deposition *and* sensing are disabled. The existing pheromone field is left in place and continues to evaporate; it is drawn in grey in the dashboard; no agent reads it. Semantics in code: `World.disable_communication`. The step is configurable and is recorded in the world's event log and in the results.

**Dynamic obstacle.** At step 1500 a wall 22 cells long is inserted perpendicular to the straight line from the nest to the food source nearest to the nest (by walking distance), at the midpoint of that line. The rule depends only on geometry, never on where trails currently are. An insertion that would isolate a food source is refused. Agents standing where the wall appears are moved to the nearest free cell. The nest scent is recomputed immediately — agents "know" the new way home at once, which is a simplification.

For the obstacle experiment only, food capacity is set to 1,000,000 so sources never move. Otherwise the wall's position would relate to different food layouts in different worlds. This applies to both arms and to both worlds.

## Experiments

| # | Name | Runs per seed | Comparison |
|---|---|---|---|
| 1 | Baseline food collection | A, B | B − A on food delivered and other metrics |
| 2 | Trail emergence | same runs | B − A on traffic concentration, last 1,000 steps |
| 3 | Communication failure | C (plus B, A from Exp. 1) | Deliveries in steps 1500–3000: C vs B, C vs A |
| 4 | Dynamic obstacle | A, B × {wall, no wall}, static food | Delivery in 500-step windows before, right after, and at the end |
| 5 | Multiple seeds | — | All of the above over 20 seeds |
| 6 | Sensitivity | A, B for each of 11 parameter variants | B − A on food delivered |

Experiment 6 variants: evaporation 0, 0.002, 0.05, 0.2; food sources 1, 12; agents 10, 150; food capacity 10, 1,000,000; and evaporation 0 combined with food capacity 10.

**Honest note on Experiment 6.** The combined variant was added after a first full run, specifically to look for a condition where communication fails. It is exploratory, not preregistered. Its result is reported as measured.

Total: 580 runs of 3,000 steps.

## Seeds

Seeds 1 to 20, listed in the config and in `summary.json`. A seed fixes the map, the food sites, the agents and all randomness. Nothing was cherry-picked: every seed in the list is in every aggregate. The dashboard's default view shows seed 1.

## Metrics

Let `T` be the number of steps run, `D(t)` cumulative deliveries after step `t`.

| Metric | Definition | Undefined when |
|---|---|---|
| Food delivered | `D(T)`: units dropped inside the nest radius. | — |
| First delivery time | Smallest `t` with `D(t) > 0`. | No delivery occurred (`None`). |
| Exploration coverage | Reachable cells on which at least one agent stood ÷ reachable cells. | — |
| Travel efficiency | Σ over deliveries of 2 × (walking distance from pickup point to nest) ÷ total distance walked by all agents. The numerator is the least travel those round trips required. 1 would mean no step was wasted. | Total distance is 0 (`None`). |
| Delivery rate | `100 × D(T) / T`, deliveries per 100 steps. Windowed: `D(b) − D(a)` for steps `[a, b)`. | `T = 0` (`None`). |
| Obstacle recovery | Deliveries in the last 500 steps ÷ deliveries in the 500 steps before the wall. *Immediate ratio* uses the 500 steps right after the wall. *Control ratio* is the same quantity in the matched no-wall run. | Pre-wall window has 0 deliveries (`None`). |
| Communication effect | Seed-paired difference, collective minus independent. | A value is missing for that seed. |
| Traffic concentration | Share of agent position samples falling on the 5% most-visited reachable cells, nest area excluded. Even traffic gives 0.05. Computed from positions, not from pheromone, so it is defined for World A too. | No samples (`None`). |

Undefined values are stored as empty CSV cells / JSON `null`, counted (`n_undefined`) and excluded from means. They are never replaced by zero. In the stored experiment no value was undefined.

## Statistics

For each condition: mean, standard deviation, median, minimum, maximum over seeds.

For each comparison: mean of the seed-paired differences; a percentile bootstrap 95% interval for that mean (10,000 resamples of seeds, fixed bootstrap seed 12345); Cohen's d for paired samples (`dz` = mean difference ÷ SD of differences); relative difference as a percentage of the baseline mean; and in how many seeds the treatment was higher.

**No p-values are reported.** The simulation is deterministic given a seed and seeds are a convenience sample of scenarios, so a significance test would add a number without adding understanding. The interval and the per-seed win count carry the information.

`dz` values here are very large (above 5). That reflects low run-to-run noise in a simulation, not a large effect in any external sense.

## Fairness limitations

- **Shared homing cue.** All worlds get the nest scent. It removes navigation-home as a source of difference and makes all agents better than a pure random walker.
- **No memory in the baseline.** A solitary forager that remembered its last food site would be a stronger and arguably fairer opponent. Not implemented in any world.
- **Carrier trails exist in World A too.** Because all carriers follow the same nest scent, independent agents also converge on similar return routes. The traffic-concentration baseline of 0.17 (not 0.05) reflects that.
- **Worlds diverge.** Once behaviour differs, worlds deplete food at different times, so later food layouts differ. Post-divergence comparisons are between whole trajectories, not between single mechanisms.
- **Experiment 3 confound.** At the cut, World C's agents are clustered on trails and its food sources are partly depleted; World A's are not. The comparison "C after the cut vs A" mixes loss of communication with different starting states. The comparison "C vs B" is cleaner, because C and B are verified identical up to the cut.
- **Experimenter-chosen parameters.** Defaults were set by hand after a brief look at behaviour, not by optimization, and not blind to outcome.

## Reproduction

```bash
# full experiment, about 5 minutes, rewrites experiments/results/
docker compose exec api python -m app.experiments.run

# reduced check: first 3 seeds, 1,000 steps, into a scratch directory
docker compose exec api python -m app.experiments.run --seeds 3 --steps 1000 --out /tmp/check
```

Without Docker, from `backend/`: `python -m app.experiments.run`.

**Reproducibility guarantee and its limit.** On one machine, the same seed and configuration reproduce identical trajectories (tested through a hash of the full state). Between a Windows host and the Linux container, a 58-run comparison gave identical delivery counts and metrics (one floating-point sum differed in its last digit), and an earlier full host run gave the same aggregate statistics for the conditions both runs shared, but the low-order bits of floating-point state differed (different math libraries). Cross-platform bit-identity is therefore not guaranteed, and over long runs small numeric differences could in principle change an outcome. The stored results were produced in the container; `summary.json` records Python, NumPy and platform versions.
