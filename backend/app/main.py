import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError
from starlette.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import engine
from app.services.storage import init_storage
from app.routes import auth, candidates, admin, pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("benchos")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    logger.info("AspireOs API starting up...")
    # Initialize S3 storage bucket
    await init_storage()
    yield
    await engine.dispose()
    logger.info("AspireOs API shut down")


app = FastAPI(title="AspireOs API", version="1.0.0", lifespan=lifespan)


@app.exception_handler(OperationalError)
@app.exception_handler(ConnectionError)
async def service_unavailable(request: Request, exc: Exception):
    logger.exception("Service connection failed for %s", request.url.path)
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "A required service is unavailable. Please try again shortly."},
    )


# Global exception handler — never leak stack traces
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled error: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal error occurred. Please try again."},
    )


# CORS
settings = get_settings()
origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
if "http://localhost:3000" not in origins:
    origins.append("http://localhost:3000")
if "http://127.0.0.1:3000" not in origins:
    origins.append("http://127.0.0.1:3000")

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health check
@app.get("/api/health")
async def health():
    return {"ok": True}


# Security headers middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    origin = request.headers.get("Origin")
    if request.method not in {"GET", "HEAD", "OPTIONS"} and origin and origin not in origins and origin != settings.FRONTEND_URL.rstrip("/"):
        response = JSONResponse(status_code=403, content={"detail": "Open AspireOs from its configured web address and try again."})
    else:
        response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Cache-Control"] = "no-store"
    return response


# Routers
app.include_router(auth.router)
app.include_router(candidates.router)
app.include_router(admin.router)
app.include_router(pipeline.router)
