"""Aggregate price response for the SIMULATOR ONLY (ARCHITECTURE §7.6). Never used in the live price path.

Sessions in the data hold exactly one event, so per-search conversion cannot be learned. Instead:
cells = city × stay-week × price-ratio bucket (quoted price / the entity's median quoted price, MAD-filtered);
booking share = bookings / (searches + views + bookings) per cell; slope of log(share) on log(ratio) by
weighted least squares; combined with a stated normal prior (mean −1.0, sd 0.5) as a precision-weighted
posterior. The result is shown as an assumption with its interval, and revenue is always a range.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.forecast import defaults as C

PRIOR_MEAN = C.ELASTICITY_PRIOR_MEAN
PRIOR_SD = C.ELASTICITY_PRIOR_SD
RATIO_BUCKETS = C.PRICE_RATIO_BUCKETS


def estimate(events: pd.DataFrame) -> dict:
    e = events[events["quoted_price"].notna()].copy()
    if e.empty:
        return _prior_only("no quoted prices")
    e["price"] = e["quoted_price"].astype(str).map(np.float64)  # ratio statistics only; never flows back into a price
    med = e.groupby("entity_id")["price"].transform("median")
    mad = e.groupby("entity_id")["price"].transform(lambda s: (s - s.median()).abs().median())
    e = e[(mad == 0) | ((e["price"] - med).abs() <= C.MAD_K * C.MAD_SCALE * mad)]
    e["ratio"] = e["price"] / med
    e["bucket"] = pd.cut(e["ratio"], RATIO_BUCKETS, labels=False)
    e["week"] = e["for_date"].map(lambda d: d.isocalendar()[:2])
    g = e.groupby(["city_id", "week", "bucket"])
    cells = pd.DataFrame({
        "n": g.size(),
        "bookings": g.apply(lambda x: (x["event_type"] == "booking").sum(), include_groups=False),
        "ratio": g["ratio"].mean(),
    }).reset_index()
    cells = cells[(cells["n"] >= C.ELASTICITY_MIN_CELL_EVENTS) & (cells["bookings"] > 0)]
    if len(cells) < C.ELASTICITY_MIN_CELLS:
        return _prior_only("too few cells")
    y = np.log(cells["bookings"] / cells["n"])
    x = np.log(cells["ratio"])
    w = cells["n"].to_numpy(dtype=float)
    xm, ym = np.average(x, weights=w), np.average(y, weights=w)
    sxx = np.sum(w * (x - xm) ** 2)
    if sxx <= 0:
        return _prior_only("no price variation")
    slope = float(np.sum(w * (x - xm) * (y - ym)) / sxx)
    resid = y - (ym + slope * (x - xm))
    se = float(np.sqrt(np.sum(w * resid ** 2) / (w.sum() - 2) / sxx))
    prec_d, prec_p = 1 / max(se, C.TINY) ** 2, 1 / PRIOR_SD ** 2
    post = (slope * prec_d + PRIOR_MEAN * prec_p) / (prec_d + prec_p)
    post_sd = float(np.sqrt(1 / (prec_d + prec_p)))
    z = C.Z_80
    return {"elasticity": post, "interval80": [post - z * post_sd, post + z * post_sd], "data_slope": slope,
            "data_se": se, "cells": int(len(cells)), "prior": {"mean": PRIOR_MEAN, "sd": PRIOR_SD},
            "method": "aggregate cells, WLS slope + normal prior", "note": "assumption for simulation only"}


def _prior_only(why: str) -> dict:
    z = C.Z_80
    return {"elasticity": PRIOR_MEAN, "interval80": [PRIOR_MEAN - z * PRIOR_SD, PRIOR_MEAN + z * PRIOR_SD],
            "data_slope": None, "data_se": None, "cells": 0, "prior": {"mean": PRIOR_MEAN, "sd": PRIOR_SD},
            "method": f"prior only ({why})", "note": "assumption for simulation only"}
