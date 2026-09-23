import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.routers import admin, auth, health, meta, predict

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("neet_predictor")

settings = get_settings()

app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    description=(
        "Backend API for the NEET Rank Predictor. Serves live cutoff-rank "
        "predictions from a centralized Postgres database, and lets admins "
        "add new years/rounds of data without touching the frontend."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors(), "message": "Invalid request payload."},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"message": "Internal server error. Please try again or contact support."},
    )


app.include_router(health.router, prefix=settings.API_V1_PREFIX)
app.include_router(auth.router, prefix=settings.API_V1_PREFIX)
app.include_router(meta.router, prefix=settings.API_V1_PREFIX)
app.include_router(predict.router, prefix=settings.API_V1_PREFIX)
app.include_router(admin.router, prefix=settings.API_V1_PREFIX)


@app.get("/admin", include_in_schema=False)
def admin_page():
    """Lets /admin work without typing the .html extension."""
    return FileResponse("frontend_dist/admin.html")


@app.get("/login", include_in_schema=False)
def login_page():
    """Lets /login work without typing the .html extension."""
    return FileResponse("frontend_dist/login.html")


# ---------------------------------------------------------------------------
# Frontend UI
# ---------------------------------------------------------------------------
# Serves the static frontend (index.html, css/, js/) from frontend_dist/ at
# the repo root. Mounted LAST and at "/" so it never shadows /docs, /redoc,
# /openapi.json, or any /api/v1/... route registered above — Starlette
# matches routes in the order they were added, so those all still win.
#
# This replaces the previous `@app.get("/")` JSON handler (removed below):
# that JSON info is still available, unchanged, at /api/v1/health, which is
# also what this Dockerfile's own HEALTHCHECK already points at, so nothing
# that depends on health-checking is affected. If some external monitor was
# pinging bare "/" expecting that JSON specifically, point it at
# /api/v1/health instead.
app.mount("/", StaticFiles(directory="frontend_dist", html=True), name="frontend")
