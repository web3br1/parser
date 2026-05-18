from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from hashlib import sha256
from time import monotonic
from typing import cast

from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class RequestBodyTooLargeError(Exception):
    pass


@dataclass(frozen=True)
class RateLimitRule:
    name: str
    requests: int
    window_seconds: int


_RATE_LIMIT_BUCKETS: dict[str, tuple[int, float]] = {}


async def enforce_rate_limit(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
    *,
    enabled: bool,
    default_requests: int,
    query_requests: int,
    upload_requests: int,
    workspace_create_requests: int,
    privacy_requests: int,
    review_mutation_requests: int,
    window_seconds: int,
) -> Response:
    if not enabled:
        return await call_next(request)

    rule = _rate_limit_rule(
        request,
        default_requests=default_requests,
        query_requests=query_requests,
        upload_requests=upload_requests,
        workspace_create_requests=workspace_create_requests,
        privacy_requests=privacy_requests,
        review_mutation_requests=review_mutation_requests,
        window_seconds=window_seconds,
    )
    if rule is None:
        return await call_next(request)

    key = _rate_limit_key(request, rule.name)
    now = monotonic()
    count, reset_at = _RATE_LIMIT_BUCKETS.get(key, (0, now + rule.window_seconds))
    if now >= reset_at:
        count = 0
        reset_at = now + rule.window_seconds
    count += 1
    _RATE_LIMIT_BUCKETS[key] = (count, reset_at)

    if count > rule.requests:
        retry_after = max(1, round(reset_at - now))
        return JSONResponse(
            status_code=429,
            content={"detail": "rate_limited", "code": rule.name},
            headers={"Retry-After": str(retry_after)},
        )
    return await call_next(request)


async def enforce_request_body_limit(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
    *,
    max_body_bytes: int,
) -> Response:
    content_length = request.headers.get("content-length")
    if (
        content_length is not None
        and content_length.isdigit()
        and int(content_length) > max_body_bytes
    ):
        return JSONResponse(
            status_code=413,
            content={"detail": "request_body_too_large"},
        )

    bytes_seen = 0
    receive = request._receive  # noqa: SLF001

    async def limited_receive() -> dict[str, object]:
        nonlocal bytes_seen
        message = await receive()
        if message.get("type") == "http.request":
            body = message.get("body", b"")
            if isinstance(body, bytes):
                bytes_seen += len(body)
                if bytes_seen > max_body_bytes:
                    raise RequestBodyTooLargeError
        return cast(dict[str, object], message)

    request._receive = limited_receive  # noqa: SLF001
    try:
        return await call_next(request)
    except RequestBodyTooLargeError:
        return JSONResponse(
            status_code=413,
            content={"detail": "request_body_too_large"},
        )


def reset_rate_limit_state() -> None:
    _RATE_LIMIT_BUCKETS.clear()


def _rate_limit_rule(
    request: Request,
    *,
    default_requests: int,
    query_requests: int,
    upload_requests: int,
    workspace_create_requests: int,
    privacy_requests: int,
    review_mutation_requests: int,
    window_seconds: int,
) -> RateLimitRule | None:
    method = request.method.upper()
    path = request.url.path
    if method == "POST" and path == "/workspaces":
        return RateLimitRule("workspace_create", workspace_create_requests, window_seconds)
    if method == "POST" and path.endswith("/query"):
        return RateLimitRule("query", query_requests, window_seconds)
    if method == "POST" and path.endswith("/sources/upload"):
        return RateLimitRule("upload", upload_requests, window_seconds)
    if method == "POST" and "/privacy/" in path:
        return RateLimitRule("privacy", privacy_requests, window_seconds)
    if method == "POST" and ("/review/" in path or "/unknown/" in path):
        return RateLimitRule("review_mutation", review_mutation_requests, window_seconds)
    if method in {"POST", "PUT", "PATCH", "DELETE"}:
        return RateLimitRule("mutation", default_requests, window_seconds)
    return None


def _rate_limit_key(request: Request, rule_name: str) -> str:
    authorization = request.headers.get("authorization", "")
    actor = authorization if authorization.startswith("Bearer ") else ""
    client_host = request.client.host if request.client else "unknown"
    identity = actor or client_host
    digest = sha256(identity.encode()).hexdigest()
    return f"{rule_name}:{digest}"


async def add_security_headers(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
    *,
    app_env: str,
) -> Response:
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if app_env == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response
