from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from app.core.logging_config import configure_logging
from app.api.routes.runs import router as run_router
from app.api.routes.run_history_routes import router as history_router
from app.api.routes.interventions import router as intervention_router
from app.api.routes.experiments import router as experiment_router
from app.api.routes.simulation import router as simulation_router

configure_logging()

app = FastAPI(title="SimuVerse", version="0.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(run_router,          prefix="/api", tags=["simulation"])
app.include_router(history_router,      prefix="/api", tags=["run history"])
app.include_router(intervention_router, prefix="/api", tags=["interventions"])
app.include_router(experiment_router,   prefix="/api", tags=["experiments"])
app.include_router(simulation_router,   prefix="/api", tags=["simulation"])


@app.get("/api/health")
def health():
    return {"status": "ok", "version": app.version}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
