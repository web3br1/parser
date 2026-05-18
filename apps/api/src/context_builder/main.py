from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from observability.errors import DomainError, TechnicalError
from observability.logging import get_logger
from observability.middleware import RequestIdMiddleware, request_id_from_scope
from observability.security_middleware import (
    add_security_headers,
    enforce_rate_limit,
    enforce_request_body_limit,
)
from starlette.middleware.trustedhost import TrustedHostMiddleware

from context_builder.config import get_settings
from context_builder.routers import (
    health,
    knowledge,
    privacy,
    query,
    review,
    sources,
    unknown,
    workspaces,
)

logger = get_logger("api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    assert settings.supabase_url, "SUPABASE_URL não configurado"
    assert settings.supabase_service_role_key, "SUPABASE_SERVICE_ROLE_KEY não configurado"
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    if settings.app_env == "production" and "*" in settings.trusted_hosts:
        raise RuntimeError("TRUSTED_HOSTS must not include '*' in production")
    app = FastAPI(
        title="Context Builder API",
        version="0.1.0",
        docs_url="/docs" if settings.app_env != "production" else None,
        redoc_url=None,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.app_env == "development" else settings.cors_allowed_origins,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
    if settings.trusted_hosts:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)
    app.add_middleware(RequestIdMiddleware)

    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next: Any) -> Any:
        return await enforce_rate_limit(
            request,
            call_next,
            enabled=settings.rate_limit_enabled,
            default_requests=settings.rate_limit_default_requests,
            query_requests=settings.rate_limit_query_requests,
            upload_requests=settings.rate_limit_upload_requests,
            workspace_create_requests=settings.rate_limit_workspace_create_requests,
            privacy_requests=settings.rate_limit_privacy_requests,
            review_mutation_requests=settings.rate_limit_review_mutation_requests,
            window_seconds=settings.rate_limit_window_seconds,
        )

    @app.middleware("http")
    async def request_body_limit_middleware(request: Request, call_next: Any) -> Any:
        return await enforce_request_body_limit(
            request,
            call_next,
            max_body_bytes=settings.max_request_body_bytes,
        )

    @app.middleware("http")
    async def security_headers_middleware(request: Request, call_next: Any) -> Any:
        return await add_security_headers(request, call_next, app_env=settings.app_env)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: object,
        exc: RequestValidationError,
    ) -> JSONResponse:
        request_id = request_id_from_scope(request)
        return JSONResponse(
            status_code=422,
            content={
                "detail": "validation_error",
                "errors": exc.errors(),
                "request_id": request_id,
            },
            headers={"X-Request-ID": request_id} if request_id else None,
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: object, exc: Exception) -> JSONResponse:
        if isinstance(exc, HTTPException):
            raise exc
        request_id = request_id_from_scope(request)
        if isinstance(exc, DomainError):
            logger.warning(
                "domain_exception",
                request_id=request_id,
                error_type=type(exc).__name__,
                error_code=exc.code,
                safe_detail=exc.safe_detail,
            )
            return JSONResponse(
                status_code=400,
                content={"detail": {"code": exc.code, **exc.safe_detail}, "request_id": request_id},
                headers={"X-Request-ID": request_id} if request_id else None,
            )
        if isinstance(exc, TechnicalError):
            logger.exception(
                "technical_exception",
                exc,
                request_id=request_id,
                error_code=exc.code,
                provider=exc.provider,
                operation=exc.operation,
            )
        else:
            logger.exception("unhandled_exception", exc, request_id=request_id)
        return JSONResponse(
            status_code=500,
            content={"detail": "internal_server_error", "request_id": request_id},
            headers={"X-Request-ID": request_id} if request_id else None,
        )

    app.include_router(health.router)
    app.include_router(workspaces.router, prefix="/workspaces", tags=["workspaces"])
    app.include_router(
        sources.router,
        prefix="/workspaces/{workspace_id}/sources",
        tags=["sources"],
    )
    app.include_router(
        review.router,
        prefix="/workspaces/{workspace_id}/review",
        tags=["review"],
    )
    app.include_router(
        unknown.router,
        prefix="/workspaces/{workspace_id}/unknown",
        tags=["unknown"],
    )
    app.include_router(
        query.router,
        prefix="/workspaces/{workspace_id}/query",
        tags=["query"],
    )
    app.include_router(
        knowledge.router,
        prefix="/workspaces/{workspace_id}/knowledge",
        tags=["knowledge"],
    )
    app.include_router(
        privacy.router,
        prefix="/workspaces/{workspace_id}/privacy",
        tags=["privacy"],
    )
    return app


app: Any = create_app()
