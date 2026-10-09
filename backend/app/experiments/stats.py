"""Small descriptive statistics helpers. No significance tests are reported:
we give means, spread, paired differences, a bootstrap interval and an effect
size, and let the reader judge."""
from __future__ import annotations

import numpy as np

BOOTSTRAP_RESAMPLES = 10_000
BOOTSTRAP_SEED = 12345


def describe(values: list) -> dict:
    """Summary of a metric across runs. Undefined (None) values are counted,
    reported and excluded — never treated as zero."""
    defined = np.array([v for v in values if v is not None], dtype=float)
    out = {"n": len(values), "n_undefined": len(values) - len(defined)}
    if len(defined) == 0:
        return {**out, "mean": None, "sd": None, "median": None, "min": None, "max": None}
    return {
        **out,
        "mean": float(defined.mean()),
        "sd": float(defined.std(ddof=1)) if len(defined) > 1 else None,
        "median": float(np.median(defined)),
        "min": float(defined.min()),
        "max": float(defined.max()),
    }


def paired(treatment: list, baseline: list, treatment_name: str, baseline_name: str) -> dict:
    """Seed-matched comparison: treatment minus baseline, pair by pair.

    ci95 is a percentile bootstrap over seeds of the mean paired difference.
    effect_size_dz is mean(diff) / sd(diff) (Cohen's d for paired samples)."""
    pairs = [(t, b) for t, b in zip(treatment, baseline) if t is not None and b is not None]
    out = {"treatment": treatment_name, "baseline": baseline_name,
           "n_pairs": len(pairs), "n_undefined_pairs": len(treatment) - len(pairs)}
    if not pairs:
        return {**out, "mean_difference": None, "ci95": None, "effect_size_dz": None,
                "relative_difference_pct": None, "treatment_higher_in": None}
    t = np.array([p[0] for p in pairs], dtype=float)
    b = np.array([p[1] for p in pairs], dtype=float)
    diff = t - b
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    means = diff[rng.integers(0, len(diff), (BOOTSTRAP_RESAMPLES, len(diff)))].mean(axis=1)
    sd = diff.std(ddof=1) if len(diff) > 1 else 0.0
    return {
        **out,
        "mean_difference": float(diff.mean()),
        "ci95": [float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))],
        "effect_size_dz": float(diff.mean() / sd) if sd > 0 else None,
        "relative_difference_pct": float(100.0 * diff.mean() / b.mean()) if b.mean() != 0 else None,
        "treatment_higher_in": f"{int((diff > 0).sum())}/{len(diff)}",
    }
