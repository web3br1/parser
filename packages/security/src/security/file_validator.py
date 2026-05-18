from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from zipfile import BadZipFile, ZipFile


class FileRejectionReason(StrEnum):
    MIME_MISMATCH = "mime_mismatch"
    MAGIC_BYTES_FAIL = "magic_bytes_fail"
    SIZE_EXCEEDED = "size_exceeded"
    EXTENSION_BLOCKED = "extension_blocked"
    EMPTY_FILE = "empty_file"
    MACRO_DETECTED = "macro_detected"
    ZIP_BOMB_SUSPECTED = "zip_bomb_suspected"
    ZIP_STRUCTURE_UNSAFE = "zip_structure_unsafe"


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    reason: FileRejectionReason | None
    detected_mime: str | None
    file_size_bytes: int


MAGIC_MAP: dict[str, bytes | None] = {
    "application/pdf": b"%PDF",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": b"PK\x03\x04",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": b"PK\x03\x04",
    "text/csv": None,
    "text/plain": None,
}

ALLOWED_EXTENSIONS: set[str] = {".pdf", ".docx", ".xlsx", ".csv", ".txt"}
MAX_FILE_SIZE_BYTES: int = 50 * 1024 * 1024
MAX_ZIP_UNCOMPRESSED_BYTES: int = 10 * 1024 * 1024
MAX_ZIP_COMPRESSION_RATIO: int = 100
MAX_ZIP_ENTRIES: int = 5_000

_EXTENSION_MIME_MAP = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".csv": "text/csv",
    ".txt": "text/plain",
}


def validate_file(path: Path, declared_mime: str) -> ValidationResult:
    stat = path.stat()
    file_size = stat.st_size

    if file_size == 0:
        return ValidationResult(False, FileRejectionReason.EMPTY_FILE, None, file_size)

    if file_size > MAX_FILE_SIZE_BYTES:
        return ValidationResult(False, FileRejectionReason.SIZE_EXCEEDED, None, file_size)

    extension = path.suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        return ValidationResult(False, FileRejectionReason.EXTENSION_BLOCKED, None, file_size)

    expected_magic = MAGIC_MAP.get(declared_mime)
    with path.open("rb") as file:
        header = file.read(2048)

    if expected_magic is not None and not header.startswith(expected_magic):
        detected = _detect_mime_from_header(header, extension, declared_mime)
        return ValidationResult(False, FileRejectionReason.MAGIC_BYTES_FAIL, detected, file_size)

    detected_mime = _detect_mime(path, header, extension, declared_mime)
    if detected_mime != declared_mime:
        return ValidationResult(False, FileRejectionReason.MIME_MISMATCH, detected_mime, file_size)

    if extension in {".docx", ".xlsx"}:
        archive_result = _validate_office_archive(path, detected_mime, file_size)
        if archive_result is not None:
            return archive_result

    return ValidationResult(True, None, detected_mime, file_size)


def magic_available() -> bool:
    try:
        import magic

        magic.from_buffer(b"test", mime=True)
    except Exception:
        return False
    return True


def _detect_mime(path: Path, header: bytes, extension: str, declared_mime: str) -> str | None:
    if extension in {".docx", ".xlsx"} and header.startswith(b"PK\x03\x04"):
        return _EXTENSION_MIME_MAP[extension]
    if extension == ".csv" and declared_mime == "text/csv" and _looks_like_text(header):
        return "text/csv"
    if extension == ".txt" and declared_mime == "text/plain" and _looks_like_text(header):
        return "text/plain"

    try:
        import magic

        return str(magic.from_file(str(path), mime=True))
    except Exception:
        return _detect_mime_from_header(header, extension, declared_mime)


def _detect_mime_from_header(header: bytes, extension: str, declared_mime: str) -> str | None:
    if header.startswith(b"%PDF"):
        return "application/pdf"
    if header.startswith(b"PK\x03\x04") and extension in {".docx", ".xlsx"}:
        return _EXTENSION_MIME_MAP[extension]
    if declared_mime in {"text/csv", "text/plain"} and _looks_like_text(header):
        return declared_mime
    if _looks_like_text(header):
        return "text/plain"
    return None


def _looks_like_text(data: bytes) -> bool:
    if not data:
        return False
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        try:
            data.decode("latin-1")
        except UnicodeDecodeError:
            return False
    return True


def _validate_office_archive(
    path: Path,
    detected_mime: str,
    file_size: int,
) -> ValidationResult | None:
    try:
        with ZipFile(path) as archive:
            total_uncompressed = 0
            total_compressed = 0
            entries = archive.infolist()
            if len(entries) > MAX_ZIP_ENTRIES:
                return ValidationResult(
                    False,
                    FileRejectionReason.ZIP_STRUCTURE_UNSAFE,
                    detected_mime,
                    file_size,
                )
            for info in entries:
                name = info.filename.lower()
                if name.startswith(("/", "\\")) or ".." in name.replace("\\", "/").split("/"):
                    return ValidationResult(
                        False,
                        FileRejectionReason.ZIP_STRUCTURE_UNSAFE,
                        detected_mime,
                        file_size,
                    )
                if name.endswith("vbaproject.bin") or "/vba" in name:
                    return ValidationResult(
                        False,
                        FileRejectionReason.MACRO_DETECTED,
                        detected_mime,
                        file_size,
                    )
                total_uncompressed += info.file_size
                total_compressed += max(info.compress_size, 1)
    except BadZipFile:
        return ValidationResult(
            False,
            FileRejectionReason.MAGIC_BYTES_FAIL,
            detected_mime,
            file_size,
        )

    compression_ratio = total_uncompressed / max(total_compressed, 1)
    if total_uncompressed > MAX_ZIP_UNCOMPRESSED_BYTES:
        return ValidationResult(
            False,
            FileRejectionReason.ZIP_BOMB_SUSPECTED,
            detected_mime,
            file_size,
        )
    if compression_ratio > MAX_ZIP_COMPRESSION_RATIO:
        return ValidationResult(
            False,
            FileRejectionReason.ZIP_BOMB_SUSPECTED,
            detected_mime,
            file_size,
        )
    return None
