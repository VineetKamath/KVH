"""Vectorised event panel: integer arrays over which every as-of computation runs.

Series are ordered: every city, then every region, then one national series. Region and national
counts are sums of their member cities, so the hierarchy always adds up exactly.
Pure: takes a DataFrame of events, returns numpy arrays. No I/O, no clock.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

EVENT_TYPES = ("search", "view", "booking", "cancellation", "abandon")
EPOCH = date.fromordinal(1)  # day numbers are proleptic ordinals; no magic epoch


def day_number(d: date) -> int:
    return (d - EPOCH).days


@dataclass
class Panel:
    city_ids: list[str]
    regions: list[str]
    city_region: np.ndarray        # (n_city,) region index of each city
    typ: np.ndarray                # event type code
    city: np.ndarray               # city index per event
    occ: np.ndarray                # occurred day number
    fd: np.ndarray                 # stay day number
    lead: np.ndarray               # lead time in days
    agg: np.ndarray                # (n_series, n_city) 0/1 membership matrix: cities, regions, national

    @property
    def n_city(self) -> int:
        return len(self.city_ids)

    @property
    def n_series(self) -> int:
        return self.agg.shape[0]

    def series_labels(self) -> list[tuple[str, str]]:
        return ([("city", c) for c in self.city_ids] + [("region", r) for r in self.regions] + [("national", "all")])

    def series_region(self) -> np.ndarray:
        """Region index per series (-1 for the national series)."""
        return np.concatenate([self.city_region, np.arange(len(self.regions)), [-1]])


def build_panel(events: pd.DataFrame) -> Panel:
    """events columns: event_type, city_id, region, occurred_date (date), for_date (date), lead_time_days."""
    cities = events[["city_id", "region"]].drop_duplicates().sort_values(["region", "city_id"])
    city_ids = cities["city_id"].tolist()
    regions = sorted(cities["region"].unique().tolist())
    region_index = {r: i for i, r in enumerate(regions)}
    city_index = {c: i for i, c in enumerate(city_ids)}
    city_region = np.array([region_index[r] for r in cities["region"]], dtype=np.int64)
    n_city, n_reg = len(city_ids), len(regions)
    agg = np.zeros((n_city + n_reg + 1, n_city), dtype=np.float64)
    agg[np.arange(n_city), np.arange(n_city)] = 1.0
    agg[n_city + city_region, np.arange(n_city)] = 1.0
    agg[-1, :] = 1.0
    typ_map = {t: i for i, t in enumerate(EVENT_TYPES)}
    return Panel(
        city_ids=city_ids,
        regions=regions,
        city_region=city_region,
        typ=events["event_type"].map(typ_map).to_numpy(dtype=np.int64),
        city=events["city_id"].map(city_index).to_numpy(dtype=np.int64),
        occ=np.array([day_number(d) for d in events["occurred_date"]], dtype=np.int64),
        fd=np.array([day_number(d) for d in events["for_date"]], dtype=np.int64),
        lead=events["lead_time_days"].to_numpy(dtype=np.int64),
        agg=agg,
    )


def type_code(name: str) -> int:
    return EVENT_TYPES.index(name)


def forward_counts(p: Panel, as_of: int, horizon: int, typ: str, known_only: bool) -> np.ndarray:
    """Counts per (series, h) for stay days as_of+1 … as_of+horizon.
    known_only=True → only events that occurred before as_of (on the books); False → everything (realised)."""
    m = (p.typ == type_code(typ)) & (p.fd > as_of) & (p.fd <= as_of + horizon)
    if known_only:
        m &= p.occ < as_of
    city = np.zeros((p.n_city, horizon))
    np.add.at(city, (p.city[m], p.fd[m] - as_of - 1), 1.0)
    return p.agg @ city


def trailing_counts(p: Panel, as_of: int, window: int, typ: str = "booking") -> np.ndarray:
    """Per-series count of `typ` events whose stay day is in [as_of - window, as_of) (complete stay dates)."""
    m = (p.typ == type_code(typ)) & (p.fd >= as_of - window) & (p.fd < as_of) & (p.occ < as_of)
    city = np.bincount(p.city[m], minlength=p.n_city).astype(np.float64)
    return p.agg @ city


def recent_occurred_counts(p: Panel, as_of: int, window: int, typ: str) -> np.ndarray:
    """Per-series count of `typ` events that occurred in [as_of - window, as_of)."""
    m = (p.typ == type_code(typ)) & (p.occ >= as_of - window) & (p.occ < as_of)
    city = np.bincount(p.city[m], minlength=p.n_city).astype(np.float64)
    return p.agg @ city


def centred_window_sum(x: np.ndarray, width: int) -> np.ndarray:
    """Centred rolling sum along axis 1, rescaled at the edges to a full-width equivalent."""
    half = width // 2
    padded = np.pad(x, ((0, 0), (half, half)))
    kernel = np.ones(width)
    out = np.apply_along_axis(lambda r: np.convolve(r, kernel, mode="valid"), 1, padded)
    n = np.convolve(np.ones(x.shape[1]), kernel, mode="full")[half: half + x.shape[1]]
    return out * (width / n)
