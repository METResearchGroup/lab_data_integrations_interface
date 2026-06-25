import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routes.posts import router as posts_router

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    """Health check endpoint. Returns 200 when the service is up."""
    return {"status": "ok"}


app.include_router(posts_router, tags=["posts"])
