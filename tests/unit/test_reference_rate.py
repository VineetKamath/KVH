"""Reference rate (D-17): removes independent night-to-night jitter, keeps structure a hotel intends.

Synthetic calendars with a known truth, so the test says what the method does on data it was not built on."""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np

from app.forecast.reference_rate import fit

START = date(2026, 9, 1)
WEEKEND = {4: 1.22, 5: 1.22, 6: 1.22}  # Fri-Sun premium


def _calendar(rng: np.random.Generator, rooms: int, nights: int, noise_sd: float, festival: tuple[int, int] | None = None,
              lift: float = 1.0):
    rows, truth = [], {}
    for r in range(rooms):
        level = 3000 + 400 * r
        for n in range(nights):
            d = START + timedelta(days=n)
            t = level * WEEKEND.get(d.weekday(), 1.0)
            if festival and festival[0] <= n < festival[1]:
                t *= lift
            truth[(f"rm{r}", d.isoformat())] = t
            rows.append((f"rm{r}", d.isoformat(), t * float(np.exp(rng.normal(0, noise_sd)))))
    return rows, truth


def _mean_abs_log_err(ref: dict, truth: dict) -> float:
    return float(np.mean([abs(np.log(ref[k] / truth[k])) for k in truth]))


def test_independent_jitter_is_removed_and_weekday_profile_recovered():
    rng = np.random.default_rng(1)
    rows, truth = _calendar(rng, rooms=40, nights=90, noise_sd=0.07)
    f = fit(rows)
    raw = {(e, d): p for e, d, p in rows}
    assert f.residual_weight < 0.15                      # no persistence → jitter dropped
    assert _mean_abs_log_err(f.reference, truth) < 0.4 * _mean_abs_log_err(raw, truth)
    assert f.jitter_after < 0.6 * f.jitter_before
    prof = np.array(f.weekday_profile)
    assert abs(prof[5] / prof[1] - 1.22) < 0.03          # weekend premium recovered


def test_persistent_multi_night_premium_is_kept():
    """A festival week the hotel priced up is structure, not noise: residuals are autocorrelated, ρ rises and
    the reference keeps most of the lift."""
    rng = np.random.default_rng(2)
    rows, truth = _calendar(rng, rooms=40, nights=90, noise_sd=0.02, festival=(40, 47), lift=1.30)
    f = fit(rows)
    assert f.residual_weight > 0.3
    kept = np.mean([f.reference[(f"rm{r}", (START + timedelta(days=n)).isoformat())] /
                    truth[(f"rm{r}", (START + timedelta(days=n)).isoformat())] for r in range(40) for n in range(40, 47)])
    assert kept > 0.9                                     # within 10% of the true festival price on average


def test_empty_and_single_room_inputs_are_safe():
    assert fit([]).reference == {}
    rows = [("rm", (START + timedelta(days=n)).isoformat(), 5000.0) for n in range(10)]
    f = fit(rows)
    assert all(abs(v - 5000.0) < 1e-6 for v in f.reference.values())
