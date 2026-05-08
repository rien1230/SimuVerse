"""FastAPI entry point for the SimuVerse backend."""

import warnings
import os
warnings.filterwarnings("ignore", category=UserWarning)
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

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

configure_logging()

_req_logger = logging.getLogger("simuverse.requests")

app = FastAPI(title="SimuVerse", version="0.3.0")

@app.middleware("http")
async def _log_requests(request, call_next):
    t0 = time.perf_counter()
    response = await call_next(request)
    ms = (time.perf_counter() - t0) * 1000
    _req_logger.info("%s %s → %d (%.0fms)", request.method, request.url.path, response.status_code, ms)
    return response

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

app.include_router(run_router,          prefix="/api", tags=["simulation"])
app.include_router(history_router,      prefix="/api", tags=["run history"])
app.include_router(intervention_router, prefix="/api", tags=["interventions"])
app.include_router(simulation_router,   prefix="/api", tags=["simulation"])
app.include_router(experiment_router,   prefix="/api", tags=["experiments"])


@app.get("/api/health")
def health():
    return {"status": "ok", "version": app.version}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8007)
