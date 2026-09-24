"""The ONLY place forecast constants live (ARCHITECTURE §7.7, G3).

Every value here is a data-free design choice (a statistical convention or a prior strength), not a
number fitted to APS-02.db. Everything data-dependent (rates, shrinkage strength k, credibility κ,
seasonal indices, cancellation rates, pickup curves, the rate window) is estimated from whatever
history the system is running on. `tests/unit/test_forecast_no_fitted_literals.py` fails the build if
a numeric literal appears in forecast/ outside this file.
"""

HORIZON_DAYS = 90            # the forward inventory calendar length
WINDOW_DAYS = 7              # forecast signal = centred 7-day sum (the forecastable grain)
QUANTILES = (0.1, 0.9)       # P10 / P90
TARGET_COVERAGE = 0.8        # P10-P90 nominal coverage
ACI_GAMMA = 0.05             # adaptive conformal step size per calibration batch (Gibbs & Candès 2021)
RATE_WINDOWS = (28, 56, 90, 180)   # candidate trailing windows; the best is chosen by nested validation
PICKUP_LOOKBACK_DAYS = 180   # stay dates used to estimate the lead-time (pickup) curve
PICKUP_PRIOR_BOOKINGS = 50   # prior strength when shrinking a local pickup curve to the national one
CANCEL_PRIOR_BOOKINGS = 20   # prior strength when shrinking a local cancellation rate
CANCEL_RECENT_DAYS = 28      # "recent" cancellation window for the cancellation-risk factor
TRAIN_WEEKS = 26             # rolling history used for model training and selection
CALIBRATION_ORIGINS = 4      # most recent origins held out for calibration + champion/challenger
CREDIBILITY_MIN = 0.3        # finest hierarchy level with z >= this is used for pricing
BAND_HIGH = 0.6              # z >= 0.6 → confidence_band 'high'
MIN_P50_FOR_WIDTH = 1.0      # relative width uses max(P50, this) so empty series do not explode
SCORE_OFFSET = 0.25          # variance-stabilising offset in the normalised conformity score
MAD_K = 5.0                  # robust outlier cut (median ± MAD_K · 1.4826 · MAD)
SELECTION_MIN_WINS = 3       # challenger must win >= 3 of the last CALIBRATION_ORIGINS origins
SELECTION_P_VALUE = 0.05     # and pass a Diebold-Mariano style paired test at this level
SELECTION_MIN_GAIN = 0.02    # and improve Poisson deviance by at least 2%
LGBM_PARAMS = {              # fixed, conservative; deliberately NOT tuned on this dataset
    "learning_rate": 0.03,
    "num_leaves": 15,
    "min_data_in_leaf": 200,
    "lambda_l2": 2.0,
    "feature_fraction": 0.8,
    "bagging_fraction": 0.8,
    "bagging_freq": 1,
    "seed": 7,
    "deterministic": True,
    "force_row_wise": True,
    "num_threads": 1,
    "verbose": -1,
}
LGBM_ROUNDS = 300
PSI_ALERT = 0.25             # conventional population-stability threshold for a significant shift
PSI_BINS = 10
COVERAGE_BAND = (0.70, 0.90)  # monitor alert band around the 0.80 target
KAPPA_LOOKBACK_WEEKS = 52    # history used to estimate the signal variance behind credibility κ

# price response (simulator only; ARCHITECTURE §7.6) — a stated prior, not a fitted value
ELASTICITY_PRIOR_MEAN = -1.0     # hotel-literature midpoint
ELASTICITY_PRIOR_SD = 0.5
PRICE_RATIO_BUCKETS = (0.0, 0.85, 0.95, 1.05, 1.15, float("inf"))
ELASTICITY_MIN_CELL_EVENTS = 3
ELASTICITY_MIN_CELLS = 10
Z_80 = 1.2816                    # two-sided 80% normal interval
MAD_SCALE = 1.4826               # MAD → standard deviation under normality
TINY = 1e-6
