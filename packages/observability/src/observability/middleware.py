from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import uuid4

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from .context import request_id_context

REQUEST_ID_HEADER = "X-Request-ID"


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid4())
        request.state.request_id = request_id
        with request_id_context(request_id):
            response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


def request_id_from_scope(request: object) -> str | None:
    state = getattr(request, "state", None)
    request_id = getattr(state, "request_id", None)
    return str(request_id) if request_id else None
