"""
fuzzy_controller.py
===================
Full transparent Mamdani Fuzzy Inference Engine.

Pipeline
--------
  Crisp Inputs
    → [1] Fuzzification       — map e, Δe → linguistic membership degrees
    → [2] Rule Evaluation     — AND = min(μ_e, μ_Δe) for each of 25 rules
    → [3] Implication         — clip output MF at firing strength (min method)
    → [4] Aggregation         — pointwise max of all clipped output MFs
    → [5] Defuzzification     — centroid / CoG on discrete universe [0, 100]
    → [6] Humidity Modifier   — scale raw output by fuzzy-weighted factor
                                Low=0.85 · Medium=1.00 · High=1.15
    → Crisp Cooling Power %

Every intermediate result is returned so the frontend can display the
complete reasoning chain (viva mode).
"""

import numpy as np

from membership_functions import (
    fuzzify_error,
    fuzzify_delta_error,
    fuzzify_humidity,
    cooling_mf_vector,
    compute_humidity_modifier,
    COOLING_UNIVERSE,
)
from rules import (
    ERROR_LABELS,
    DELTA_ERROR_LABELS,
    RULE_MATRIX,
)


# ---------------------------------------------------------------------------
# Linguistic label lookup for cooling output
# ---------------------------------------------------------------------------

def _cooling_level_label(power: float) -> str:
    """Map a crisp cooling percentage to a descriptive linguistic label."""
    if power < 20:
        return "Very Low"
    if power < 40:
        return "Low"
    if power < 60:
        return "Medium"
    if power < 80:
        return "High"
    return "Very High"


# ---------------------------------------------------------------------------
# Natural-language explanation generator
# ---------------------------------------------------------------------------

def _generate_explanation(
    e: float,
    de: float,
    mu_e: dict,
    mu_de: dict,
    mu_h: dict,
    activated: list,
    raw: float,
    final: float,
    level: str,
    modifier: float,
) -> str:
    """Build a clear, student-readable explanation of the FLC decision."""

    dominant_e  = max(mu_e,  key=mu_e.get)
    dominant_de = max(mu_de, key=mu_de.get)
    dominant_h  = max(mu_h,  key=mu_h.get)

    # --- error description ---
    if e < -8:
        e_desc = "significantly above the target (hot room)"
    elif e < -3:
        e_desc = "moderately above the target"
    elif -3 <= e <= 3:
        e_desc = "near the target"
    elif e < 8:
        e_desc = "moderately below the target (cool room)"
    else:
        e_desc = "well below the target (very cool room)"

    # --- rate of change description ---
    if de < -1.5:
        de_desc = "worsening rapidly — room temperature is rising fast"
    elif de < -0.3:
        de_desc = "worsening slowly — room is warming up"
    elif -0.3 <= de <= 0.3:
        de_desc = "stable — rate of change is near zero"
    elif de < 1.5:
        de_desc = "improving slowly — room is cooling down"
    else:
        de_desc = "improving rapidly — room temperature is dropping fast"

    lines = [
        f"━━ STEP 1 · FUZZIFICATION ━━",
        f"The temperature error e = {e:+.2f}°C.",
        f"The room is currently {e_desc}.",
        f"Dominant error category: '{dominant_e}' (μ = {mu_e[dominant_e]:.3f}).",
        f"",
        f"The rate of change of error Δe = {de:+.2f}°C/step.",
        f"This is {de_desc}.",
        f"Dominant Δe category: '{dominant_de}' (μ = {mu_de[dominant_de]:.3f}).",
        f"",
        f"━━ STEP 2 · RULE EVALUATION (AND = min) ━━",
        f"{len(activated)} rule(s) fired with non-zero strength.",
    ]

    if activated:
        top = max(activated, key=lambda r: r["strength"])
        lines.append(
            f"Strongest rule: IF e={top['e_label']} AND Δe={top['de_label']} "
            f"→ Cooling={top['consequent']} (strength = {top['strength']:.3f})."
        )

    lines += [
        f"",
        f"━━ STEP 3–4 · IMPLICATION & AGGREGATION ━━",
        f"Each output MF is clipped at its rule's firing strength (min implication).",
        f"All clipped MFs are combined pointwise using maximum (max aggregation).",
        f"",
        f"━━ STEP 5 · CENTROID DEFUZZIFICATION ━━",
        f"u* = Σ(u · μ_agg(u)) / Σ(μ_agg(u))  over u ∈ [0, 100]",
        f"Raw defuzzified cooling power = {raw:.2f}%.",
        f"",
        f"━━ STEP 6 · HUMIDITY MODIFIER ━━",
        f"Humidity category: '{dominant_h}' → modifier = {modifier:.3f}",
        f"  Low = 0.85 · Medium = 1.00 · High = 1.15  (fuzzy-weighted average)",
        f"Final cooling power = {raw:.2f}% × {modifier:.3f} = {final:.2f}% → {level}.",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main inference function
# ---------------------------------------------------------------------------

def mamdani_inference(
    error: float,
    delta_error: float,
    humidity: float,
) -> dict:
    """
    Run the complete Mamdani fuzzy inference pipeline.

    Parameters
    ----------
    error       : temperature error  e = T_target - T_current  (°C)
    delta_error : rate of change of error  Δe = e(t) - e(t-1)  (°C/step)
    humidity    : relative humidity  (%)

    Returns
    -------
    dict with every intermediate value of the inference pipeline.
    """

    # ------------------------------------------------------------------
    # 1. Fuzzification  (clamp inputs to their universe bounds first)
    #    Standard FLC practice: values beyond the universe are treated as
    #    the extreme linguistic category rather than producing zero output.
    # ------------------------------------------------------------------
    error       = float(np.clip(error,       -15.0, 15.0))
    delta_error = float(np.clip(delta_error,  -5.0,  5.0))
    humidity    = float(np.clip(humidity,      0.0, 100.0))

    mu_e  = fuzzify_error(error)
    mu_de = fuzzify_delta_error(delta_error)
    mu_h  = fuzzify_humidity(humidity)

    # ------------------------------------------------------------------
    # 2. Rule evaluation  (AND = min)
    # ------------------------------------------------------------------
    activated_rules: list[dict] = []
    rule_id = 1

    for i, e_lbl in enumerate(ERROR_LABELS):
        for j, de_lbl in enumerate(DELTA_ERROR_LABELS):
            output_lbl = RULE_MATRIX[i][j]
            strength   = min(mu_e[e_lbl], mu_de[de_lbl])

            rule_entry = {
                "rule_id":    rule_id,
                "e_label":    e_lbl,
                "de_label":   de_lbl,
                "antecedent": f"e={e_lbl}, Δe={de_lbl}",
                "consequent": output_lbl,
                "strength":   round(float(strength), 4),
                "active":     strength > 0.0,
            }
            activated_rules.append(rule_entry)
            rule_id += 1

    # Rules that actually fire
    fired = [r for r in activated_rules if r["active"]]

    # ------------------------------------------------------------------
    # 3. Implication (min) + 4. Aggregation (max)
    # ------------------------------------------------------------------
    u = COOLING_UNIVERSE                            # shape: (N,)
    aggregated = np.zeros(len(u), dtype=float)

    for rule in fired:
        output_mf = cooling_mf_vector(u, rule["consequent"])   # shape: (N,)
        clipped   = np.minimum(rule["strength"], output_mf)    # min implication
        aggregated = np.maximum(aggregated, clipped)           # max aggregation

    # ------------------------------------------------------------------
    # 5. Centroid defuzzification
    # ------------------------------------------------------------------
    denom = float(np.sum(aggregated))
    if denom < 1e-9:
        raw_cooling = 0.0
    else:
        raw_cooling = float(np.sum(u * aggregated) / denom)

    # ------------------------------------------------------------------
    # 6. Humidity modifier
    #    Low = 0.85  ·  Medium = 1.00  ·  High = 1.15
    # ------------------------------------------------------------------
    modifier      = compute_humidity_modifier(mu_h)
    cooling_power = float(np.clip(raw_cooling * modifier, 0.0, 100.0))
    cooling_level = _cooling_level_label(cooling_power)

    # ------------------------------------------------------------------
    # Natural-language explanation
    # ------------------------------------------------------------------
    explanation = _generate_explanation(
        e=error, de=delta_error,
        mu_e=mu_e, mu_de=mu_de, mu_h=mu_h,
        activated=fired,
        raw=raw_cooling,
        final=cooling_power,
        level=cooling_level,
        modifier=modifier,
    )

    return {
        "temperature_error":  round(error,        4),
        "delta_error":        round(delta_error,  4),
        "humidity_modifier":  round(modifier,     4),
        "membership_values": {
            "error":       {k: round(v, 4) for k, v in mu_e.items()},
            "delta_error": {k: round(v, 4) for k, v in mu_de.items()},
            "humidity":    {k: round(v, 4) for k, v in mu_h.items()},
        },
        "all_rules":      activated_rules,
        "activated_rules": [
            {k: v for k, v in r.items() if k != "active"}
            for r in fired
        ],
        "aggregated_output": {
            "x": [round(float(v), 2) for v in u],
            "y": [round(float(v), 4) for v in aggregated],
        },
        "raw_cooling_power":  round(raw_cooling,    2),
        "cooling_power":      round(cooling_power,  2),
        "cooling_level":      cooling_level,
        "explanation":        explanation,
    }
