"""Static result charts, drawn only from the records/summary of an executed run."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

SURFACE, INK, INK2, MUTED, GRID = "#1a1a19", "#ffffff", "#c3c2b7", "#898781", "#2c2c2a"
COLORS = {"independent": "#3987e5", "collective": "#d95926", "interrupted": "#199e70"}
LABELS = {"independent": "Independent", "collective": "Collective", "interrupted": "Communication breakdown"}
STRIDE = 50

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "text.color": INK, "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.edgecolor": "#383835", "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "axes.spines.top": False, "axes.spines.right": False, "font.size": 11,
    "axes.titlesize": 13, "axes.titleweight": "bold", "axes.titlelocation": "left",
    "legend.frameon": False, "figure.dpi": 150,
})


def _rows(records, group, variant, mode):
    rows = [r for r in records if (r["group"], r["variant"], r["mode"]) == (group, variant, mode)]
    return sorted(rows, key=lambda r: r["seed"])


def _save(fig, out: Path, name: str, note: str):
    fig.text(0.01, -0.03, note, color=MUTED, fontsize=8, ha="left", va="top")
    fig.savefig(out / name, bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)


def render_all(records: list[dict], summary: dict, out: Path) -> None:
    spec = summary["manifest"]["spec"]
    n, steps, t_int, t_obs = len(spec["seeds"]), spec["steps"], spec["interruption_step"], spec["obstacle_step"]
    note = f"Synthetic simulation data · {n} seeds · Swarm Mind v{summary['manifest']['simulator_version']}"
    x = np.arange(0, steps + 1, STRIDE)
    modes = ("independent", "collective", "interrupted")
    core = {m: np.array([r["series"] for r in _rows(records, "core", "default", m)], dtype=float) for m in modes}

    # 1. cumulative food curves
    fig, ax = plt.subplots(figsize=(9, 5))
    for m in modes:
        mean, sd = core[m].mean(0), core[m].std(0, ddof=1) if n > 1 else 0
        ax.fill_between(x, mean - sd, mean + sd, color=COLORS[m], alpha=0.18, linewidth=0)
        ax.plot(x, mean, color=COLORS[m], linewidth=2, label=LABELS[m])
        ax.annotate(f"{mean[-1]:.0f}", (x[-1], mean[-1]), xytext=(6, 0), textcoords="offset points",
                    color=INK, va="center", fontsize=10)
    ax.axvline(t_int, color=MUTED, linewidth=1, linestyle=(0, (4, 3)))
    ax.annotate("communication cut\n(breakdown world only)", (t_int, ax.get_ylim()[1]), xytext=(-6, -4),
                textcoords="offset points", ha="right", va="top", color=INK2, fontsize=9)
    ax.set(title="Food delivered to the nest (mean ± 1 SD across seeds)", xlabel="simulation step",
           ylabel="cumulative food delivered", xlim=(0, steps))
    ax.legend(loc="upper left")
    _save(fig, out, "food_delivered_curves.png", note)

    # 2. per-seed outcomes
    fig, ax = plt.subplots(figsize=(7, 5))
    jitter = np.random.default_rng(0).uniform(-0.12, 0.12, n)
    for i, m in enumerate(modes):
        final = core[m][:, -1]
        ax.scatter(i + jitter, final, s=34, color=COLORS[m], edgecolor=SURFACE, linewidth=1, zorder=3)
        ax.hlines(final.mean(), i - 0.28, i + 0.28, color=INK, linewidth=2, zorder=4)
        ax.annotate(f"mean {final.mean():.0f}", (i + 0.3, final.mean()), xytext=(4, 0),
                    textcoords="offset points", va="center", fontsize=10, color=INK)
    ax.set_xticks(range(3), [LABELS[m].replace(" ", "\n", 1) for m in modes])
    ax.set(title=f"Food delivered after {steps} steps — one dot per seed", ylabel="food delivered",
           xlim=(-0.5, 2.9), ylim=(0, None))
    ax.grid(axis="x", visible=False)
    _save(fig, out, "food_delivered_by_seed.png", note)

    # 3. interruption windows
    e3 = summary["results"]["exp3_communication_failure"]
    fig, ax = plt.subplots(figsize=(8, 5))
    width = 0.26
    for i, m in enumerate(modes):
        for j, key in enumerate(("pre_deliveries", "post_deliveries")):
            d = e3[key][m]
            pos = j + (i - 1) * (width + 0.02)
            ax.bar(pos, d["mean"], width, color=COLORS[m], label=LABELS[m] if j == 0 else None)
            ax.errorbar(pos, d["mean"], yerr=d["sd"] or 0, color=INK2, linewidth=1.2, capsize=3)
            ax.annotate(f"{d['mean']:.0f}", (pos, d["mean"] + (d["sd"] or 0)), xytext=(0, 4),
                        textcoords="offset points", ha="center", fontsize=10, color=INK)
    ax.set_xticks([0, 1], [f"before the cut\nsteps 0–{t_int}", f"after the cut\nsteps {t_int}–{steps}"])
    ax.set(title="Deliveries before and after communication is cut (mean ± 1 SD)", ylabel="food delivered in window")
    ax.grid(axis="x", visible=False)
    ax.legend(loc="upper left")
    _save(fig, out, "interruption_windows.png", note)

    # 4. dynamic obstacle: delivery rate over time
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), sharey=True)
    xr = np.arange(100, steps + 1, 100)
    for ax, m in zip(axes, ("independent", "collective")):
        for variant, style, alpha in (("control", (0, (4, 3)), 0.75), ("obstacle", "solid", 1.0)):
            data = np.array([r["series"] for r in _rows(records, "obstacle", variant, m)], dtype=float)
            rate = (data[:, 2::2] - data[:, :-2:2]).mean(0)
            ax.plot(xr, rate, color=COLORS[m], linewidth=2, linestyle=style, alpha=alpha,
                    label="no obstacle (control)" if variant == "control" else "obstacle inserted")
        ax.axvline(t_obs, color=MUTED, linewidth=1, linestyle=(0, (1, 2)))
        ax.set(title=LABELS[m], xlabel="simulation step", xlim=(0, steps))
        ax.legend(loc="lower right")
    axes[0].set_ylabel("food delivered per 100 steps")
    axes[0].set_ylim(0, None)
    axes[0].annotate("wall inserted", (t_obs, 0), xytext=(5, 6), textcoords="offset points", color=INK2, fontsize=9)
    fig.suptitle("Dynamic obstacle: delivery rate with and without the new wall (static food sources)",
                 x=0.01, y=1.02, ha="left", fontweight="bold", fontsize=13)
    _save(fig, out, "obstacle_recovery.png", note)

    # 5. sensitivity of the communication effect
    sens = summary["results"]["exp6_sensitivity"]
    names = list(sens)
    fig, ax = plt.subplots(figsize=(9, 0.5 * len(names) + 1.8))
    for i, name in enumerate(names):
        eff, base = sens[name]["communication_effect"], sens[name]["independent"]["mean"]
        if eff["relative_difference_pct"] is None:
            continue
        lo, hi = (100 * v / base for v in eff["ci95"])
        ax.plot([lo, hi], [i, i], color=COLORS["collective"], linewidth=2)
        ax.scatter(eff["relative_difference_pct"], i, s=60, color=COLORS["collective"], edgecolor=SURFACE,
                   linewidth=1.5, zorder=3)
        ax.annotate(f"{eff['relative_difference_pct']:+.0f}%", (hi, i), xytext=(8, 0),
                    textcoords="offset points", va="center", fontsize=10, color=INK)
    ax.axvline(0, color=INK2, linewidth=1)
    ax.set_yticks(range(len(names)), names)
    ax.invert_yaxis()
    ax.grid(axis="y", visible=False)
    ax.margins(x=0.12)
    ax.set(title="Communication effect on food delivered, by condition",
           xlabel="collective vs independent, % difference in mean food delivered (bar: bootstrap 95% interval)")
    _save(fig, out, "sensitivity.png", note)

    # 6. where agents walked (first seed)
    maps = {m: next((r for r in _rows(records, "core", "default", m) if "_visits" in r), None)
            for m in ("independent", "collective")}
    if all(maps.values()):
        fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
        vmax = max(np.log1p(r["_visits"]).max() for r in maps.values())
        for ax, (m, r) in zip(axes, maps.items()):
            cmap = LinearSegmentedColormap.from_list(
                "ramp", [SURFACE, "#184f95", "#3987e5", "#cde2fb"]).with_extremes(bad="#55544f")
            img = np.ma.masked_where(r["_obstacles"], np.log1p(r["_visits"]))
            im = ax.imshow(img, cmap=cmap, vmin=0, vmax=vmax, interpolation="nearest")
            ax.set_title(f"{LABELS[m]} — concentration {r['traffic_concentration']:.2f}")
            ax.set_xticks([]), ax.set_yticks([]), ax.grid(False)
        fig.colorbar(im, ax=axes, shrink=0.8, label="log(1 + visits per cell)")
        fig.suptitle(f"Where agents walked during the last {spec['trail_window']} steps (seed {spec['seeds'][0]}; "
                     "grey = obstacles)", x=0.01, ha="left", fontweight="bold", fontsize=13)
        _save(fig, out, "traffic_maps.png", note)
