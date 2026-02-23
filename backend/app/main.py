# Main FastAPI app setup for SimuVerse
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.run_routes import router as run_router

# Create FastAPI app (ONCE!)
app = FastAPI(title="SimuVerse", version="0.3.0")

# Enable CORS for frontend development - properly indented
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "http://localhost:63342",
        "http://127.0.0.1:63342",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount run management endpoints under /api
app.include_router(run_router, prefix="/api", tags=["runs"])