"""
main.py
=======
FastAPI application — serves the fuzzy-controller REST API and the static
frontend files from a single process (single port, no CORS issues).

Run with:
    uvicorn main:app --reload --host 0.0.0.0 --port 8000

Then open  http://localhost:8000  in a browser.

API Endpoints
-------------
  GET  /health                 health check
  GET  /rules                  full 25-rule base
  GET  /membership-functions   all MF curves for plotting
  POST /predict                single fuzzy inference step
  POST /simulate               100-step thermal simulation
  POST /compare                fuzzy vs threshold side-by-side comparison
"""

import sys
import os
from pathlib import Path

# Ensure the backend directory is on the Python path when running from repo root
sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import Optional

from fuzzy_controller import mamdani_inference
from simulation import run_simulation, run_comparison
from membership_functions import get_mf_curves
from rules import get_rule_matrix_for_display

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Fuzzy Logic Smart Temperature Control System",
    description=(
        "Mamdani Fuzzy Inference Engine for adaptive cooling control. "
        "Built as a FOAI PBL academic project."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class PredictRequest(BaseModel):
    target_temperature: float = Field(24.0, ge=10, le=40, description="Setpoint (°C)")
    current_temperature: float = Field(32.0, ge=0,  le=50, description="Measured room temperature (°C)")
    humidity: float             = Field(60.0, ge=0,  le=100, description="Relative humidity (%)")
    previous_error: float       = Field(0.0,  description="Error from the previous step (for Δe)")


class SimulateRequest(BaseModel):
    target_temperature: float   = Field(24.0, ge=10,  le=40)
    initial_temperature: float  = Field(34.0, ge=0,   le=50)
    humidity: float              = Field(60.0, ge=0,   le=100)
    n_steps: int                 = Field(100,  ge=10,  le=300)
    enable_noise: bool           = Field(False)
    disturbance_at_step: int     = Field(50,   ge=1,   le=299)
    disturbance_magnitude: float = Field(5.0,  ge=0,   le=15)
    controller_type: str         = Field("fuzzy", pattern="^(fuzzy|threshold)$")
    noise_filter: str            = Field("none", pattern="^(none|moving_avg|ema)$")
    filter_window: int           = Field(3,    ge=2,   le=10)
    ema_alpha: float             = Field(0.3,  ge=0.05, le=0.95)


class CompareRequest(BaseModel):
    target_temperature: float   = Field(24.0, ge=10, le=40)
    initial_temperature: float  = Field(34.0, ge=0,  le=50)
    humidity: float              = Field(60.0, ge=0,  le=100)
    n_steps: int                 = Field(100,  ge=10, le=300)
    disturbance_at_step: int     = Field(50,   ge=1,  le=299)
    disturbance_magnitude: float = Field(5.0,  ge=0,  le=15)


# ---------------------------------------------------------------------------
# API Routes — must be declared BEFORE mounting static files
# ---------------------------------------------------------------------------

@app.get("/health", tags=["System"])
def health():
    """Health check — confirms the API is running."""
    return {"status": "ok", "service": "Fuzzy Temperature Controller v1.0"}


@app.get("/rules", tags=["Fuzzy Logic"])
def get_rules():
    """Return the complete 25-rule Mamdani rule base."""
    return get_rule_matrix_for_display()


@app.get("/membership-functions", tags=["Fuzzy Logic"])
def get_membership_functions():
    """Return all MF parameters and curve data (x, y arrays) for plotting."""
    return get_mf_curves()


@app.post("/predict", tags=["Fuzzy Logic"])
def predict(req: PredictRequest):
    """
    Run a single Mamdani fuzzy inference step.

    Returns the complete reasoning chain:
      fuzzification → rule evaluation → aggregation → defuzzification → output
    """
    try:
        error       = req.target_temperature - req.current_temperature
        delta_error = error - req.previous_error
        result      = mamdani_inference(error, delta_error, req.humidity)
        result["inputs"] = {
            "target_temperature":  req.target_temperature,
            "current_temperature": req.current_temperature,
            "humidity":            req.humidity,
            "previous_error":      req.previous_error,
        }
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/simulate", tags=["Simulation"])
def simulate(req: SimulateRequest):
    """
    Run a multi-step thermal simulation with the chosen controller.

    Returns one record per time step with temperature, cooling power,
    error, and disturbance information.
    """
    try:
        records = run_simulation(
            target_temperature    = req.target_temperature,
            initial_temperature   = req.initial_temperature,
            humidity              = req.humidity,
            n_steps               = req.n_steps,
            enable_noise          = req.enable_noise,
            disturbance_at_step   = req.disturbance_at_step,
            disturbance_magnitude = req.disturbance_magnitude,
            controller_type       = req.controller_type,
            noise_filter          = req.noise_filter,
            filter_window         = req.filter_window,
            ema_alpha             = req.ema_alpha,
        )
        return {
            "controller_type":     req.controller_type,
            "n_steps":             req.n_steps,
            "target_temperature":  req.target_temperature,
            "initial_temperature": req.initial_temperature,
            "disturbance_at_step": req.disturbance_at_step,
            "records":             records,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/compare", tags=["Simulation"])
def compare(req: CompareRequest):
    """
    Run fuzzy and threshold controllers under identical conditions and
    return step records + performance metrics for both.
    """
    try:
        return run_comparison(
            target_temperature    = req.target_temperature,
            initial_temperature   = req.initial_temperature,
            humidity              = req.humidity,
            n_steps               = req.n_steps,
            disturbance_at_step   = req.disturbance_at_step,
            disturbance_magnitude = req.disturbance_magnitude,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Serve the frontend — MUST be mounted AFTER all API routes
# ---------------------------------------------------------------------------

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

if FRONTEND_DIR.exists():
    app.mount(
        "/",
        StaticFiles(directory=str(FRONTEND_DIR), html=True),
        name="static",
    )
else:
    @app.get("/", tags=["System"])
    def root():
        return {
            "message": "Frontend not found. Place index.html in the frontend/ directory.",
            "api_docs": "/docs",
        }
