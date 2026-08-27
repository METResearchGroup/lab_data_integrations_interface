import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routes.query import router as query_router
from backend.telemetry import force_telemetry_flush, setup_telemetry

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Export what is buffered on shutdown, so a redeploy still reports."""

    yield
    force_telemetry_flush()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    """Health check endpoint. Returns 200 when the service is up."""
    logger.debug("health check called")
    return {"status": "ok"}


app.include_router(query_router)


setup_telemetry(app)
