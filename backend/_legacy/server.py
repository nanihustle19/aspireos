import asyncio
import logging
import os

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from core import client, logger
import auth_routes
import candidates
import admin_routes
import pipeline
from seed import seed
from storage import init_storage
from worker import worker_loop

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

app = FastAPI(title="BenchOS API")


@app.get("/api/health")
async def health():
    return {"ok": True}


app.include_router(auth_routes.router)
app.include_router(candidates.router)
app.include_router(admin_routes.router)
app.include_router(pipeline.router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ["CORS_ORIGINS"].split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    await seed()
    try:
        init_storage()
        logger.info("Storage initialized")
    except Exception as e:
        logger.error(f"Storage init failed: {e}")
    app.state.workers = [asyncio.create_task(worker_loop(["SCAN"])),
                         asyncio.create_task(worker_loop(["EXPORT_CANDIDATES", "IMPORT_CANDIDATES"], outbox=True))]


@app.on_event("shutdown")
async def shutdown():
    client.close()
