from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from fastapi import HTTPException, UploadFile

from context_builder.schemas.context_build import (
    ContextBuildFileMetadata,
    ContextBuildStagedUploadResponse,
)

DEFAULT_STAGING_ROOT = Path(r"C:\tmp\parser-context-build-staging")
ALLOWED_EXTENSIONS = {".md", ".csv", ".txt", ".pdf", ".docx", ".xlsx", ".zip"}
BLOCKED_EXTENSIONS = {".exe", ".ps1", ".sh", ".bat", ".cmd", ".dll", ".env", ".pem", ".key"}
MAX_STAGED_FILES = 1000
MAX_STAGED_BYTES = 100 * 1024 * 1024


@dataclass(frozen=True)
class StagedUpload:
    staged_upload_id: str
    workspace_id: str
    root: Path
    files_root: Path
    source_root: Path
    input_hash: str
    input_fingerprint: str
    files: list[ContextBuildFileMetadata]
    warnings: list[str]
    blocking_reasons: list[str]


@dataclass(frozen=True)
class _StagedFile:
    relative_path: str
    data: bytes


async def stage_context_build_upload(
    *,
    workspace_id: str,
    uploads: list[UploadFile],
    relative_paths: str | None,
) -> ContextBuildStagedUploadResponse:
    staged_files = await _collect_uploads(uploads, relative_paths)
    upload_id = uuid.uuid4().hex
    root = _workspace_staging_root(workspace_id) / upload_id
    files_root = root / "files"
    try:
        files_root.mkdir(parents=True, exist_ok=False)
        response_files = _write_staged_files(files_root, staged_files)
        source_root = _source_root_for(files_root, response_files)
        input_hash = _input_hash(staged_files)
        input_fingerprint = f"staged_upload:{input_hash.removeprefix('sha256:')}"
        metadata = {
            "staged_upload_id": upload_id,
            "workspace_id": workspace_id,
            "input_hash": input_hash,
            "input_fingerprint": input_fingerprint,
            "files": [item.model_dump() for item in response_files],
            "source_root_relative": source_root.relative_to(files_root).as_posix()
            if source_root != files_root
            else ".",
            "warnings": [],
            "blocking_reasons": [],
        }
        (root / "metadata.json").write_text(
            json.dumps(metadata, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    except Exception:
        shutil.rmtree(root, ignore_errors=True)
        raise

    return ContextBuildStagedUploadResponse(
        staged_upload_id=upload_id,
        input_hash=input_hash,
        input_fingerprint=input_fingerprint,
        files=response_files,
    )


def resolve_staged_upload(*, workspace_id: str, staged_upload_id: str) -> StagedUpload:
    if not staged_upload_id or any(char in staged_upload_id for char in ("/", "\\", ".")):
        raise HTTPException(status_code=404, detail="staged_upload_not_found")
    root = (_workspace_staging_root(workspace_id) / staged_upload_id).resolve()
    workspace_root = _workspace_staging_root(workspace_id).resolve()
    if not _is_relative_to(root, workspace_root):
        raise HTTPException(status_code=404, detail="staged_upload_not_found")
    metadata_path = root / "metadata.json"
    if not metadata_path.exists():
        raise HTTPException(status_code=404, detail="staged_upload_not_found")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    files_root = root / "files"
    source_root_relative = metadata.get("source_root_relative", ".")
    source_root = (
        files_root
        if source_root_relative == "."
        else (files_root / _normalize_relative_path(str(source_root_relative))).resolve()
    )
    if not _is_relative_to(source_root, files_root.resolve()):
        raise HTTPException(status_code=400, detail={"code": "invalid_staged_upload"})
    files = [
        ContextBuildFileMetadata(**item)
        for item in metadata.get("files", [])
        if isinstance(item, dict)
    ]
    return StagedUpload(
        staged_upload_id=staged_upload_id,
        workspace_id=workspace_id,
        root=root,
        files_root=files_root,
        source_root=source_root,
        input_hash=str(metadata["input_hash"]),
        input_fingerprint=str(metadata["input_fingerprint"]),
        files=files,
        warnings=list(metadata.get("warnings", [])),
        blocking_reasons=list(metadata.get("blocking_reasons", [])),
    )


async def _collect_uploads(
    uploads: list[UploadFile],
    relative_paths: str | None,
) -> list[_StagedFile]:
    if not uploads:
        raise HTTPException(status_code=400, detail={"code": "no_files"})
    paths = _parse_relative_paths(relative_paths)
    if paths is not None and len(paths) != len(uploads):
        raise HTTPException(status_code=400, detail={"code": "relative_paths_count_mismatch"})

    if len(uploads) == 1:
        upload = uploads[0]
        filename = paths[0] if paths is not None else upload.filename or ""
        data = await upload.read()
        if len(data) > MAX_STAGED_BYTES:
            raise HTTPException(status_code=400, detail={"code": "staged_upload_too_large"})
        if _extension_for(filename) == ".zip":
            return _extract_zip(data)
        return [_staged_file(filename, data)]

    if len(uploads) > MAX_STAGED_FILES:
        raise HTTPException(status_code=400, detail={"code": "too_many_files"})
    staged_files: list[_StagedFile] = []
    total_bytes = 0
    for index, upload in enumerate(uploads):
        raw_path = paths[index] if paths is not None else upload.filename or ""
        data = await upload.read()
        total_bytes += len(data)
        if total_bytes > MAX_STAGED_BYTES:
            raise HTTPException(status_code=400, detail={"code": "staged_upload_too_large"})
        staged_files.append(_staged_file(raw_path, data))
    return _validate_unique(staged_files)


def _parse_relative_paths(relative_paths: str | None) -> list[str] | None:
    if relative_paths is None or relative_paths == "":
        return None
    try:
        value = json.loads(relative_paths)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail={"code": "invalid_relative_paths"}) from exc
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise HTTPException(status_code=400, detail={"code": "invalid_relative_paths"})
    return value


def _extract_zip(data: bytes) -> list[_StagedFile]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=400, detail={"code": "invalid_zip"}) from exc
    staged_files: list[_StagedFile] = []
    total_bytes = 0
    with archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            if len(staged_files) >= MAX_STAGED_FILES:
                raise HTTPException(status_code=400, detail={"code": "too_many_files"})
            if info.file_size < 0:
                raise HTTPException(status_code=400, detail={"code": "invalid_zip"})
            total_bytes += info.file_size
            if total_bytes > MAX_STAGED_BYTES:
                raise HTTPException(status_code=400, detail={"code": "staged_upload_too_large"})
            try:
                data = archive.read(info)
            except (RuntimeError, zipfile.BadZipFile) as exc:
                raise HTTPException(status_code=400, detail={"code": "invalid_zip"}) from exc
            staged_files.append(_staged_file(info.filename, data))
    return _validate_unique(staged_files)


def _staged_file(raw_path: str, data: bytes) -> _StagedFile:
    relative_path = _normalize_relative_path(raw_path)
    _validate_extension(relative_path)
    return _StagedFile(relative_path=relative_path, data=data)


def _normalize_relative_path(raw_path: str) -> str:
    value = raw_path.strip()
    if not value:
        raise HTTPException(status_code=400, detail={"code": "invalid_relative_path"})
    if value.startswith(("/", "\\")) or value.startswith("//") or value.startswith("\\\\"):
        raise HTTPException(status_code=400, detail={"code": "invalid_relative_path"})
    if len(value) >= 2 and value[1] == ":":
        raise HTTPException(status_code=400, detail={"code": "invalid_relative_path"})
    normalized = value.replace("\\", "/")
    parts = PurePosixPath(normalized).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise HTTPException(status_code=400, detail={"code": "invalid_relative_path"})
    return PurePosixPath(*parts).as_posix()


def _validate_extension(relative_path: str) -> None:
    path = PurePosixPath(relative_path)
    name = path.name.casefold()
    extension = _extension_for(name)
    if name == ".env" or extension in BLOCKED_EXTENSIONS:
        raise HTTPException(status_code=400, detail={"code": "blocked_file_type"})
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail={"code": "unsupported_file_type"})


def _extension_for(path: str) -> str:
    name = PurePosixPath(path).name.casefold()
    if name == ".env":
        return ".env"
    return PurePosixPath(name).suffix


def _validate_unique(files: list[_StagedFile]) -> list[_StagedFile]:
    seen: set[str] = set()
    for item in files:
        key = item.relative_path.casefold()
        if key in seen:
            raise HTTPException(status_code=400, detail={"code": "duplicate_relative_path"})
        seen.add(key)
    return files


def _write_staged_files(
    files_root: Path,
    files: list[_StagedFile],
) -> list[ContextBuildFileMetadata]:
    response_files = []
    for item in files:
        target = (files_root / item.relative_path).resolve()
        if not _is_relative_to(target, files_root.resolve()):
            raise HTTPException(status_code=400, detail={"code": "invalid_relative_path"})
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(item.data)
        response_files.append(
            ContextBuildFileMetadata(
                name=Path(item.relative_path).name,
                size=len(item.data),
                relative_path=item.relative_path,
            )
        )
    return response_files


def _source_root_for(files_root: Path, files: list[ContextBuildFileMetadata]) -> Path:
    for item in files:
        if Path(item.relative_path or item.name).name.casefold() == "00_source_manifest.md":
            parent = Path(item.relative_path or item.name).parent
            return files_root if str(parent) == "." else (files_root / parent).resolve()
    return files_root


def _input_hash(files: list[_StagedFile]) -> str:
    digest = hashlib.sha256()
    for item in sorted(files, key=lambda value: value.relative_path.casefold()):
        digest.update(item.relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(item.data)
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


def _workspace_staging_root(workspace_id: str) -> Path:
    root = Path(os.environ.get("CONTEXT_BUILD_STAGING_ROOT", str(DEFAULT_STAGING_ROOT)))
    safe_workspace = hashlib.sha256(workspace_id.encode("utf-8")).hexdigest()
    return (root / "default" / safe_workspace).expanduser().resolve()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
