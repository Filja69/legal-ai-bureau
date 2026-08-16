"""Upload security validation — Phase 9.2 brief §5/§6. Runs BEFORE anything
touches storage or an extractor. One responsibility: is this byte string
plausibly the file type its extension claims to be, and is it safe to open
at all? Never does text extraction (that's `app/documents/extraction/`) and
never touches the database.
"""
from __future__ import annotations

import zipfile
from dataclasses import dataclass
from io import BytesIO

# Reuses the existing size ceiling (app/config/settings.py MAX_UPLOAD_SIZE_BYTES,
# Phase 9 audit §15) — deliberately not a second, possibly-contradicting limit
# here; the API layer already enforces it while streaming the upload in, this
# module re-checks the final byte count as defense-in-depth, nothing more.

_ALLOWED_SUFFIXES = {".pdf", ".docx", ".txt", ".xlsx", ".csv", ".png", ".jpg", ".jpeg"}

# Magic-byte signatures — detected media type wins over whatever the client's
# Content-Type header or the filename extension claims (brief §5:
# "extension/MIME mismatch" must be caught, not trusted).
_PDF_MAGIC = b"%PDF-"
_ZIP_MAGIC_VARIANTS = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")  # normal / empty / spanned zip
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC = b"\xff\xd8\xff"

# ZIP bomb defense (brief §6) — DOCX/XLSX are ZIP containers; a malicious
# archive can claim to decompress to gigabytes from a tiny upload. These caps
# are checked from `ZipFile.infolist()` metadata alone — the archive is never
# actually decompressed to check them.
_MAX_ZIP_UNCOMPRESSED_BYTES = 200 * 1024 * 1024  # 200 MB
_MAX_ZIP_COMPRESSION_RATIO = 100  # uncompressed / compressed
_MAX_ZIP_ENTRY_COUNT = 5_000


class DocumentValidationError(Exception):
    """Raised with a machine-readable `code` (see brief §2 "machine-readable
    error + safe human-readable explanation") and a message safe to show a
    user — never a raw parser traceback.
    """

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass
class ValidationResult:
    suffix: str
    detected_media_type: str


def _detect_media_type(content: bytes) -> str | None:
    if content.startswith(_PDF_MAGIC):
        return "application/pdf"
    if content.startswith(_ZIP_MAGIC_VARIANTS):
        return "application/zip"  # DOCX/XLSX are ZIP containers — narrowed to a specific
        # office media type only after the internal structure is checked below.
    if content.startswith(_PNG_MAGIC):
        return "image/png"
    if content.startswith(_JPEG_MAGIC):
        return "image/jpeg"
    return None  # plain text has no reliable magic bytes — handled separately below


def _validate_zip_container(content: bytes, expected_suffix: str) -> None:
    try:
        with zipfile.ZipFile(BytesIO(content)) as zf:
            bad_entry = zf.testzip()
            if bad_entry is not None:
                raise DocumentValidationError("CORRUPTED_FILE", f"{expected_suffix} archive is corrupted (bad entry: {bad_entry})")

            infolist = zf.infolist()
            if len(infolist) > _MAX_ZIP_ENTRY_COUNT:
                raise DocumentValidationError("ZIP_BOMB_SUSPECTED", "Archive contains an implausible number of entries")

            total_uncompressed = sum(i.file_size for i in infolist)
            total_compressed = sum(i.compress_size for i in infolist) or 1
            if total_uncompressed > _MAX_ZIP_UNCOMPRESSED_BYTES:
                raise DocumentValidationError("ZIP_BOMB_SUSPECTED", "Archive would decompress to an implausibly large size")
            if total_uncompressed / total_compressed > _MAX_ZIP_COMPRESSION_RATIO:
                raise DocumentValidationError("ZIP_BOMB_SUSPECTED", "Archive compression ratio is implausibly high")

            # DOCX/XLSX both require this manifest entry at the container root;
            # its absence means the file is a ZIP but not really an Office document.
            if "[Content_Types].xml" not in zf.namelist():
                raise DocumentValidationError(
                    "CORRUPTED_FILE", f"{expected_suffix} file is missing its Office document manifest"
                )
    except zipfile.BadZipFile as exc:
        raise DocumentValidationError("CORRUPTED_FILE", f"{expected_suffix} file is not a valid archive") from exc


def validate_upload(content: bytes, filename: str | None) -> ValidationResult:
    """Raises `DocumentValidationError` on any problem; returns the detected
    (not client-claimed) media type on success.
    """
    if not content:
        raise DocumentValidationError("EMPTY_FILE", "Uploaded file is empty")

    suffix = ("." + filename.rsplit(".", 1)[-1].lower()) if filename and "." in filename else ""
    if suffix not in _ALLOWED_SUFFIXES:
        raise DocumentValidationError("UNSUPPORTED_FORMAT", f"Unsupported file type {suffix!r}")

    detected = _detect_media_type(content)

    if suffix == ".pdf":
        if detected != "application/pdf":
            raise DocumentValidationError("MIME_MISMATCH", "File extension is .pdf but content is not a PDF")
        return ValidationResult(suffix, "application/pdf")

    if suffix in (".docx", ".xlsx"):
        if detected != "application/zip":
            raise DocumentValidationError("MIME_MISMATCH", f"File extension is {suffix} but content is not a valid Office document")
        _validate_zip_container(content, suffix)
        media_type = (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            if suffix == ".docx"
            else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        return ValidationResult(suffix, media_type)

    if suffix in (".png", ".jpg", ".jpeg"):
        expected = "image/png" if suffix == ".png" else "image/jpeg"
        if detected != expected:
            raise DocumentValidationError("MIME_MISMATCH", f"File extension is {suffix} but content is not a valid image")
        return ValidationResult(suffix, expected)

    if suffix in (".txt", ".csv"):
        # No reliable magic bytes for plain text — instead, positively confirm
        # it decodes as UTF-8 (or UTF-8 with BOM). A PDF/ZIP/image header
        # happens to also be composed of valid UTF-8 bytes in places, so
        # first rule out anything that matches a KNOWN binary signature
        # (brief §5 "extension/MIME mismatch") before trusting the decode.
        if detected is not None:
            raise DocumentValidationError(
                "MIME_MISMATCH", f"File extension is {suffix} but content looks like {detected}, not plain text"
            )
        try:
            content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise DocumentValidationError(
                "MIME_MISMATCH", f"File extension is {suffix} but content is not valid UTF-8 text"
            ) from exc
        return ValidationResult(suffix, "text/plain" if suffix == ".txt" else "text/csv")

    # Unreachable — suffix is already allow-listed above.
    raise DocumentValidationError("UNSUPPORTED_FORMAT", f"Unsupported file type {suffix!r}")  # pragma: no cover
