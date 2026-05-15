import asyncio
import logging

from fastapi import FastAPI, HTTPException

app = FastAPI()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@app.get("/hello")
async def hello():
    logger.info("hello endpoint called")
    return {"message": "hello"}


@app.get("/error")
async def error():
    raise HTTPException(status_code=500, detail="intentional error")


@app.get("/slow")
async def slow(ms: int = 1000):
    logger.info(f"injecting delay of {ms} ms")
    await asyncio.sleep(ms / 1000)
    return {"slept_ms": ms}
