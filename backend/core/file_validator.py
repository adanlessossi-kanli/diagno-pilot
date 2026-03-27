"""
FileValidator — validation des fichiers uploadés (REQ 3.1–3.5, REQ 4, REQ 5).

Validation en étapes :
  1. Contenu non vide (→ HTTP 400)
  2. Taille (> 20 Mo → HTTP 413)
  3. MIME type via magic bytes (non autorisé ou discordant → HTTP 415)
  4. Extension / MIME canonical map (→ HTTP 415)
  5. Détection polyglot (→ HTTP 415)
  6. Contenu CSV (→ HTTP 415)
  7. Nom de fichier (traversée de répertoire → HTTP 400)

Tous les rejets sont journalisés avec IP, nom de fichier, et raison.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

logger = logging.getLogger(__name__)

ALLOWED_MIME_TYPES: frozenset[str] = frozenset(
    {
        "application/pdf",
        "image/jpeg",
        "image/png",
        "text/csv",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
)

EXTENSION_MIME_MAP: dict[str, str] = {
    ".pdf":  "application/pdf",
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png":  "image/png",
    ".csv":  "text/csv",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

MAX_FILE_SIZE_BYTES: int = 20 * 1024 * 1024  # 20 Mo

# Regex pour détecter les séquences de traversée de répertoire
_PATH_TRAVERSAL_RE = re.compile(r"\.\.[/\\]")

# Magic byte signatures for polyglot detection
_MIME_SIGNATURES: list[tuple[str, bytes]] = [
    ("application/pdf", b"%PDF"),
    ("image/jpeg", b"\xff\xd8"),
    ("image/png", b"\x89PNG\r\n\x1a\n"),
    ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", b"PK\x03\x04"),
]

# Tentative d'import de python-magic avec fallback gracieux
try:
    import magic as _magic  # type: ignore[import-untyped]

    def _detect_mime(content: bytes) -> str:
        return _magic.from_buffer(content, mime=True)

    _MAGIC_AVAILABLE = True
except ImportError:  # pragma: no cover
    _MAGIC_AVAILABLE = False

    def _detect_mime(content: bytes) -> str:  # type: ignore[misc]
        """Fallback minimal basé sur les magic bytes si python-magic n'est pas disponible."""
        if content[:4] == b"%PDF":
            return "application/pdf"
        if content[:2] in (b"\xff\xd8", b"\xff\xe0", b"\xff\xe1"):
            return "image/jpeg"
        if content[:8] == b"\x89PNG\r\n\x1a\n":
            return "image/png"
        # xlsx : ZIP avec signature PK
        if content[:2] == b"PK":
            return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        return "application/octet-stream"


class FileValidator:
    """Valide la taille, le MIME type et le nom d'un fichier uploadé."""

    # Nombre d'octets lus pour la détection MIME
    _MIME_PROBE_BYTES: int = 8192

    def validate_size(self, size_bytes: int) -> None:
        """Lève HTTP 413 si la taille dépasse MAX_FILE_SIZE_BYTES."""
        if size_bytes > MAX_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File size {size_bytes} bytes exceeds the 20 MB limit.",
            )

    def validate_mime(self, content: bytes, declared_mime: str | None) -> None:
        """
        Lève HTTP 415 si :
        - le MIME type détecté n'est pas dans la liste blanche, ou
        - le MIME type déclaré par le client diffère du MIME type détecté.
        """
        detected = _detect_mime(content[: self._MIME_PROBE_BYTES])

        if detected not in ALLOWED_MIME_TYPES:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"MIME type '{detected}' is not allowed. "
                f"Allowed types: {sorted(ALLOWED_MIME_TYPES)}",
            )

        if declared_mime and declared_mime != detected:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=(
                    f"Declared MIME type '{declared_mime}' does not match "
                    f"detected MIME type '{detected}'."
                ),
            )

    def validate_filename(self, filename: str) -> None:
        """Lève HTTP 400 si le nom de fichier contient une séquence de traversée de répertoire."""
        if _PATH_TRAVERSAL_RE.search(filename):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Filename '{filename}' contains a path traversal sequence.",
            )

    def validate_not_empty(self, content: bytes) -> None:
        """Raise HTTP 400 if content is empty."""
        if len(content) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File is empty.",
            )

    def validate_extension(self, filename: str, detected_mime: str) -> None:
        """
        Raise HTTP 415 if the file extension is absent from EXTENSION_MIME_MAP
        or does not match the detected MIME type.
        """
        suffix = Path(filename).suffix.lower()
        if suffix not in EXTENSION_MIME_MAP:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"File extension '{suffix}' is not allowed.",
            )
        expected_mime = EXTENSION_MIME_MAP[suffix]
        if expected_mime != detected_mime:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=(
                    f"Extension '{suffix}' does not match detected MIME type '{detected_mime}'."
                ),
            )

    def validate_polyglot(self, content: bytes) -> None:
        """
        Raise HTTP 415 if the file simultaneously matches magic byte signatures
        of two or more distinct MIME types.
        """
        probe = content[: self._MIME_PROBE_BYTES]
        matches = [mime for mime, sig in _MIME_SIGNATURES if probe.startswith(sig)]
        if len(matches) > 1:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"Polyglot file detected: matches signatures for {matches}",
            )

    def validate_csv_content(self, content: bytes) -> None:
        """
        For CSV files: decode as UTF-8 and reject if null bytes or
        non-printable characters (except common whitespace) are present.
        """
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="CSV file contains invalid characters.",
            )
        for ch in text:
            code = ord(ch)
            # Allow printable ASCII, tab (9), newline (10), carriage return (13)
            if code == 0 or (code < 32 and code not in (9, 10, 13)):
                raise HTTPException(
                    status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                    detail="CSV file contains invalid characters.",
                )

    async def validate(
        self,
        file: UploadFile,
        filename: str,
        ip: str,
    ) -> bytes:
        """
        Orchestrates all validations and logs every rejection.
        Returns the file content bytes to avoid double-reading by the caller.
        """
        content = await file.read()
        size = len(content)
        declared_mime: str | None = file.content_type
        detected_mime: str = _detect_mime(content[: self._MIME_PROBE_BYTES])

        def _log_rejection(reason: str, status_code: int) -> None:
            logger.warning(
                "File rejected",
                extra={
                    "ip": ip,
                    "filename": filename,
                    "detected_mime": detected_mime,
                    "declared_mime": declared_mime,
                    "reason": reason,
                    "status": status_code,
                },
            )

        # 1. Empty file
        try:
            self.validate_not_empty(content)
        except HTTPException as exc:
            _log_rejection(exc.detail, exc.status_code)
            raise

        # 2. Size
        try:
            self.validate_size(size)
        except HTTPException as exc:
            _log_rejection(exc.detail, exc.status_code)
            raise

        # 3. MIME type (allowlist + declared vs detected)
        try:
            self.validate_mime(content, declared_mime)
        except HTTPException as exc:
            _log_rejection(exc.detail, exc.status_code)
            raise

        # 4. Extension / MIME canonical map
        try:
            self.validate_extension(filename, detected_mime)
        except HTTPException as exc:
            _log_rejection(exc.detail, exc.status_code)
            raise

        # 5. Polyglot detection
        try:
            self.validate_polyglot(content)
        except HTTPException as exc:
            _log_rejection(exc.detail, exc.status_code)
            raise

        # 6. CSV content check
        if detected_mime == "text/csv":
            try:
                self.validate_csv_content(content)
            except HTTPException as exc:
                _log_rejection(exc.detail, exc.status_code)
                raise

        # 7. Filename path traversal (keep existing)
        try:
            self.validate_filename(filename)
        except HTTPException as exc:
            _log_rejection(exc.detail, exc.status_code)
            raise

        return content


# Instance partagée (singleton léger)
file_validator = FileValidator()
