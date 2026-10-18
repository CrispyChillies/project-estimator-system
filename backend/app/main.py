import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import actuals, agent, estimates, insights, projects, settings
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging import setup_logging
from app.db.session import SessionLocal
from app.services.reference import ensure_reference_data

cfg = get_settings()
setup_logging(cfg.log_level)
log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_: FastAPI):
    with SessionLocal() as db:
        ensure_reference_data(db)
    log.info("startup", extra={"extra": {"llm_mode": cfg.llm_mode}})
    yield


app = FastAPI(title="Calibr API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in cfg.cors_origins.split(",")],
                   allow_methods=["*"], allow_headers=["*"])


def _err(status: int, code: str, message: str, details=None) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message, "details": details}})


@app.exception_handler(AppError)
async def app_error(_: Request, exc: AppError):
    return _err(exc.status, exc.code, exc.message, exc.details)


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    return _err(422, "validation_error", "Invalid request", [
        {"loc": e.get("loc"), "msg": e.get("msg")} for e in exc.errors()])


@app.exception_handler(Exception)
async def unhandled(_: Request, exc: Exception):
    log.exception("unhandled error")
    return _err(500, "internal_error", "Internal server error")


for r in (projects.router, estimates.router, agent.router, actuals.router, insights.router, settings.router):
    app.include_router(r, prefix="/api/v1")


@app.get("/health")
def root_health():
    with SessionLocal() as db:
        return settings.health(db)
