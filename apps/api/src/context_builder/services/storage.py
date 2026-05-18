import os

from fastapi import HTTPException

from supabase import create_client


def upload_to_storage(*, content: bytes, path: str, mime_type: str) -> str:
    """
    Faz upload para o bucket privado. Nunca logar o conteúdo do arquivo.
    """
    supabase = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )
    bucket = os.environ["WORKSPACE_STORAGE_BUCKET"]
    try:
        supabase.storage.from_(bucket).upload(
            path=path,
            file=content,
            file_options={"content-type": mime_type, "cache-control": "3600"},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail="storage_upload_failed") from exc
    return path


def delete_from_storage(path: str) -> None:
    supabase = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )
    bucket = os.environ["WORKSPACE_STORAGE_BUCKET"]
    supabase.storage.from_(bucket).remove([path])
