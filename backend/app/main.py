import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import actuals, admin, agent, agent_panel, auth, estimates, insights, projects, settings
from app.core.access import authz_guard
from app.core.auth import csrf_ok
from app.core.bootstrap import bootstrap, validate_config
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging import setup_logging
from app.core.usage import deny_model_override, request_user_context

cfg = get_settings()
setup_logging(cfg.log_level)
log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_: FastAPI):
    validate_config(cfg)
    bootstrap()
    log.info("startup", extra={"extra": {"app_env": cfg.app_env, "llm_mode": cfg.llm_mode}})
    yield


app = FastAPI(title="Calibr API", version="1.0.0", lifespan=lifespan,
              docs_url=None if cfg.is_production else "/docs", redoc_url=None,
              openapi_url=None if cfg.is_production else "/openapi.json")
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in cfg.cors_origins.split(",") if o.strip()],
                   allow_credentials=True, allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
                   allow_headers=["Content-Type", "X-CSRF-Token"])


def _err(status: int, code: str, message: str, details=None) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message, "details": details}})


@app.middleware("http")
async def security(request: Request, call_next):
    if not csrf_ok(request):
        return _err(403, "csrf_failed", "Security check failed. Reload the page and try again.")
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > (cfg.max_upload_mb + 1) * 1024 * 1024:
        return _err(413, "too_large", f"Request is larger than {cfg.max_upload_mb} MB")
    with request_user_context(request):
        response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    if cfg.is_production:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


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
    return _err(500, "internal_error", "Something went wrong on our side. Please try again.")


guarded = [Depends(authz_guard), Depends(deny_model_override)]
for r in (projects.router, estimates.router, agent.router, agent_panel.router, actuals.router, insights.router,
          settings.router):
    app.include_router(r, prefix="/api/v1", dependencies=guarded)
app.include_router(admin.router, prefix="/api/v1", dependencies=[Depends(deny_model_override)])
for r in (auth.router, settings.public):
    app.include_router(r, prefix="/api/v1")


@app.get("/health")
def root_health():
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        return settings.health(db)
