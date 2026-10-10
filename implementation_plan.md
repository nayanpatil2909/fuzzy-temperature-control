# Fuzzy Logic-Based Smart Temperature Control System
## Implementation Plan

### Problem Summary

Build a complete, educational, interactive web application demonstrating Mamdani Fuzzy Logic for adaptive temperature control. The fuzzy pipeline — Fuzzification → Rule Evaluation → Inference → Aggregation → Centroid Defuzzification → Output — must be fully visible, explainable, and academically sound.

---

## Architecture Decision

### Chosen Stack

| Layer | Technology | Reason |
|---|---|---|
| Backend (AI Engine) | Python + FastAPI | Clean REST API, easy local dev, Python ecosystem for fuzzy logic |
| Fuzzy Engine | NumPy (custom) + scikit-fuzzy reference | Custom implementation keeps pipeline transparent for viva; scikit-fuzzy used for validation |
| Frontend | Single-file HTML + Vanilla CSS + JavaScript | Zero build step, runs in browser, easy to present |
| Charts | Chart.js (CDN) | Lightweight, interactive, no install needed |
| Gauge | Custom SVG/Canvas in JS | Full control over visual appearance |

> **No React, no TypeScript, no bundler.** This is an academic project — simplicity of runtime is a feature.

### Why Python backend instead of pure JS?
The fuzzy math (membership functions, rule aggregation, centroid defuzzification on a discrete universe) is cleaner to implement, test, and explain in Python with NumPy. The frontend consumes the API and focuses on visualization and UX.

---

## Fuzzy Controller Design

### Architecture Choice: **Option A (selected)**

- **Primary inputs**: Temperature Error `e = T_target − T_current` and Rate of Change of Error `Δe = e(t) − e(t−1)`
- **Secondary input**: Humidity (used as a modifier/gain on the output)
- **Why Option A?** Produces a 5×5 = 25-rule base that is academically classic (PID-like fuzzy controller), easier to reason about during viva, and aligns with Mamdani control literature.

### Sign Convention (Critical)

```
e = T_target − T_current

e < 0  →  room is HOTTER than target  →  need MORE cooling
e > 0  →  room is COOLER than target  →  need LESS cooling
e ≈ 0  →  room is AT target          →  maintain cooling
```

The rules are written so that **Negative Big error → Very High cooling**. This is physically correct and must be clearly documented.

---

## Membership Functions

### Input 1: Temperature Error `e` — Universe: [−15, +15] °C

| Label | Type | Parameters |
|---|---|---|
| NB (Negative Big) | Trapezoid | [−15, −15, −8, −4] |
| NS (Negative Small) | Triangle | [−8, −4, 0] |
| ZE (Zero) | Triangle | [−3, 0, +3] |
| PS (Positive Small) | Triangle | [0, +4, +8] |
| PB (Positive Big) | Trapezoid | [+4, +8, +15, +15] |

### Input 2: Rate of Change of Error `Δe` — Universe: [−5, +5] °C/step

| Label | Type | Parameters |
|---|---|---|
| NB | Trapezoid | [−5, −5, −3, −1] |
| NS | Triangle | [−3, −1, 0] |
| ZE | Triangle | [−1, 0, +1] |
| PS | Triangle | [0, +1, +3] |
| PB | Trapezoid | [+1, +3, +5, +5] |

### Input 3: Humidity — Universe: [0, 100] %

| Label | Type | Parameters |
|---|---|---|
| Low | Trapezoid | [0, 0, 30, 50] |
| Medium | Triangle | [30, 50, 70] |
| High | Trapezoid | [60, 80, 100, 100] |

### Output: Cooling Power — Universe: [0, 100] %

| Label | Type | Parameters |
|---|---|---|
| VL (Very Low) | Trapezoid | [0, 0, 10, 25] |
| L (Low) | Triangle | [10, 25, 40] |
| M (Medium) | Triangle | [30, 50, 70] |
| H (High) | Triangle | [60, 75, 90] |
| VH (Very High) | Trapezoid | [75, 90, 100, 100] |

---

## Rule Base (25 Core Rules)

Error rows (e): NB, NS, ZE, PS, PB  
Rate-of-change columns (Δe): NB, NS, ZE, PS, PB

```
        Δe→  NB    NS    ZE    PS    PB
e↓
NB           VH    VH    VH    H     H
NS           VH    H     H     M     L
ZE           H     M     M     L     VL
PS           M     L     L     VL    VL
PB           L     VL    VL    VL    VL
```

**Humidity modifier**: The raw crisp output is scaled by a humidity factor:
- Low humidity → factor 0.85 (less cooling needed)
- Medium humidity → factor 1.00 (no change)
- High humidity → factor 1.15 (more cooling needed), capped at 100%

This keeps the 25-rule base clean while still incorporating humidity meaningfully.

---

## Mamdani Inference Pipeline

```
1. FUZZIFICATION
   - Compute μ_NB(e), μ_NS(e), μ_ZE(e), μ_PS(e), μ_PB(e)
   - Compute μ_NB(Δe), μ_NS(Δe), ..., μ_PB(Δe)

2. RULE EVALUATION (AND = minimum)
   - For each of 25 rules: firing_strength = min(μ_row(e), μ_col(Δe))

3. IMPLICATION (min)
   - Clip each output MF at firing_strength

4. AGGREGATION (max)
   - Take pointwise maximum of all clipped output MFs

5. DEFUZZIFICATION (Centroid)
   - u* = Σ(u · μ_agg(u)) / Σ(μ_agg(u))  over discrete universe [0,100]

6. HUMIDITY SCALING
   - Apply humidity modifier to u*
```

---

## Simulation Model

```
T(t+1) = T(t) + α·(T_ambient − T(t)) − β·cooling_power + noise + disturbance(t)
```

Where:
- `α = 0.02` — thermal drift toward ambient (simplified heat gain)
- `β = 0.08` — cooling effectiveness per unit power
- `noise` — optional Gaussian noise σ=0.1
- `disturbance(t)` — step disturbance at t=50s: +5°C simulated heat load

Clearly labeled as a **simplified first-order thermal model**, not a real HVAC model.

---

## Project Structure

```
fuzzy-temperature-control/
│
├── backend/
│   ├── main.py                  # FastAPI app, routes
│   ├── fuzzy_controller.py      # Core Mamdani FLC (transparent pipeline)
│   ├── membership_functions.py  # All MF definitions + evaluation
│   ├── rules.py                 # Rule base + rule matrix
│   ├── simulation.py            # Time-step simulation engine
│   └── requirements.txt
│
├── frontend/
│   ├── index.html               # Full dashboard (single page)
│   ├── style.css                # Modern dark theme dashboard CSS
│   └── script.js                # API calls, charts, interactivity
│
├── tests/
│   └── test_fuzzy.py            # 8+ test cases
│
└── README.md
```

---

## API Endpoints

### `POST /predict`
Runs one fuzzy inference step.

**Input:**
```json
{
  "target_temperature": 24.0,
  "current_temperature": 31.0,
  "humidity": 70.0,
  "previous_error": -6.0
}
```

**Output:**
```json
{
  "temperature_error": -7.0,
  "rate_of_error": -1.0,
  "humidity_modifier": 1.05,
  "membership_values": {
    "error": {"NB": 0.75, "NS": 0.25, "ZE": 0.0, "PS": 0.0, "PB": 0.0},
    "delta_error": {"NB": 0.0, "NS": 0.5, "ZE": 0.5, "PS": 0.0, "PB": 0.0},
    "humidity": {"Low": 0.0, "Medium": 0.0, "High": 1.0}
  },
  "activated_rules": [
    {"rule_id": 1, "antecedent": "e=NB, Δe=NS", "consequent": "VH", "strength": 0.25},
    {"rule_id": 2, "antecedent": "e=NB, Δe=ZE", "strength": 0.25, "consequent": "VH"}
  ],
  "raw_cooling_power": 82.3,
  "cooling_power": 86.4,
  "cooling_level": "Very High",
  "explanation": "...",
  "aggregated_output_curve": {"x": [...], "y": [...]}
}
```

### `POST /simulate`
Runs 100-step simulation.

**Input:**
```json
{
  "target_temperature": 24.0,
  "initial_temperature": 34.0,
  "humidity": 65.0,
  "enable_noise": false,
  "disturbance_at_step": 50,
  "disturbance_magnitude": 5.0,
  "controller_type": "fuzzy"
}
```

**Output:** Array of time steps with temperature, cooling power, disturbance flag.

### `GET /membership-functions`
Returns all MF parameters for display in the UI.

### `GET /rules`
Returns the full rule base.

### `GET /health`
Health check.

---

## UI Sections

1. **Header** — Title, subtitle, system status badge
2. **Control Panel** — Target temp, current temp, humidity sliders + Predict button
3. **Fuzzy Analysis Panel** — Error, Δe, membership values, activated rules table
4. **Output Panel** — Cooling % gauge, linguistic label, AI explanation
5. **Aggregated Output Curve** — Chart showing the aggregated MF and centroid point
6. **Simulation Panel** — Run button, speed, disturbance toggle; live charts
7. **Comparison Panel** — Fuzzy vs. Threshold side-by-side simulation + metrics table
8. **Educational Panel** — Concept glossary, MF visualization charts, rule matrix grid

---

## Verification Plan

### Automated Tests (`tests/test_fuzzy.py`)
```
pytest tests/test_fuzzy.py -v
```
8 test cases:
1. Temperature well below target → Very Low cooling
2. Temperature at target, no change → Low/Medium cooling
3. Temperature slightly above target → Medium cooling
4. Temperature significantly above target → Very High cooling
5. High humidity boost → cooling ≥ dry case
6. Low humidity reduction → cooling ≤ baseline
7. Rapid temperature increase (large Δe) → cooling higher than steady-state
8. Disturbance rejection → controller increases cooling after disturbance

### Manual Verification
- Open `http://localhost:8000` after starting backend
- Serve `frontend/index.html` via Live Server or `python -m http.server 3000`
- Test slider interactions, simulation playback, and Viva Mode explanations

---

## Open Questions

> [!IMPORTANT]
> **Q1: Should the UI be served by FastAPI (single port)?**
> I will configure FastAPI to also serve the static frontend files at `/` so the user only needs to run one command: `uvicorn backend.main:app`. This avoids CORS issues and simplifies deployment.

> [!NOTE]
> **Q2: Humidity architecture confirmed as Option A** (modifier, not primary input). This gives the cleanest 25-rule base and the most interpretable academic presentation.

> [!NOTE]
> **Q3: Comparison controller** will be a simple hysteresis/threshold bang-bang controller (ON/OFF with 2°C band). This is deliberately simple to contrast with fuzzy smoothness, not a PID.
