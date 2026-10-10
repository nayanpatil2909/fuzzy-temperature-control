"""
simulation.py
=============
Simplified first-order thermal simulation model.

IMPORTANT: This is a SOFTWARE SIMULATION, not a real HVAC model.
It is used exclusively to demonstrate the behaviour of the fuzzy
controller under dynamic conditions.

Thermal Model
-------------
  T(t+1) = T(t)
           + α · (T_ambient − T(t))          ← natural heat drift toward ambient
           − β · (cooling_power / 100)        ← active cooling effect
           + η                                ← optional sensor noise  N(0, σ)
           + d(t)                             ← disturbance at step t_d

Parameters
----------
  α = 0.025  thermal drift coefficient (room gains heat from ambient)
  β = 0.80   cooling effectiveness (°C removed per step at 100 % power)
  σ = 0.10   sensor noise standard deviation (when noise is enabled)
  d(t)       one-shot heat-load disturbance of magnitude Δ°C at step t_d

Threshold Controller (for comparison)
--------------------------------------
  ON–OFF bang-bang with hysteresis band (default ±1 °C):
    T > target + band  →  cooling = 100 %
    T < target - band  →  cooling = 0 %
    otherwise          →  hold previous cooling state
"""

import numpy as np
import random
from typing import Optional

from fuzzy_controller import mamdani_inference

# ---------------------------------------------------------------------------
# Simulation constants
# ---------------------------------------------------------------------------
ALPHA = 0.025    # thermal drift (heat gain from ambient environment)
BETA  = 0.80     # cooling effectiveness (°C per step at 100% power)
SIGMA = 0.10     # noise standard deviation


# ---------------------------------------------------------------------------
# Threshold (bang-bang) controller
# ---------------------------------------------------------------------------

def threshold_controller(
    t_current: float,
    t_target: float,
    prev_cooling: float,
    hysteresis: float = 1.0,
) -> float:
    """Simple hysteresis bang-bang controller for comparison purposes."""
    if t_current > t_target + hysteresis:
        return 100.0
    if t_current < t_target - hysteresis:
        return 0.0
    return prev_cooling   # hold inside the dead-band


# ---------------------------------------------------------------------------
# Single-controller simulation
# ---------------------------------------------------------------------------

def run_simulation(
    target_temperature: float,
    initial_temperature: float,
    humidity: float,
    n_steps: int = 100,
    enable_noise: bool = False,
    disturbance_at_step: int = 50,
    disturbance_magnitude: float = 5.0,
    controller_type: str = "fuzzy",
    noise_filter: str = "none",        # "none" | "moving_avg" | "ema"
    filter_window: int = 3,
    ema_alpha: float = 0.3,
) -> list[dict]:
    """
    Run a time-step simulation and return a list of step-by-step records.

    Parameters
    ----------
    target_temperature    : desired setpoint (°C)
    initial_temperature   : starting room temperature (°C)
    humidity              : fixed humidity for this run (%)
    n_steps               : number of simulation steps
    enable_noise          : inject Gaussian sensor noise
    disturbance_at_step   : step index at which to inject a heat disturbance
    disturbance_magnitude : size of the disturbance (°C, added once)
    controller_type       : "fuzzy" | "threshold"
    noise_filter          : optional noise filter
    filter_window         : window size for moving average
    ema_alpha             : smoothing factor for EMA filter
    """
    T_ambient = initial_temperature   # ambient = no-cooling equilibrium
    T = initial_temperature
    prev_error   = 0.0
    prev_cooling = 0.0

    # Noise filter state
    raw_buffer: list[float] = []          # for moving average
    ema_state: Optional[float] = None     # for EMA

    records: list[dict] = []

    for step in range(n_steps + 1):

        # ---- Sensor noise -----------------------------------------------
        noise = random.gauss(0, SIGMA) if enable_noise else 0.0
        T_measured = T + noise

        # ---- Optional noise filtering -----------------------------------
        if noise_filter == "moving_avg":
            raw_buffer.append(T_measured)
            if len(raw_buffer) > filter_window:
                raw_buffer.pop(0)
            T_filtered = float(np.mean(raw_buffer))
        elif noise_filter == "ema":
            if ema_state is None:
                ema_state = T_measured
            else:
                ema_state = ema_alpha * T_measured + (1 - ema_alpha) * ema_state
            T_filtered = ema_state
        else:
            T_filtered = T_measured

        # ---- Compute error -----------------------------------------------
        error = target_temperature - T_filtered          # e = T_target − T_current
        delta_error = error - prev_error                 # Δe = e(t) − e(t−1)

        # ---- Controller decision ----------------------------------------
        if controller_type == "fuzzy":
            result = mamdani_inference(error, delta_error, humidity)
            cooling_power = result["cooling_power"]
        else:
            cooling_power = threshold_controller(T_filtered, target_temperature, prev_cooling)

        # ---- Record current state BEFORE updating temperature -----------
        disturbance_applied = False
        if step == disturbance_at_step and disturbance_magnitude != 0:
            disturbance_applied = True

        records.append({
            "step":                  step,
            "temperature":           round(T, 3),
            "temperature_measured":  round(T_measured, 3),
            "temperature_filtered":  round(T_filtered, 3),
            "target_temperature":    target_temperature,
            "error":                 round(error, 3),
            "delta_error":           round(delta_error, 3),
            "cooling_power":         round(cooling_power, 2),
            "disturbance_applied":   disturbance_applied,
            "ambient_temperature":   T_ambient,
        })

        # ---- Disturbance injection (one-shot heat spike) ----------------
        if step == disturbance_at_step:
            T += disturbance_magnitude

        # ---- Thermal dynamics -------------------------------------------
        heat_gain    = ALPHA * (T_ambient - T)
        cooling_loss = BETA  * (cooling_power / 100.0)
        T = T + heat_gain - cooling_loss

        # ---- Carry state forward ----------------------------------------
        prev_error   = error
        prev_cooling = cooling_power

    return records


# ---------------------------------------------------------------------------
# Comparative simulation (fuzzy vs threshold, same conditions)
# ---------------------------------------------------------------------------

def run_comparison(
    target_temperature: float,
    initial_temperature: float,
    humidity: float,
    n_steps: int = 100,
    disturbance_at_step: int = 50,
    disturbance_magnitude: float = 5.0,
) -> dict:
    """
    Run both controllers under identical conditions and compute
    performance metrics for side-by-side comparison.
    """
    random.seed(42)   # reproducible
    fuzzy_records = run_simulation(
        target_temperature, initial_temperature, humidity,
        n_steps=n_steps,
        disturbance_at_step=disturbance_at_step,
        disturbance_magnitude=disturbance_magnitude,
        controller_type="fuzzy",
    )

    random.seed(42)   # same noise seed
    threshold_records = run_simulation(
        target_temperature, initial_temperature, humidity,
        n_steps=n_steps,
        disturbance_at_step=disturbance_at_step,
        disturbance_magnitude=disturbance_magnitude,
        controller_type="threshold",
    )

    # ---- Compute metrics ------------------------------------------------
    def compute_metrics(records: list[dict]) -> dict:
        temps   = [r["temperature"] for r in records]
        cooling = [r["cooling_power"] for r in records]
        target  = target_temperature

        # 2 % settling band  (minimum 0.5 °C)
        delta = abs(initial_temperature - target)
        band = max(0.5, 0.02 * delta)
        band  = max(0.5, 0.02 * delta)
        # 10 consecutive stable steps required for a reliable settle
        settling_time = next(
            (r["step"] for r in records[1:]
             if all(abs(s["temperature"] - target) <= band
                    for s in records[r["step"]: min(r["step"] + 10, len(records))])),
            n_steps,
        )

        errors   = [t - target for t in temps]
        # Overshoot: temp drops more than 5 % of initial error below target
        overshoot_threshold = max(0.5, 0.05 * delta)
        overshoot_vals = [e for e in errors if e < -overshoot_threshold]
        overshoot = abs(min(overshoot_vals)) if overshoot_vals else 0.0
        sse       = float(np.mean([e**2 for e in errors]))
        iae       = float(np.mean([abs(e) for e in errors]))
        control_effort = float(np.mean(cooling))
        control_variation = float(np.std(np.diff(cooling)))

        return {
            "settling_time_steps": settling_time,
            "overshoot_deg":       round(overshoot, 3),
            "steady_state_error":  round(abs(np.mean(errors[-10:])), 3),
            "mean_squared_error":  round(sse, 4),
            "integral_abs_error":  round(iae, 3),
            "mean_control_effort": round(control_effort, 2),
            "control_variation":   round(control_variation, 4),
            "temperature_std":     round(float(np.std(temps[-20:])), 4),
        }

    return {
        "fuzzy":     {"records": fuzzy_records,     "metrics": compute_metrics(fuzzy_records)},
        "threshold": {"records": threshold_records, "metrics": compute_metrics(threshold_records)},
    }
