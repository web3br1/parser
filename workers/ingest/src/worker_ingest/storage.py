import os
import tempfile
from pathlib import Path

from supabase import create_client


def download_from_storage(storage_path: str) -> str:
    """
    Baixa arquivo do Supabase Storage para /tmp e retorna o caminho local.
    O caller é responsável por deletar o arquivo temporário no finally.
    """
    supabase = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )
    bucket = os.environ["WORKSPACE_STORAGE_BUCKET"]
    data = supabase.storage.from_(bucket).download(storage_path)
    suffix = Path(storage_path).suffix or ".tmp"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir="/tmp")
    tmp.write(data)
    tmp.flush()
    tmp.close()
    return tmp.name
