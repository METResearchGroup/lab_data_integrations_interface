import asyncio
import logging

from fastapi import FastAPI, HTTPException
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

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

@app.get("/fanout")
async def fanout(branches: int = 5):
    with tracer.start_as_current_span("fanout_parent"):
        await asyncio.gather(*[child_op(i) for i in range(branches)])
    return {"message": f"fanned {branches} branches"}

    
async def child_op(index: int):
    with tracer.start_as_current_span(f"child_op_{index}"):
        await asyncio.sleep(0.1)
    
