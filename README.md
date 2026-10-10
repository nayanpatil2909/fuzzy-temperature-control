# Fuzzy Logic-Based Smart Temperature Control System
### Foundations of Artificial Intelligence — PBL Project

---

## 1 · Project Overview

This project implements a **Mamdani Fuzzy Logic Controller (FLC)** for adaptive room temperature control. Given the current temperature, a target setpoint, and humidity, the controller computes the appropriate cooling/fan power percentage (0–100 %) through a fully transparent fuzzy inference pipeline.

The application is a complete, interactive web dashboard built to:
- Demonstrate every step of the Mamdani inference process
- Run a simplified thermal simulation with disturbance rejection
- Compare fuzzy control against a simple bang-bang threshold controller
- Serve as a viva-ready educational reference

**IMPORTANT**: This is a software simulation project, not a real HVAC system.

---

## 2 · Problem Statement

A room's temperature must be controlled to a user-defined setpoint despite varying heat loads and humidity. A fixed threshold controller is too crude — it switches cooling fully ON or OFF, causing oscillation and discomfort. This project demonstrates how Fuzzy Logic can provide smooth, intelligent, and interpretable control.

---

## 3 · Proposed Methodology

### Architecture Choice: **Option A — Error + Rate-of-Error (PID-style FLC)**

| Input | Symbol | Range |
|---|---|---|
| Temperature Error | `e = T_target − T_current` | [−15, +15] °C |
| Rate of Change of Error | `Δe = e(t) − e(t−1)` | [−5, +5] °C/step |
| Humidity (modifier) | `H` | [0, 100] % |

| Output | Symbol | Range |
|---|---|---|
| Cooling/Fan Power | `u` | [0, 100] % |

**Why Option A?**  
The error × rate-of-error structure is the classic Mamdani FLC architecture. It produces an interpretable 5×5 = 25-rule base, mirrors PID-controller logic, and is well-documented in control-systems literature — making it ideal for academic explanation.

---

## 4 · Sign Convention

```
e = T_target − T_current

e < 0  →  room HOTTER than target  →  Negative error  →  MORE cooling
e > 0  →  room COOLER than target  →  Positive error  →  LESS cooling
e = 0  →  AT setpoint              →  maintain current cooling

Δe < 0  →  error becoming more negative  →  room heating up  →  boost cooling
Δe > 0  →  error improving               →  room cooling down →  ease off
```

This convention ensures that the rule "IF e = NB AND Δe = NB THEN Cooling = VH" means **very high cooling when the room is very hot and getting hotter**, which is physically correct.

---

## 5 · Membership Functions

All MFs use triangular (`trimf`) or trapezoidal (`trapmf`) shapes.

### Temperature Error  e ∈ [−15, +15] °C

| Label | Type | Parameters (a, b, c, d) |
|---|---|---|
| NB (Negative Big) | Trapezoid | −15, −15, −8, −4 |
| NS (Negative Small) | Triangle | −8, −4, 0 |
| ZE (Zero) | Triangle | −3, 0, +3 |
| PS (Positive Small) | Triangle | 0, +4, +8 |
| PB (Positive Big) | Trapezoid | +4, +8, +15, +15 |

### Rate of Change of Error  Δe ∈ [−5, +5] °C/step

| Label | Type | Parameters |
|---|---|---|
| NB | Trapezoid | −5, −5, −3, −1 |
| NS | Triangle | −3, −1, 0 |
| ZE | Triangle | −1, 0, +1 |
| PS | Triangle | 0, +1, +3 |
| PB | Trapezoid | +1, +3, +5, +5 |

### Humidity  H ∈ [0, 100] %

| Label | Type | Parameters |
|---|---|---|
| Low | Trapezoid | 0, 0, 30, 50 |
| Medium | Triangle | 30, 50, 70 |
| High | Trapezoid | 60, 80, 100, 100 |

### Cooling Output  u ∈ [0, 100] %

| Label | Type | Parameters |
|---|---|---|
| VL (Very Low) | Trapezoid | 0, 0, 10, 25 |
| L (Low) | Triangle | 10, 25, 40 |
| M (Medium) | Triangle | 30, 50, 70 |
| H (High) | Triangle | 60, 75, 90 |
| VH (Very High) | Trapezoid | 75, 90, 100, 100 |

---

## 6 · Rule Base (25 Rules)

```
         Δe →    NB    NS    ZE    PS    PB
   e ↓
   NB           VH    VH    VH    H     H
   NS           VH    H     H     M     L
   ZE           H     M     M     L     VL
   PS           M     L     L     VL    VL
   PB           L     VL    VL    VL    VL
```

**Reading the matrix**: Row = Temperature Error label, Column = Rate-of-Error label.  
Example: `e = NB, Δe = ZE → Cooling = VH`  
*(Room is very hot and error is stable — apply maximum cooling)*

---

## 7 · Mamdani Inference Pipeline

```
Step 1 — Fuzzification
  μ_NB(e), μ_NS(e), μ_ZE(e), μ_PS(e), μ_PB(e) from Error MFs
  μ_NB(Δe), …, μ_PB(Δe) from Delta-Error MFs

Step 2 — Rule Evaluation  (AND = min)
  For each rule (i, j):
    α_ij = min( μ_label_e(e), μ_label_de(Δe) )

Step 3 — Implication  (min)
  Clipped output MF:  μ'_ij(u) = min( α_ij, μ_output(u) )

Step 4 — Aggregation  (max)
  μ_agg(u) = max over all (i,j) of μ'_ij(u)

Step 5 — Defuzzification  (Centroid / CoG)
  u* = Σ( uₖ · μ_agg(uₖ) ) / Σ( μ_agg(uₖ) )
  where uₖ ∈ { 0, 0.5, 1.0, …, 100 }  (201 discrete points)

Step 6 — Humidity Modifier
  modifier = Σ( μ_label_H × factor_label ) / Σ( μ_label_H )
    Low = 0.85 · Medium = 1.00 · High = 1.15
  Final cooling = clip( u* × modifier, 0, 100 )
```

---

## 8 · Humidity Modifier (Low=0.85, Medium=1.00, High=1.15)

Humidity is incorporated as a post-inference scaling factor computed by fuzzy-weighted average:

```
modifier = (μ_Low × 0.85 + μ_Medium × 1.00 + μ_High × 1.15)
           ─────────────────────────────────────────────────
                  μ_Low + μ_Medium + μ_High
```

| Pure Humidity | Modifier |
|---|---|
| 0 %   (all Low)    | 0.85 — dry air, less cooling demand |
| 50 %  (all Medium) | 1.00 — neutral |
| 100 % (all High)   | 1.15 — humid air, more cooling demand |
| 65 %  (mixed) | ≈ 1.075 — interpolated smoothly |

---

## 9 · Thermal Simulation Model

```
T(t+1) = T(t)
        + α · (T_ambient − T(t))    ← heat drift toward ambient
        − β · (P(t) / 100)          ← active cooling
        + noise(t)                  ← optional Gaussian noise  N(0, 0.10)
        + disturbance               ← one-shot heat spike at step t_d

Parameters:
  α = 0.025   thermal drift coefficient
  β = 0.80    cooling effectiveness (°C per step at 100% power)
  T_ambient = initial_temperature
```

**Disclaimer**: This is a simplified first-order linear model. It is not a validated HVAC thermal model. It is used exclusively to demonstrate controller behaviour qualitatively.

---

## 10 · Technologies Used

| Component | Technology |
|---|---|
| AI / Fuzzy Engine | Python, NumPy (custom implementation) |
| Backend API | FastAPI, Uvicorn |
| Validation | Pydantic v2 |
| Frontend | HTML5, Vanilla CSS, Vanilla JavaScript |
| Charts | Chart.js 4, chartjs-plugin-annotation |
| Gauge | Custom HTML5 Canvas arc |
| Tests | pytest |

---

## 11 · Project Structure

```
fuzzy-temperature-control/
│
├── backend/
│   ├── main.py                  FastAPI application (API + static serving)
│   ├── fuzzy_controller.py      Mamdani inference engine (full pipeline)
│   ├── membership_functions.py  MF definitions + fuzzification helpers
│   ├── rules.py                 25-rule base + matrix accessor
│   ├── simulation.py            Thermal model + comparison runner
│   └── requirements.txt         Python dependencies
│
├── frontend/
│   ├── index.html               8-panel interactive dashboard
│   ├── style.css                Dark HMI aesthetic CSS
│   └── script.js                Charts, API, gauge, educational panel
│
├── tests/
│   └── test_fuzzy.py            12 physics-consistent unit tests
│
└── README.md                    This document
```

---

## 12 · Installation

### Prerequisites
- Python 3.10 or higher
- pip

### Steps

```bash
# 1. Clone or download the project
cd "fuzzy-temperature-control"

# 2. Create a virtual environment
python -m venv .venv

# 3. Activate it
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# macOS / Linux:
source .venv/bin/activate

# 4. Install dependencies
pip install -r backend/requirements.txt
```

---

## 13 · How to Run

```bash
# From the project root directory, with the venv active:
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

Then open **http://localhost:8000** in your browser.

The FastAPI backend also serves the frontend static files, so **no separate frontend server is needed**.

API documentation is available at **http://localhost:8000/docs** (Swagger UI).

---

## 14 · How to Run Tests

```bash
# From the project root, with the venv active:
pytest tests/test_fuzzy.py -v
```

Expected output:
```
tests/test_fuzzy.py::test_temperature_below_target_gives_low_cooling     PASSED
tests/test_fuzzy.py::test_temperature_at_target_stable_gives_moderate    PASSED
tests/test_fuzzy.py::test_temperature_slightly_above_target_gives_medium PASSED
tests/test_fuzzy.py::test_temperature_significantly_above_target_gives_high PASSED
tests/test_fuzzy.py::test_high_humidity_increases_cooling                PASSED
tests/test_fuzzy.py::test_low_humidity_decreases_cooling                 PASSED
tests/test_fuzzy.py::test_rapid_temperature_rise_increases_cooling       PASSED
tests/test_fuzzy.py::test_rapid_temperature_fall_reduces_cooling         PASSED
tests/test_fuzzy.py::test_extreme_heat_worsening_gives_very_high         PASSED
tests/test_fuzzy.py::test_humidity_modifier_values                       PASSED
tests/test_fuzzy.py::test_error_mf_full_coverage                         PASSED
tests/test_fuzzy.py::test_inference_result_structure                     PASSED
```

---

## 15 · Example Inputs and Outputs

### Example 1 — Hot, Humid Room

| Input | Value |
|---|---|
| Target Temperature | 24.0 °C |
| Current Temperature | 32.0 °C |
| Humidity | 75 % |
| Previous Error | 0.0 |

**Computation**:
```
e  = 24 − 32 = −8.0 °C         → NB (0.67), NS (0.33)
Δe = −8 − 0  = −8.0 °C/step   → clamped to NB (1.0)
Rules fired: NB×NB(0.67)→VH, NS×NB(0.33)→VH
Raw u* (centroid) ≈ 90.2%
Humidity modifier = (0.0×0.85 + 0.5×1.00 + 0.5×1.15)/1.0 ≈ 1.075
Final cooling = clip(90.2 × 1.075, 0, 100) = 100.0% → Very High
```

### Example 2 — At Setpoint, Dry

| Input | Value |
|---|---|
| Target Temperature | 24.0 °C |
| Current Temperature | 24.0 °C |
| Humidity | 10 % |
| Previous Error | 0.0 |

```
e  = 0.0   → ZE (1.0)
Δe = 0.0   → ZE (1.0)
Rule: ZE×ZE → M
Raw u* ≈ 50.0%
Modifier = 0.85 (dry)
Final cooling ≈ 42.5% → Low
```

### Example 3 — Cool Room

```
Target=24°C, Current=18°C, Humidity=50%
e  = +6 → PS (0.5), PB (0.5)
Δe = 0  → ZE (1.0)
Rules: PS×ZE(0.5)→L, PB×ZE(0.5)→VL
Raw u* ≈ 18%
Modifier = 1.00
Final cooling ≈ 18% → Very Low ✓
```

---

## 16 · API Reference

### `POST /predict`
```json
// Request
{
  "target_temperature": 24.0,
  "current_temperature": 31.0,
  "humidity": 70.0,
  "previous_error": -6.0
}

// Response (excerpt)
{
  "temperature_error": -7.0,
  "delta_error": -1.0,
  "humidity_modifier": 1.1,
  "membership_values": { "error": {"NB":0.75,...}, ... },
  "activated_rules": [{"rule_id":1,"strength":0.75,"consequent":"VH"}, ...],
  "raw_cooling_power": 88.3,
  "cooling_power": 97.1,
  "cooling_level": "Very High",
  "explanation": "━━ STEP 1..."
}
```

### `POST /simulate`
Runs a 100-step thermal simulation. Returns time-step records.

### `POST /compare`
Runs both fuzzy and threshold controllers and returns metrics.

### `GET /rules`
Returns the 25-rule matrix and all rules as structured text.

### `GET /membership-functions`
Returns all MF curve data (x, y arrays) for plotting.

---

## 17 · Limitations

1. **Simplified thermal model** — α and β parameters are approximate; real HVAC systems have complex non-linear dynamics.
2. **Fixed humidity** — Humidity is held constant per simulation run. Real environments have time-varying humidity.
3. **No occupancy modelling** — Heat load from people, equipment, and solar gain is not explicitly modelled.
4. **Manual rule base** — The 25 rules were designed by expert reasoning. An ANFIS (Adaptive Neuro-Fuzzy) system could learn these from data.
5. **Discrete defuzzification** — The centroid is approximated numerically on 201 points; a very coarsely discretised universe could introduce small rounding errors (negligible with 201 points).

---

## 18 · Future Scope

### Hardware Integration
- **DHT22 sensor** → measure real temperature and humidity
- **ESP32 microcontroller** → read sensors, send data via MQTT/HTTP to this API
- **PWM fan/HVAC actuator** → receives the cooling % from this controller
- The `/predict` endpoint is already designed to accept sensor readings directly

### Algorithmic Enhancements
- **ANFIS** — learn MF parameters from historical data
- **Multi-zone control** — extend the rule base to handle several rooms
- **Occupancy-aware setpoint scheduling** — detect room presence and adjust target
- **Energy optimisation** — add an energy-cost objective to the defuzzification

---

## 19 · Academic Integrity Statement

All results in this document labelled as "example" or "simulated" are derived from the actual software implementation, not manually fabricated. The thermal simulation is clearly identified as a simplified model. No real-world energy savings or HVAC performance claims are made.

---

*Project by — FOAI PBL Group | Fuzzy Logic-Based Smart Temperature Control System*
