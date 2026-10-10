"""
membership_functions.py
=======================
Defines all fuzzy membership functions (MFs) used in the Mamdani FLC.

Universes of discourse
----------------------
  Temperature Error  e   : [-15, +15] °C   (e = T_target - T_current)
  Rate of Error     Δe   : [-5,  +5]  °C/step
  Humidity          H    : [0,   100] %
  Cooling Output    u    : [0,   100] %

Sign convention (IMPORTANT)
---------------------------
  e < 0  →  room is HOTTER than target  →  Negative error  →  More cooling needed
  e > 0  →  room is COOLER than target  →  Positive error  →  Less cooling needed

MF types
--------
  trimf   (a, b, c)     triangular
  trapmf  (a, b, c, d)  trapezoidal
"""

import numpy as np
from typing import Union


# ---------------------------------------------------------------------------
# Primitive MF functions — scalar version
# ---------------------------------------------------------------------------

def trimf_scalar(x: float, a: float, b: float, c: float) -> float:
    """Triangular membership function for a single crisp value.

    Parameters
    ----------
    x : crisp input value
    a : left foot  (μ = 0)
    b : peak       (μ = 1)
    c : right foot (μ = 0)
    """
    if x <= a or x >= c:
        return 0.0
    if x == b:
        return 1.0
    if a < x < b:
        return (x - a) / (b - a)
    # b < x < c
    return (c - x) / (c - b)


def trapmf_scalar(x: float, a: float, b: float, c: float, d: float) -> float:
    """Trapezoidal membership function for a single crisp value.

    Parameters
    ----------
    x       : crisp input value
    a, b    : rising edge  (a → foot, b → shoulder)
    c, d    : falling edge (c → shoulder, d → foot)

    Note: when a == b the left edge is a vertical wall (flat from a onward);
          when c == d the right edge is a vertical wall (flat up to d).
          Both boundary points are included in the plateau (μ = 1).
    """
    # Strictly outside both feet → 0
    if x < a or x > d:
        return 0.0
    # On the plateau (including shoulder points)
    if b <= x <= c:
        return 1.0
    # Rising slope  a ≤ x < b
    if x < b:
        if b == a:
            return 1.0          # vertical left wall — x==a is on plateau
        return (x - a) / (b - a)
    # Falling slope  c < x ≤ d
    if d == c:
        return 1.0              # vertical right wall — x==d is on plateau
    return (d - x) / (d - c)


# ---------------------------------------------------------------------------
# Primitive MF functions — vector version (for curve plotting)
# ---------------------------------------------------------------------------

def trimf_vec(x: np.ndarray, a: float, b: float, c: float) -> np.ndarray:
    """Triangular MF evaluated over a NumPy array of points."""
    mu = np.zeros_like(x, dtype=float)
    # Rising slope
    rising = (x > a) & (x < b)
    if b != a:
        mu[rising] = (x[rising] - a) / (b - a)
    # Peak
    mu[x == b] = 1.0
    # Falling slope
    falling = (x > b) & (x < c)
    if c != b:
        mu[falling] = (c - x[falling]) / (c - b)
    return mu


def trapmf_vec(x: np.ndarray, a: float, b: float, c: float, d: float) -> np.ndarray:
    """Trapezoidal MF evaluated over a NumPy array of points."""
    mu = np.zeros_like(x, dtype=float)
    mu[(x >= b) & (x <= c)] = 1.0
    rising = (x > a) & (x < b)
    if b != a:
        mu[rising] = (x[rising] - a) / (b - a)
    falling = (x > c) & (x < d)
    if d != c:
        mu[falling] = (d - x[falling]) / (d - c)
    return mu


# ---------------------------------------------------------------------------
# MF parameter tables
# ---------------------------------------------------------------------------

# Each entry: (type, *params)
#   "tri"  → trimf_scalar(x, a, b, c)
#   "trap" → trapmf_scalar(x, a, b, c, d)

ERROR_MF_PARAMS: dict = {
    "NB": ("trap", -15, -15,  -8,  -4),
    "NS": ("tri",   -8,  -4,   0),
    "ZE": ("tri",   -3,   0,   3),
    "PS": ("tri",    0,   4,   8),
    "PB": ("trap",   4,   8,  15,  15),
}

DELTA_MF_PARAMS: dict = {
    "NB": ("trap", -5, -5, -3, -1),
    "NS": ("tri",  -3, -1,  0),
    "ZE": ("tri",  -1,  0,  1),
    "PS": ("tri",   0,  1,  3),
    "PB": ("trap",  1,  3,  5,  5),
}

HUMIDITY_MF_PARAMS: dict = {
    "Low":    ("trap",  0,  0, 30, 50),
    "Medium": ("tri",  30, 50, 70),
    "High":   ("trap", 60, 80, 100, 100),
}

COOLING_MF_PARAMS: dict = {
    "VL": ("trap",  0,  0, 10, 25),
    "L":  ("tri",  10, 25, 40),
    "M":  ("tri",  30, 50, 70),
    "H":  ("tri",  60, 75, 90),
    "VH": ("trap", 75, 90, 100, 100),
}

# Discrete universe for centroid defuzzification (101 equally spaced points)
COOLING_UNIVERSE: np.ndarray = np.linspace(0, 100, 201)


# ---------------------------------------------------------------------------
# Scalar MF evaluation helper
# ---------------------------------------------------------------------------

def _eval_scalar(x: float, params: tuple) -> float:
    """Dispatch a scalar evaluation based on the MF type tag."""
    mf_type = params[0]
    args = params[1:]
    if mf_type == "tri":
        return trimf_scalar(x, *args)
    if mf_type == "trap":
        return trapmf_scalar(x, *args)
    raise ValueError(f"Unknown MF type: {mf_type}")


def _eval_vec(x: np.ndarray, params: tuple) -> np.ndarray:
    """Dispatch a vector evaluation based on the MF type tag."""
    mf_type = params[0]
    args = params[1:]
    if mf_type == "tri":
        return trimf_vec(x, *args)
    if mf_type == "trap":
        return trapmf_vec(x, *args)
    raise ValueError(f"Unknown MF type: {mf_type}")


# ---------------------------------------------------------------------------
# Fuzzification functions — return dict {label: membership_degree}
# ---------------------------------------------------------------------------

def fuzzify_error(e: float) -> dict:
    """Fuzzify the temperature error into the five linguistic sets."""
    return {label: _eval_scalar(e, params) for label, params in ERROR_MF_PARAMS.items()}


def fuzzify_delta_error(de: float) -> dict:
    """Fuzzify the rate of change of error into the five linguistic sets."""
    return {label: _eval_scalar(de, params) for label, params in DELTA_MF_PARAMS.items()}


def fuzzify_humidity(h: float) -> dict:
    """Fuzzify the humidity percentage into the three linguistic sets."""
    return {label: _eval_scalar(h, params) for label, params in HUMIDITY_MF_PARAMS.items()}


# ---------------------------------------------------------------------------
# Output MF evaluation (vector, used during aggregation)
# ---------------------------------------------------------------------------

def cooling_mf_vector(u: np.ndarray, label: str) -> np.ndarray:
    """Return the output MF curve for the given linguistic label."""
    return _eval_vec(u, COOLING_MF_PARAMS[label])


# ---------------------------------------------------------------------------
# MF curve data — used by the GET /membership-functions endpoint
# ---------------------------------------------------------------------------

def get_mf_curves() -> dict:
    """Return all MF curves as (x, y) lists for frontend plotting."""
    error_x = np.linspace(-15, 15, 301).tolist()
    delta_x = np.linspace(-5, 5, 201).tolist()
    humidity_x = np.linspace(0, 100, 201).tolist()
    cooling_x = np.linspace(0, 100, 201).tolist()

    error_x_arr   = np.array(error_x)
    delta_x_arr   = np.array(delta_x)
    humidity_x_arr = np.array(humidity_x)
    cooling_x_arr  = np.array(cooling_x)

    return {
        "error": {
            "universe": error_x,
            "sets": {
                label: _eval_vec(error_x_arr, params).tolist()
                for label, params in ERROR_MF_PARAMS.items()
            }
        },
        "delta_error": {
            "universe": delta_x,
            "sets": {
                label: _eval_vec(delta_x_arr, params).tolist()
                for label, params in DELTA_MF_PARAMS.items()
            }
        },
        "humidity": {
            "universe": humidity_x,
            "sets": {
                label: _eval_vec(humidity_x_arr, params).tolist()
                for label, params in HUMIDITY_MF_PARAMS.items()
            }
        },
        "cooling": {
            "universe": cooling_x,
            "sets": {
                label: _eval_vec(cooling_x_arr, params).tolist()
                for label, params in COOLING_MF_PARAMS.items()
            }
        },
        "parameters": {
            "error": ERROR_MF_PARAMS,
            "delta_error": DELTA_MF_PARAMS,
            "humidity": HUMIDITY_MF_PARAMS,
            "cooling": COOLING_MF_PARAMS,
        }
    }


# ---------------------------------------------------------------------------
# Humidity modifier (Low=0.85, Medium=1.00, High=1.15)
# ---------------------------------------------------------------------------

HUMIDITY_MODIFIER_MAP: dict = {
    "Low":    0.85,
    "Medium": 1.00,
    "High":   1.15,
}


def compute_humidity_modifier(mu_humidity: dict) -> float:
    """
    Compute the humidity scaling factor using fuzzy weighted average.

    modifier = Σ(μ_label × factor_label) / Σ(μ_label)

    Pure Low    → 0.85   (dry air, less cooling demand)
    Pure Medium → 1.00   (neutral)
    Pure High   → 1.15   (humid air, more cooling demand)

    Intermediate humidities get a smooth, proportionally interpolated factor.
    """
    numerator   = sum(mu_humidity[lbl] * HUMIDITY_MODIFIER_MAP[lbl] for lbl in mu_humidity)
    denominator = sum(mu_humidity.values())
    if denominator == 0:
        return 1.00
    return numerator / denominator
