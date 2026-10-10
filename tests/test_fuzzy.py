"""
test_fuzzy.py
=============
Unit tests for the Mamdani Fuzzy Inference Engine.

Test cases cover all physically meaningful scenarios:
  1.  Temperature well below target  →  Very Low cooling
  2.  Temperature at target, stable  →  Low / Medium cooling
  3.  Temperature slightly above target → Medium cooling
  4.  Temperature significantly above target → High / Very High cooling
  5.  High humidity boost             →  cooling ≥ medium-humidity case
  6.  Low humidity reduction          →  cooling ≤ medium-humidity case
  7.  Rapid temperature rise (large negative Δe) → higher cooling than stable
  8.  Rapid temperature fall (large positive Δe) → lower cooling than stable
  9.  Extreme heat + worsening trend  → Very High cooling
  10. Boundary MF check               → membership degrees sum sanity

Run with:
    cd backend
    pytest ../tests/test_fuzzy.py -v

Or from repo root:
    pytest tests/test_fuzzy.py -v
"""

import sys
import os
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

import pytest
from fuzzy_controller import mamdani_inference
from membership_functions import (
    fuzzify_error,
    fuzzify_delta_error,
    fuzzify_humidity,
    compute_humidity_modifier,
    trimf_scalar,
    trapmf_scalar,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def infer(t_target: float, t_current: float, humidity: float, prev_error: float = 0.0) -> dict:
    """Convenience wrapper: computes e and Δe then calls mamdani_inference."""
    e  = t_target - t_current
    de = e - prev_error
    return mamdani_inference(e, de, humidity)


# ---------------------------------------------------------------------------
# Test 1 — Temperature well below target → minimal cooling
# ---------------------------------------------------------------------------

def test_temperature_below_target_gives_low_cooling():
    """
    Scenario: Target=24°C, Current=16°C  →  e=+8 (PB)
    Room is much colder than target. Cooling should be very low.
    """
    result = infer(t_target=24, t_current=16, humidity=50)
    assert result["cooling_power"] < 30, (
        f"Expected < 30%, got {result['cooling_power']}%  "
        f"(room is already cold, e = {result['temperature_error']})"
    )
    assert result["cooling_level"] in {"Very Low", "Low"}


# ---------------------------------------------------------------------------
# Test 2 — Temperature at target, stable → maintenance cooling
# ---------------------------------------------------------------------------

def test_temperature_at_target_stable_gives_moderate_cooling():
    """
    Scenario: Target=24°C, Current=24°C, Δe≈0
    Room is exactly at setpoint with no change trend.
    Cooling should be moderate — not zero (thermal loads exist) and not high.
    """
    result = infer(t_target=24, t_current=24, humidity=50, prev_error=0.0)
    assert 10 < result["cooling_power"] < 70, (
        f"Expected maintenance cooling 10–70%, got {result['cooling_power']}%"
    )


# ---------------------------------------------------------------------------
# Test 3 — Temperature slightly above target → medium cooling
# ---------------------------------------------------------------------------

def test_temperature_slightly_above_target_gives_medium_cooling():
    """
    Scenario: Target=24°C, Current=27°C  →  e=−3 (NS), stable (de≈0).
    prev_error is set to −3 so Δe = 0 (room is warm but not getting worse).
    Expected: moderate-to-high cooling (NS×ZE → H).
    """
    result = infer(t_target=24, t_current=27, humidity=50, prev_error=-3.0)
    assert 20 <= result["cooling_power"] <= 85, (
        f"Expected 20–85% for stable slight overshoot (NS), got {result['cooling_power']}%"
    )


# ---------------------------------------------------------------------------
# Test 4 — Temperature significantly above target → high/very high cooling
# ---------------------------------------------------------------------------

def test_temperature_significantly_above_target_gives_high_cooling():
    """
    Scenario: Target=24°C, Current=34°C  →  e=−10 (NB)
    Room is very hot. Should trigger Very High cooling.
    """
    result = infer(t_target=24, t_current=34, humidity=50)
    assert result["cooling_power"] >= 70, (
        f"Expected >= 70% for large overshoot, got {result['cooling_power']}%"
    )
    assert result["cooling_level"] in {"High", "Very High"}


# ---------------------------------------------------------------------------
# Test 5 — High humidity boosts cooling output
# ---------------------------------------------------------------------------

def test_high_humidity_increases_cooling():
    """
    High humidity (90%) modifier = 1.15  →  output ≥ medium humidity output.
    """
    base   = infer(t_target=24, t_current=30, humidity=50)
    humid  = infer(t_target=24, t_current=30, humidity=90)
    assert humid["cooling_power"] >= base["cooling_power"], (
        f"High humidity ({humid['cooling_power']:.1f}%) should be ≥ "
        f"medium humidity ({base['cooling_power']:.1f}%)"
    )
    assert humid["humidity_modifier"] >= 1.0


# ---------------------------------------------------------------------------
# Test 6 — Low humidity reduces cooling output
# ---------------------------------------------------------------------------

def test_low_humidity_decreases_cooling():
    """
    Low humidity (10%) modifier = 0.85  →  output ≤ medium humidity output.
    """
    base = infer(t_target=24, t_current=30, humidity=50)
    dry  = infer(t_target=24, t_current=30, humidity=10)
    assert dry["cooling_power"] <= base["cooling_power"], (
        f"Low humidity ({dry['cooling_power']:.1f}%) should be ≤ "
        f"medium humidity ({base['cooling_power']:.1f}%)"
    )
    assert dry["humidity_modifier"] <= 1.0


# ---------------------------------------------------------------------------
# Test 7 — Rapid temperature rise (large negative Δe) boosts cooling
# ---------------------------------------------------------------------------

def test_rapid_temperature_rise_increases_cooling():
    """
    Same error (e=−5, NS) but with a rapidly worsening Δe (−4 vs 0).
    The controller should respond more aggressively to the worsening trend.
    """
    stable = mamdani_inference(error=-5, delta_error=0.0, humidity=50)
    rising = mamdani_inference(error=-5, delta_error=-4.0, humidity=50)
    assert rising["cooling_power"] >= stable["cooling_power"], (
        f"Rapid rise ({rising['cooling_power']:.1f}%) should be ≥ "
        f"stable ({stable['cooling_power']:.1f}%)"
    )


# ---------------------------------------------------------------------------
# Test 8 — Rapid temperature fall (large positive Δe) reduces cooling
# ---------------------------------------------------------------------------

def test_rapid_temperature_fall_reduces_cooling():
    """
    Same error (e=−5, NS) but with rapidly improving Δe (+4 vs 0).
    Temperature is dropping fast; controller should ease off cooling.
    """
    stable  = mamdani_inference(error=-5, delta_error= 0.0, humidity=50)
    falling = mamdani_inference(error=-5, delta_error=+4.0, humidity=50)
    assert falling["cooling_power"] <= stable["cooling_power"], (
        f"Rapid fall ({falling['cooling_power']:.1f}%) should be ≤ "
        f"stable ({stable['cooling_power']:.1f}%)"
    )


# ---------------------------------------------------------------------------
# Test 9 — Extreme heat + worsening → Very High cooling
# ---------------------------------------------------------------------------

def test_extreme_heat_worsening_gives_very_high():
    """
    Worst case: room is already very hot (e=−12, NB) AND getting hotter (Δe=−4, NB).
    Should produce close to maximum cooling output.
    """
    result = mamdani_inference(error=-12, delta_error=-4.0, humidity=70)
    assert result["cooling_power"] >= 85, (
        f"Expected ≥ 85% for worst-case heat load, got {result['cooling_power']}%"
    )
    assert result["cooling_level"] == "Very High"


# ---------------------------------------------------------------------------
# Test 10 — Humidity modifier arithmetic
# ---------------------------------------------------------------------------

def test_humidity_modifier_values():
    """Verify that pure Low/Medium/High humidities produce exactly 0.85/1.00/1.15."""
    # Pure Low (humidity=0 → μ_Low=1, μ_Medium=0, μ_High=0)
    mu_low = fuzzify_humidity(0)
    assert abs(compute_humidity_modifier(mu_low) - 0.85) < 1e-6, \
        f"Pure Low modifier should be 0.85, got {compute_humidity_modifier(mu_low)}"

    # Pure Medium (humidity=50)
    mu_med = fuzzify_humidity(50)
    assert abs(compute_humidity_modifier(mu_med) - 1.00) < 1e-6, \
        f"Pure Medium modifier should be 1.00, got {compute_humidity_modifier(mu_med)}"

    # Pure High (humidity=100)
    mu_high = fuzzify_humidity(100)
    assert abs(compute_humidity_modifier(mu_high) - 1.15) < 1e-6, \
        f"Pure High modifier should be 1.15, got {compute_humidity_modifier(mu_high)}"


# ---------------------------------------------------------------------------
# Test 11 — MF coverage: every crisp error value fires at least one MF
# ---------------------------------------------------------------------------

def test_error_mf_full_coverage():
    """
    For any error in [-15, 15], the membership values should sum > 0
    (at least one MF is active — no dead zones).
    """
    import numpy as np
    for e in np.linspace(-15, 15, 61):
        mu = fuzzify_error(float(e))
        total = sum(mu.values())
        assert total > 0, f"No MF fires for error={e:.2f} — dead zone detected"


# ---------------------------------------------------------------------------
# Test 12 — Rule pipeline returns the required keys
# ---------------------------------------------------------------------------

def test_inference_result_structure():
    """The inference result dict must contain all documented keys."""
    result = mamdani_inference(error=-5, delta_error=-1, humidity=60)
    required_keys = [
        "temperature_error", "delta_error", "humidity_modifier",
        "membership_values", "activated_rules", "all_rules",
        "aggregated_output", "raw_cooling_power",
        "cooling_power", "cooling_level", "explanation",
    ]
    for key in required_keys:
        assert key in result, f"Missing key '{key}' in inference result"

    assert "x" in result["aggregated_output"] and "y" in result["aggregated_output"]
    assert 0 <= result["cooling_power"] <= 100
    assert result["cooling_level"] in {"Very Low", "Low", "Medium", "High", "Very High"}
