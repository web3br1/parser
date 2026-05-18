from typing import Any, cast

from fastapi import Depends, Header, HTTPException

from context_builder.config import Settings, get_settings
from supabase import Client, create_client

UPLOAD_ALLOWED_ROLES: frozenset[str] = frozenset({"owner", "manager"})
REVIEW_ALLOWED_ROLES: frozenset[str] = frozenset({"reviewer", "manager", "owner"})
PUBLISH_ALLOWED_ROLES: frozenset[str] = frozenset({"manager", "owner"})
WORKSPACE_MEMBER_ROLES: frozenset[str] = frozenset({"owner", "manager", "reviewer", "staff"})


def _row(data: Any) -> dict[str, Any] | None:
    if isinstance(data, dict):
        return data
    return None


def get_supabase_anon(settings: Settings = Depends(get_settings)) -> Client:
    """Client anon para validar JWT do usuário."""
    return create_client(settings.supabase_url, settings.supabase_anon_key)


def get_supabase_service_for_backend_only(settings: Settings = Depends(get_settings)) -> Client:
    """Client service role para operações privilegiadas do backend."""
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


def get_supabase_service(settings: Settings = Depends(get_settings)) -> Client:
    """Compatibility alias; prefer get_supabase_service_for_backend_only in new routes."""
    return get_supabase_service_for_backend_only(settings)


async def get_current_user(
    authorization: str | None = Header(default=None),
    db: Client = Depends(get_supabase_anon),
) -> dict[str, Any]:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing_bearer_token")

    token = authorization.removeprefix("Bearer ").strip()
    try:
        user_response = db.auth.get_user(token)
        user = user_response.user if user_response is not None else None
        if not user:
            raise HTTPException(status_code=401, detail="invalid_token")
        return {"id": user.id, "email": user.email}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="invalid_token") from None


async def require_workspace_member(
    workspace_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: Client = Depends(get_supabase_service_for_backend_only),
) -> dict[str, Any]:
    result = cast(Any, (
        db.table("workspace_members")
        .select("role")
        .eq("workspace_id", workspace_id)
        .eq("user_id", current_user["id"])
        .maybe_single()
        .execute()
    ))
    membership = _row(result.data)
    if not membership:
        raise HTTPException(status_code=403, detail="not_workspace_member")
    role = str(membership["role"])
    if role not in WORKSPACE_MEMBER_ROLES:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "invalid_workspace_role",
                "allowed": sorted(WORKSPACE_MEMBER_ROLES),
                "current": role,
            },
        )

    return {
        "user": current_user,
        "role": role,
        "workspace_id": workspace_id,
    }


async def require_upload_permission(
    membership: dict[str, Any] = Depends(require_workspace_member),
) -> dict[str, Any]:
    if membership["role"] not in UPLOAD_ALLOWED_ROLES:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "insufficient_role",
                "required": sorted(UPLOAD_ALLOWED_ROLES),
                "current": membership["role"],
            },
        )
    return membership


async def require_review_role(
    membership: dict[str, Any] = Depends(require_workspace_member),
) -> dict[str, Any]:
    """
    Verifica que o membro tem role para revisar fatos.
    reviewer, manager e owner podem revisar. staff não pode.
    Construído sobre require_workspace_member (TASK-003).
    """
    if membership["role"] not in REVIEW_ALLOWED_ROLES:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "insufficient_role",
                "required": sorted(REVIEW_ALLOWED_ROLES),
                "current": membership["role"],
            },
        )
    return membership


async def require_publish_role(
    membership: dict[str, Any] = Depends(require_workspace_member),
) -> dict[str, Any]:
    if membership["role"] not in PUBLISH_ALLOWED_ROLES:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "insufficient_role",
                "required": sorted(PUBLISH_ALLOWED_ROLES),
                "current": membership["role"],
            },
        )
    return membership


def create_supabase_client(settings: Settings | None = None) -> Client:
    resolved = settings or get_settings()
    return get_supabase_service_for_backend_only(resolved)
