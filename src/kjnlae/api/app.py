"""FastAPI transport. Authority is loaded once from trusted host configuration."""

import hmac
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from kjnlae import Guard, __version__
from kjnlae.api.audit import configure_audit
from kjnlae.api.config import Settings
from kjnlae.api.middleware import LimitsMiddleware
from kjnlae.classifiers.local import ModelConfig, TransformersClassifier
from kjnlae.evaluation.benchmark import benchmark
from kjnlae.evaluation.sandbox import run_scenarios
from kjnlae.guards.actions import ActionGateway, Authority
from kjnlae.guards.output import OutputGuard
from kjnlae.schemas import (
    ActionRequest,
    ActionResult,
    OutputRequest,
    OutputResult,
    ScanRequest,
    ScanResult,
)
from kjnlae.storage.sqlite import SQLiteHistory


def create_app(
    settings: Settings | None = None,
    *,
    action_gateway: ActionGateway | None = None,
    trusted_authority: Authority | None = None,
) -> FastAPI:
    cfg = settings or Settings.from_env()
    audit = configure_audit()
    classifier = (
        TransformersClassifier(
            ModelConfig(
                model_id=cfg.model_id, revision=cfg.model_revision, positive_label=cfg.model_label
            )
        )
        if cfg.model_id
        else None
    )
    guard = Guard(classifier)
    authority = trusted_authority or cfg.authority()
    actions = action_gateway or ActionGateway()
    outputs = OutputGuard(cfg.output_secrets, cfg.output_hosts)
    history = SQLiteHistory(cfg.database, cfg.retention)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if cfg.require_ml and classifier:
            # Loading is mandatory for deployments that require this control.
            import asyncio

            await asyncio.to_thread(classifier.classify, "Readiness probe")
        yield
        if classifier:
            classifier.close()

    app = FastAPI(
        title="kjnlae",
        version=__version__,
        lifespan=lifespan,
        docs_url=None if cfg.production else "/docs",
        redoc_url=None if cfg.production else "/redoc",
        openapi_url=None if cfg.production else "/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(cfg.cors_origins),
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.add_middleware(LimitsMiddleware, rate=cfg.rate_limit)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(cfg.allowed_hosts))

    def authenticate(authorization: Annotated[str | None, Header()] = None) -> None:
        if cfg.api_key:
            supplied = (authorization or "").removeprefix("Bearer ")
            if (
                not authorization
                or not authorization.startswith("Bearer ")
                or not hmac.compare_digest(supplied.encode(), cfg.api_key.encode())
            ):
                raise HTTPException(401, "Authentication required")

    protected = [Depends(authenticate)]

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Pydantic errors ordinarily include full offending input; strip it.
        return JSONResponse(
            {
                "error": "validation_error",
                "details": [{"location": list(e["loc"]), "type": e["type"]} for e in exc.errors()],
            },
            status_code=422,
        )

    @app.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse({"error": "internal_error"}, status_code=500)

    @app.get("/health/live")
    def live() -> dict[str, str]:
        return {"status": "live"}

    def controls_ready() -> bool:
        return not cfg.require_ml or (classifier is not None and classifier.is_ready())

    @app.get("/health/ready")
    def ready() -> JSONResponse:
        try:
            history.list(1)
            db_ok = True
        except Exception:
            db_ok = False
        healthy = db_ok and controls_ready()
        return JSONResponse(
            {
                "status": "ready" if healthy else "not_ready",
                "database": db_ok,
                "required_ml": cfg.require_ml,
                "ml": classifier.status if classifier else "disabled",
            },
            status_code=200 if healthy else 503,
        )

    @app.get("/v1/system/capabilities", dependencies=protected)
    def capabilities() -> dict[str, Any]:
        return {
            "version": __version__,
            "deterministic": True,
            "model": classifier.provenance() if classifier else {"status": "disabled"},
            "policy": guard.policy.id,
            "action_policy": "action-v1",
            "output_policy": "output-v1",
            "production": cfg.production,
            "laboratory": not cfg.production,
            "max_characters": 32768,
            "history_retention": cfg.retention,
            "authorized_principal": authority.principal,
            "granted_actions": len(authority.grants),
            "limitations": [
                "Scanner cannot guarantee injection resistance",
                "Authorization endpoint never executes tools",
                "Known-secret output checks are not universal DLP",
                "Analysis metadata cannot grant authority",
                "Approvals are process-local and one-use",
            ],
        }

    @app.post("/v1/scan", response_model=ScanResult, dependencies=protected)
    @app.post("/v1/guard/input", response_model=ScanResult, dependencies=protected)
    def scan(request: ScanRequest) -> ScanResult:
        result = guard.scan_request(request)
        history.record(result.model_dump())
        audit.info(
            "scan_decision",
            extra={"decision": result.decision, "inspection_complete": result.inspection_complete},
        )
        return result

    @app.post("/v1/guard/action", response_model=ActionResult, dependencies=protected)
    def action(request: ActionRequest) -> ActionResult:
        available = controls_ready()
        result = actions.authorize(
            request.action, authority, request.approval_token, controls_ready=available
        )
        audit.info(
            "action_decision", extra={"decision": result.decision, "degraded": not available}
        )
        return result

    @app.post("/v1/guard/output", response_model=OutputResult, dependencies=protected)
    def output(request: OutputRequest) -> OutputResult:
        result = outputs.inspect(request.text, request.structured)
        audit.info("output_decision", extra={"decision": result.decision})
        return result

    @app.get("/v1/history", dependencies=protected)
    def get_history() -> list[dict[str, Any]]:
        return history.list()

    @app.delete("/v1/history", dependencies=protected)
    def delete_history() -> dict[str, bool]:
        history.clear()
        return {"cleared": True}

    if not cfg.production:

        @app.get("/v1/lab", dependencies=protected)
        def lab() -> list[dict[str, Any]]:
            return run_scenarios(guard)

        @app.get("/v1/evaluation", dependencies=protected)
        def evaluation() -> dict[str, Any]:
            # HTTP lab evaluates cheap fixtures only. CLI explicitly opts into ML.
            return benchmark()

    dist = Path(__file__).resolve().parents[3] / "frontend" / "dist"
    # Docker may provide a separate fixed frontend root.
    if not dist.exists():
        dist = Path("/app/frontend/dist")
    if dist.is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/", include_in_schema=False)
        def index() -> FileResponse:
            return FileResponse(dist / "index.html")

    return app
