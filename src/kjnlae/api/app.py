"""Versioned HTTP transport. Only deployment configuration supplies authority."""

import asyncio
import hmac
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, Literal, cast

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field, model_validator
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from kjnlae import Guard, __version__
from kjnlae.api.audit import configure_audit
from kjnlae.api.config import Settings
from kjnlae.api.middleware import LimitsMiddleware
from kjnlae.context import TrustedSecurityContext
from kjnlae.evaluation.benchmark import benchmark
from kjnlae.evaluation.sandbox import run_scenarios
from kjnlae.guards.actions import ActionGateway, Authority
from kjnlae.guards.output import OutputGuard
from kjnlae.guards.resources import HostAuthority, ProposedAction, ResourceCatalog
from kjnlae.schemas import ActionRequest, ActionResult, OutputRequest, OutputResult
from kjnlae.schemas_v2 import ContentEnvelope, InspectionRequestV2, InspectionResultV2, StrictV2
from kjnlae.storage.sqlite import SQLiteHistory


class ActionRequestV2(StrictV2):
    action: ProposedAction


class OutputRequestV2(StrictV2):
    text: str = Field(max_length=32768)
    structured: dict[str, str] | None = None

    @model_validator(mode="after")
    def bounded_output(self) -> "OutputRequestV2":
        if len(self.text) + sum(len(value) for value in (self.structured or {}).values()) > 32768:
            raise ValueError("Combined output exceeds supported limit")
        return self


class OutputInspectionResponseV2(StrictV2):
    inspection_decision: Literal["ALLOW", "BLOCK"]
    violations: list[str]
    release_authorized: Literal[False] = False
    policy_id: str = "output-inspection-v2"


class RagInspectRequestV2(StrictV2):
    chunks: list[ContentEnvelope] = Field(min_length=1, max_length=16)


def create_app(
    settings: Settings | None = None,
    *,
    action_gateway: ActionGateway | None = None,
    trusted_authority: Authority | None = None,
    trusted_authority_v2: HostAuthority | None = None,
    resource_catalog: ResourceCatalog | None = None,
    guard_override: Guard | None = None,
) -> FastAPI:
    cfg = settings or Settings.from_env()
    audit = configure_audit()
    guard = guard_override or Guard(model_dir=cfg.model_dir, model_hash=cfg.model_hash)
    authority = trusted_authority or cfg.authority()
    configured_authority, configured_catalog = cfg.authority_v2()
    host_authority = trusted_authority_v2 or configured_authority
    catalog = resource_catalog or configured_catalog
    actions = action_gateway or ActionGateway()
    outputs = OutputGuard(cfg.output_secrets, cfg.output_hosts)
    history = SQLiteHistory(cfg.database, cfg.retention)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if guard.classifier is not None:
            await asyncio.to_thread(guard.scan, "Service readiness probe.")
        yield
        if guard_override is None:
            guard.close()

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
        return guard.capabilities()["model_status"] == "AVAILABLE"

    @app.get("/health/ready")
    def ready() -> JSONResponse:
        try:
            history.list(1, tenant=host_authority.tenant)
            db_ok = True
        except Exception:
            db_ok = False
        healthy = db_ok and controls_ready()
        return JSONResponse(
            {
                "status": "ready" if healthy else "not_ready",
                "database": db_ok,
                "model": guard.capabilities()["model_status"],
            },
            status_code=200 if healthy else 503,
        )

    @app.get("/v2/system/capabilities", dependencies=protected)
    def capabilities() -> dict[str, Any]:
        return {
            "version": __version__,
            **guard.capabilities(),
            "action_policy": "action-v2",
            "output_policy": "output-v2",
            "production": cfg.production,
            "limitations": [
                "Scanner cannot guarantee LLM resistance",
                "Action endpoint authorizes but never executes tools",
                "Known-secret output checks are not universal DLP",
            ],
        }

    @app.post("/v2/scan", response_model=InspectionResultV2, dependencies=protected)
    @app.post("/v2/guard/input", response_model=InspectionResultV2, dependencies=protected)
    def scan(request: InspectionRequestV2) -> InspectionResultV2:
        result = guard.inspect(request)
        history.record(result.model_dump(), tenant=host_authority.tenant)
        audit.info(
            "scan_decision",
            extra={
                "decision": result.policy_decision,
                "inspection_complete": result.inspection_complete,
            },
        )
        return result

    @app.post("/v2/guard/action", dependencies=protected)
    def action_v2(request: ActionRequestV2) -> dict[str, Any]:
        result = actions.authorize_v2(
            request.action,
            host_authority,
            catalog,
            controls_ready=controls_ready(),
        )
        audit.info("action_decision", extra={"decision": result.decision})
        return result.model_dump()

    @app.post("/v2/guard/output", response_model=OutputInspectionResponseV2, dependencies=protected)
    def output_v2(request: OutputRequestV2) -> OutputInspectionResponseV2:
        result = outputs.inspect(request.text, request.structured)
        audit.info("output_inspection", extra={"decision": result.decision})
        return OutputInspectionResponseV2(
            inspection_decision=cast(Literal["ALLOW", "BLOCK"], result.decision),
            violations=result.violations,
        )

    @app.post("/v2/rag/inspect", dependencies=protected)
    def inspect_rag(request: RagInspectRequestV2) -> list[InspectionResultV2]:
        context = TrustedSecurityContext(
            host_authority.principal, host_authority.tenant, host_authority.task
        )
        return guard.inspect_chunks(request.chunks, context)

    @app.get("/v2/history", dependencies=protected)
    def get_history() -> list[dict[str, Any]]:
        return history.list(tenant=host_authority.tenant)

    @app.delete("/v2/history", dependencies=protected)
    def delete_history() -> dict[str, bool]:
        history.clear(tenant=host_authority.tenant)
        return {"cleared": True}

    if not cfg.production:

        @app.get("/v2/lab", dependencies=protected)
        def lab() -> list[dict[str, Any]]:
            return run_scenarios(guard)

        @app.get("/v2/evaluation", dependencies=protected)
        def evaluation() -> dict[str, Any]:
            return benchmark(guard)

    @app.post("/v1/scan", dependencies=protected)
    @app.post("/v1/guard/input", dependencies=protected)
    def retired_scan() -> JSONResponse:
        return JSONResponse({"error": "retired_endpoint", "migration": "/v2/scan"}, status_code=410)

    @app.post("/v1/guard/action", response_model=ActionResult, dependencies=protected)
    def action(request: ActionRequest) -> ActionResult:
        if request.approval_token is not None:
            raise HTTPException(422, "Approval tokens belong to trusted host execution")
        return actions.authorize(request.action, authority, controls_ready=controls_ready())

    @app.post("/v1/guard/output", response_model=OutputResult, dependencies=protected)
    def output(request: OutputRequest) -> OutputResult:
        return outputs.inspect(request.text, request.structured)

    dist = Path(__file__).resolve().parents[3] / "frontend" / "dist"
    if not dist.exists():
        dist = Path("/app/frontend/dist")
    if dist.is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/", include_in_schema=False)
        def index() -> FileResponse:
            return FileResponse(dist / "index.html")

    return app
