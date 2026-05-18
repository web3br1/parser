from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from security.file_validator import FileRejectionReason, validate_file


def test_good_pdf_valid(tmp_path: Path) -> None:
    path = tmp_path / "good.pdf"
    path.write_bytes(b"%PDF-1.7 content")
    result = validate_file(path, "application/pdf")
    assert result.valid is True


def test_fake_pdf_fails_magic(tmp_path: Path) -> None:
    path = tmp_path / "fake.pdf"
    path.write_text("plain text", encoding="utf-8")
    result = validate_file(path, "application/pdf")
    assert result.valid is False
    assert result.reason == FileRejectionReason.MAGIC_BYTES_FAIL


def test_empty_file_fails(tmp_path: Path) -> None:
    path = tmp_path / "empty.txt"
    path.write_bytes(b"")
    result = validate_file(path, "text/plain")
    assert result.reason == FileRejectionReason.EMPTY_FILE


def test_size_exceeded_fails(tmp_path: Path) -> None:
    path = tmp_path / "big.txt"
    with path.open("wb") as file:
        file.seek(51 * 1024 * 1024)
        file.write(b"x")
    result = validate_file(path, "text/plain")
    assert result.reason == FileRejectionReason.SIZE_EXCEEDED


def test_blocked_extension_fails(tmp_path: Path) -> None:
    path = tmp_path / "run.exe"
    path.write_bytes(b"MZ")
    result = validate_file(path, "application/octet-stream")
    assert result.reason == FileRejectionReason.EXTENSION_BLOCKED


def test_docx_with_vba_project_bin_rejected_as_macro(tmp_path: Path) -> None:
    path = tmp_path / "macro.docx"
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("word/document.xml", "<document />")
        archive.writestr("word/vbaProject.bin", b"macro")

    result = validate_file(
        path,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    assert result.valid is False
    assert result.reason == FileRejectionReason.MACRO_DETECTED


def test_high_compression_xlsx_rejected_as_zip_bomb(tmp_path: Path) -> None:
    path = tmp_path / "bomb.xlsx"
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("xl/workbook.xml", "A" * (12 * 1024 * 1024))

    result = validate_file(
        path,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    assert result.valid is False
    assert result.reason == FileRejectionReason.ZIP_BOMB_SUSPECTED


def test_large_uncompressed_office_archive_rejected_even_with_normal_ratio(
    tmp_path: Path,
) -> None:
    path = tmp_path / "large.xlsx"
    payload = bytes(range(256)) * (11 * 1024 * 1024 // 256)
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("xl/workbook.xml", payload)

    result = validate_file(
        path,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    assert result.valid is False
    assert result.reason == FileRejectionReason.ZIP_BOMB_SUSPECTED


def test_office_archive_with_path_traversal_entry_rejected(tmp_path: Path) -> None:
    path = tmp_path / "traversal.docx"
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("../evil.bin", "x")

    result = validate_file(
        path,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    assert result.valid is False
    assert result.reason == FileRejectionReason.ZIP_STRUCTURE_UNSAFE
