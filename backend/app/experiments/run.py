"""Reproducible multi-seed experiment runner.

    python -m app.experiments.run                 # full default experiment
    python -m app.experiments.run --seeds 3 --steps 600 --out /tmp/x   # quick check

Writes summary.json, runs.csv, series.json and PNG charts. Every number in
those files is measured from simulations executed by this command.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from app import __version__
from app.config import SimConfig, world_config, world_overrides
from app.experiments.stats import describe, paired
from app.metrics import compute_metrics, ratio, traffic_concentration
from app.simulation.world import World

SERIES_STRIDE = 50
EXPERIMENTS_DIR = Path(os.environ.get("SWARM_EXPERIMENTS_DIR", Path(__file__).resolve().parents[3] / "experiments"))
RUN_METRICS = ("food_delivered", "first_delivery_step", "exploration_coverage", "travel_efficiency",
               "delivery_rate_per_100", "food_relocations", "deposit_events", "pheromone_sensed_total")
CSV_COLUMNS = ("group", "variant", "mode", "seed", "steps", *RUN_METRICS, "traffic_concentration", "digest")


def simulate(job: dict) -> dict:
    """Runs one world to completion and returns its measurements."""
    cfg = SimConfig(**job["config"])
    steps, trail_window = job["steps"], min(job["trail_window"], job["steps"])
    world = World(cfg).run(steps - trail_window)
    visits_before = world.visits.copy()
    world.run(trail_window)
    window_visits = world.visits - visits_before
    metrics = compute_metrics(world)
    record = {k: job[k] for k in ("group", "variant", "mode", "seed", "steps")}
    record.update({k: metrics[k] for k in RUN_METRICS})
    record["traffic_concentration"] = traffic_concentration(window_visits, world)
    record["series"] = world.delivered_history[::SERIES_STRIDE]
    record["events"] = world.events
    record["digest"] = world.digest()
    if job.get("keep_visits"):
        record["_visits"] = window_visits
        record["_obstacles"] = world.obstacles
    return record


def window(record: dict, start: int, end: int) -> int:
    """Deliveries during steps [start, end); both must be multiples of SERIES_STRIDE."""
    return record["series"][end // SERIES_STRIDE] - record["series"][start // SERIES_STRIDE]


def build_jobs(spec: dict) -> list[dict]:
    steps = spec["steps"]
    jobs: list[dict] = []

    def add(group, variant, mode, seed, base: dict, extra: dict | None = None, **flags):
        cfg = world_config(SimConfig(seed=seed, **base), mode, spec["interruption_step"])
        if extra:
            cfg = cfg.model_copy(update=extra)
        jobs.append({"group": group, "variant": variant, "mode": mode, "seed": seed, "steps": steps,
                     "trail_window": spec["trail_window"], "config": cfg.model_dump(), **flags})

    for seed in spec["seeds"]:
        first = seed == spec["seeds"][0]
        for mode in ("independent", "collective", "interrupted"):
            add("core", "default", mode, seed, spec["base"], keep_visits=first)
        for mode in ("independent", "collective"):
            base = {**spec["base"], **spec["obstacle_base"]}
            add("obstacle", "control", mode, seed, base)
            add("obstacle", "obstacle", mode, seed, base, {"obstacle_step": spec["obstacle_step"]})
        for overrides in spec.get("sensitivity", []):
            variant = "+".join(f"{k}={v}" for k, v in overrides.items())
            for mode in ("independent", "collective"):
                add("sensitivity", variant, mode, seed, {**spec["base"], **overrides})
    return jobs


def run_jobs(jobs: list[dict], workers: int | None = None) -> list[dict]:
    if workers == 1 or len(jobs) < 4:
        return [simulate(j) for j in jobs]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(simulate, jobs, chunksize=4))


def _select(records, group, variant, mode) -> list[dict]:
    rows = [r for r in records if (r["group"], r["variant"], r["mode"]) == (group, variant, mode)]
    return sorted(rows, key=lambda r: r["seed"])


def _col(rows, key) -> list:
    return [r[key] for r in rows]


def compare_modes(records, group, variant, metrics=("food_delivered",)) -> dict:
    """Per-mode summary plus the paired collective-minus-independent effect."""
    a, b = _select(records, group, variant, "independent"), _select(records, group, variant, "collective")
    out = {}
    for metric in metrics:
        out[metric] = {
            "independent": describe(_col(a, metric)),
            "collective": describe(_col(b, metric)),
            "communication_effect": paired(_col(b, metric), _col(a, metric), "collective", "independent"),
        }
    return out


def summarise(records: list[dict], spec: dict) -> dict:
    steps, t_int, t_obs, w = spec["steps"], spec["interruption_step"], spec["obstacle_step"], spec["window"]
    core = {m: _select(records, "core", "default", m) for m in ("independent", "collective", "interrupted")}
    a, b, c = core["independent"], core["collective"], core["interrupted"]

    exp1 = compare_modes(records, "core", "default",
                         ("food_delivered", "first_delivery_step", "exploration_coverage",
                          "travel_efficiency", "delivery_rate_per_100"))

    exp2 = {
        "definition": "share of agent position samples on the 5% most-visited reachable cells "
                      f"(nest area excluded) during the last {spec['trail_window']} steps",
        "uniform_reference": 0.05,
        "independent": describe(_col(a, "traffic_concentration")),
        "collective": describe(_col(b, "traffic_concentration")),
        "difference": paired(_col(b, "traffic_concentration"), _col(a, "traffic_concentration"),
                             "collective", "independent"),
    }

    pre = {m: [window(r, 0, t_int) for r in rows] for m, rows in core.items()}
    post = {m: [window(r, t_int, steps) for r in rows] for m, rows in core.items()}
    exp3 = {
        "interruption_step": t_int,
        "pre_window": [0, t_int],
        "post_window": [t_int, steps],
        # B and C share seed, map and rules until the interruption, so they must match exactly.
        "pre_interruption_trajectories_identical":
            all(rb["series"][: t_int // SERIES_STRIDE + 1] == rc["series"][: t_int // SERIES_STRIDE + 1]
                for rb, rc in zip(b, c)),
        "pre_deliveries": {m: describe(v) for m, v in pre.items()},
        "post_deliveries": {m: describe(v) for m, v in post.items()},
        "interrupted_vs_collective_post": paired(post["interrupted"], post["collective"], "interrupted", "collective"),
        "interrupted_vs_independent_post": paired(post["interrupted"], post["independent"], "interrupted", "independent"),
    }

    exp4 = {"obstacle_step": t_obs, "window": w,
            "windows": {"pre": [t_obs - w, t_obs], "post_early": [t_obs, t_obs + w], "post_late": [steps - w, steps]},
            "recovery_definition": "deliveries in post_late window / deliveries in pre window, per run "
                                   "(undefined when the pre window has no deliveries)"}
    for mode in ("independent", "collective"):
        ctrl, obst = _select(records, "obstacle", "control", mode), _select(records, "obstacle", "obstacle", mode)
        block = {"obstacle_inserted_in": f"{sum(1 for r in obst if r['events'])}/{len(obst)}"}
        for name, (s, e) in exp4["windows"].items():
            block[name] = {
                "control": describe([window(r, s, e) for r in ctrl]),
                "obstacle": describe([window(r, s, e) for r in obst]),
                "obstacle_vs_control": paired([window(r, s, e) for r in obst], [window(r, s, e) for r in ctrl],
                                              "obstacle", "control"),
            }
        s0, e0 = exp4["windows"]["pre"]
        s2, e2 = exp4["windows"]["post_late"]
        s1, e1 = exp4["windows"]["post_early"]
        block["immediate_ratio"] = describe([ratio(window(r, s1, e1), window(r, s0, e0)) for r in obst])
        block["recovery_ratio"] = describe([ratio(window(r, s2, e2), window(r, s0, e0)) for r in obst])
        block["control_ratio"] = describe([ratio(window(r, s2, e2), window(r, s0, e0)) for r in ctrl])
        exp4[mode] = block
    exp4["communication_effect_after_obstacle"] = paired(
        [window(r, t_obs, steps) for r in _select(records, "obstacle", "obstacle", "collective")],
        [window(r, t_obs, steps) for r in _select(records, "obstacle", "obstacle", "independent")],
        "collective", "independent")

    sensitivity = {"default": exp1["food_delivered"]}
    for variant in dict.fromkeys(r["variant"] for r in records if r["group"] == "sensitivity"):
        sensitivity[variant] = compare_modes(records, "sensitivity", variant)["food_delivered"]

    return {
        "exp1_baseline_food_collection": exp1,
        "exp2_trail_emergence": exp2,
        "exp3_communication_failure": exp3,
        "exp4_dynamic_obstacle": exp4,
        "exp5_multiple_seeds": {"seeds": spec["seeds"], "runs_per_condition": len(spec["seeds"]),
                                "total_runs": len(records)},
        "exp6_sensitivity": sensitivity,
    }


def mean_series(records: list[dict]) -> dict:
    out = {}
    for key in sorted({(r["group"], r["variant"], r["mode"]) for r in records}):
        data = np.array([r["series"] for r in _select(records, *key)], dtype=float)
        out["/".join(key)] = {"mean": data.mean(axis=0).round(2).tolist(),
                              "sd": (data.std(axis=0, ddof=1) if len(data) > 1 else data.std(axis=0)).round(2).tolist()}
    return out


def _source_revision() -> str | None:
    try:
        root = Path(__file__).resolve().parents[3]
        rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=root, capture_output=True, text=True, timeout=5)
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True, timeout=5)
        if rev.returncode != 0:
            return None
        return rev.stdout.strip() + ("+uncommitted" if dirty.stdout.strip() else "")
    except (OSError, subprocess.SubprocessError):
        return None


def quick_comparison(seeds: list[int], steps: int, interruption_step: int, base: dict | None = None) -> dict:
    """Small three-world comparison used by the dashboard's "Run experiment" button."""
    jobs = []
    for seed in seeds:
        for mode in ("independent", "collective", "interrupted"):
            cfg = world_config(SimConfig(seed=seed, **(base or {})), mode, interruption_step)
            jobs.append({"group": "core", "variant": "default", "mode": mode, "seed": seed, "steps": steps,
                         "trail_window": steps, "config": cfg.model_dump()})
    records = [simulate(j) for j in jobs]
    by_mode = {m: _select(records, "core", "default", m) for m in ("independent", "collective", "interrupted")}
    delivered = {m: _col(rows, "food_delivered") for m, rows in by_mode.items()}
    return {
        "kind": "quick",
        "seeds": seeds, "steps": steps, "interruption_step": interruption_step,
        "food_delivered": {m: describe(v) for m, v in delivered.items()},
        "per_seed": delivered,
        "collective_vs_independent": paired(delivered["collective"], delivered["independent"], "collective", "independent"),
        "interrupted_vs_collective": paired(delivered["interrupted"], delivered["collective"], "interrupted", "collective"),
    }


def main(argv: list[str] | None = None) -> Path:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, default=EXPERIMENTS_DIR / "configs" / "default.json")
    parser.add_argument("--out", type=Path, default=EXPERIMENTS_DIR / "results")
    parser.add_argument("--seeds", type=int, help="use only the first N seeds of the config")
    parser.add_argument("--steps", type=int, help="override run length (interventions move to the midpoint)")
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--no-charts", action="store_true")
    args = parser.parse_args(argv)

    spec = json.loads(args.config.read_text(encoding="utf-8"))
    if args.seeds:
        spec["seeds"] = spec["seeds"][: args.seeds]
    if args.steps:
        half = (args.steps // 2 // 100) * 100
        spec.update(steps=args.steps, interruption_step=half, obstacle_step=half,
                    window=min(spec["window"], half), trail_window=min(spec["trail_window"], half))
    for key in ("steps", "interruption_step", "obstacle_step", "window"):
        if spec[key] % SERIES_STRIDE:
            raise SystemExit(f"{key} must be a multiple of {SERIES_STRIDE}")

    jobs = build_jobs(spec)
    print(f"Running {len(jobs)} simulations ({len(spec['seeds'])} seeds x {spec['steps']} steps) ...", flush=True)
    started = time.time()
    records = run_jobs(jobs, args.workers)
    elapsed = time.time() - started

    args.out.mkdir(parents=True, exist_ok=True)
    summary = {
        "manifest": {
            "experiment": spec["name"],
            "data": "synthetic - generated by the Swarm Mind simulator; no real-world or biological data",
            "simulator_version": __version__,
            "source_revision": _source_revision(),
            "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "python": platform.python_version(),
            "numpy": np.__version__,
            "platform": platform.platform(),
            "runtime_seconds": round(elapsed, 1),
            "command": "python -m app.experiments.run",
            "spec": spec,
            "default_config": SimConfig().model_dump(),
            "world_differences": {m: world_overrides(m, spec["interruption_step"])
                                  for m in ("independent", "collective", "interrupted")},
            "statistics": "mean / sd / median over seeds; paired differences with a 10,000-resample percentile "
                          "bootstrap 95% interval and Cohen's dz. No significance tests are performed.",
        },
        "results": summarise(records, spec),
    }
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (args.out / "series.json").write_text(
        json.dumps({"stride": SERIES_STRIDE, "series": mean_series(records)}), encoding="utf-8")
    with (args.out / "runs.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(CSV_COLUMNS)
        for r in sorted(records, key=lambda r: (r["group"], r["variant"], r["mode"], r["seed"])):
            writer.writerow(["" if r[c] is None else r[c] for c in CSV_COLUMNS])

    if not args.no_charts:
        from app.experiments.charts import render_all
        render_all(records, summary, args.out)

    effect = summary["results"]["exp1_baseline_food_collection"]["food_delivered"]["communication_effect"]
    print(f"Done in {elapsed:.0f}s. Collective - independent food delivered: "
          f"{effect['mean_difference']:+.1f} (95% CI {effect['ci95'][0]:+.1f}..{effect['ci95'][1]:+.1f}, "
          f"n={effect['n_pairs']} seeds). Results in {args.out}", flush=True)
    return args.out


if __name__ == "__main__":
    main()
