"""FastAPI entry point for the SimuVerse backend.

Backend entry point and API wiring.

Quick map:
- main.py                     -> app startup + middleware + router registration
- api/routes/runs.py         -> live run creation, stepping, status, WebSocket
- api/routes/interventions.py -> user interventions during a live run
- api/routes/simulation.py    -> one-shot helper endpoints
- api/routes/experiments.py   -> batch experiment endpoints
- services/run_manager.py     -> lifecycle of a single run
- services/run_registry.py    -> registry for all active runs
- sim/model.py                -> core simulation state machine
"""

import warnings
import os

# Silence noisy warnings from HuggingFace/tokenizers before any imports trigger them
warnings.filterwarnings("ignore", category=UserWarning)
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")  # avoids fork-safety warnings in workers

import time
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from app.core.logging_config import configure_logging
from app.api.routes.runs import router as run_router
from app.api.routes.run_history_routes import history_router
from app.api.routes.interventions import router as intervention_router
from app.api.routes.simulation import router as simulation_router
from app.api.routes.experiments import router as experiment_router

# Set up logging before anything else so early startup messages are captured
configure_logging()

# Dedicated logger for HTTP request timing — keeps it separate from sim output
_req_logger = logging.getLogger("simuverse.requests")


app = FastAPI(title="SimuVerse", version="0.3.0")


@app.middleware("http")
async def _log_requests(request, call_next):
    """Log every incoming request with its method, path, status code, and duration.

    perf_counter gives sub-millisecond precision, which is handy for spotting
    slow simulation steps in the request log.
    """
    t0 = time.perf_counter()
    response = await call_next(request)
    ms = (time.perf_counter() - t0) * 1000  # convert seconds → milliseconds
    _req_logger.info("%s %s → %d (%.0fms)", request.method, request.url.path, response.status_code, ms)
    return response


# ── Frontend access policy ────────────────────────────────────────────────
# Allow requests from all the local dev servers we might be running the frontend on.
# "null" covers file:// origins in some browsers when opening HTML directly.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5001", "http://127.0.0.1:5001",
        "http://localhost:5002", "http://127.0.0.1:5002",  # preview static server
        "http://localhost:3000", "http://127.0.0.1:3000",
        "http://localhost:63342", "http://127.0.0.1:63342",  # JetBrains IDE server
        "null",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API route registration ────────────────────────────────────────────────
# Register all route groups under the /api prefix so the app is split by feature
# instead of growing into one giant routes file.
app.include_router(run_router,          prefix="/api", tags=["simulation"])
app.include_router(history_router,      prefix="/api", tags=["run history"])
app.include_router(intervention_router, prefix="/api", tags=["interventions"])
app.include_router(simulation_router,   prefix="/api", tags=["simulation"])
app.include_router(experiment_router,   prefix="/api", tags=["experiments"])


@app.get("/api/health")
def health():
    """Simple health-check endpoint so load balancers and tests can confirm the server is up."""
    return {"status": "ok", "version": app.version}


if __name__ == "__main__":
    # Only used when running directly with `python main.py` during local dev
    uvicorn.run(app, host="127.0.0.1", port=8007)
