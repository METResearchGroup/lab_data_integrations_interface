from fastapi import FastAPI

from backend.routes.posts import router as posts_router

app = FastAPI()


@app.get("/health")
def health():
    """Health check endpoint. Returns 200 when the service is up."""
    return {"status": "ok"}


app.include_router(posts_router, tags=["posts"])
