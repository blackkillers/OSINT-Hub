"""
OSINT-Hub FastAPI Main Gateway Application
==========================================
Zero Trust API Gateway, WebSockets broker integration, and CORS setup.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog

from app.api.scans import router as scans_router

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    logger.info("Initializing OSINT-Hub API Gateway")
    yield
    logger.info("Shutting down OSINT-Hub API Gateway")


app = FastAPI(
    title="OSINT-Hub API Gateway",
    description="Sovereign Zero-Trust OSINT Investigation Platform",
    version="1.0.0",
    lifespan=lifespan,
)

# Configure CORS - Restrict strictly for Zero Trust environments
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API Routers
app.include_router(scans_router, prefix="/api/v1", tags=["Scans & Investigations"])


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint for Docker & reverse proxy monitoring."""
    return {"status": "healthy", "service": "osint-hub-backend"}
