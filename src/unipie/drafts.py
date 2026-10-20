"""Per-session, atomic crash drafts with strict versioned validation."""

import json
import os
import uuid
from pathlib import Path

from unipie.document import Document
from unipie.formats import atomic_json


def draft_directory() -> Path:
    """Return a user-specific application state directory."""
    if os.name == "nt":
        return (
            Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
            / "UniPie"
            / "drafts"
        )
    return (
        Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
        / "unipie"
        / "drafts"
    )


class DraftStore:
    """Keep one uniquely named draft per process without replacing other sessions."""

    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory if directory is not None else draft_directory()
        self.path = self.directory / f"{uuid.uuid4().hex}.json"

    def write(self, document: Document) -> None:
        """Persist the current document and its last saved baseline atomically."""
        if not document.dirty:
            self.clear()
            return
        self.directory.mkdir(parents=True, exist_ok=True)
        atomic_json(
            self.path,
            {
                "format": "unipie-draft",
                "version": 1,
                "glyphs": document.records,
                "saved": document.saved,
                "active": document.active,
                "path": str(document.path) if document.path else None,
                "digest": document.digest,
            },
        )

    def clear(self) -> None:
        """Discard only the draft owned by this session."""
        self.path.unlink(missing_ok=True)

    def candidates(self) -> list[Path]:
        """Return prior session drafts, newest first, leaving them untouched."""
        return sorted(
            (path for path in self.directory.glob("*.json") if path != self.path),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )


def read_draft(path: Path) -> Document:
    """Recover a valid draft, refusing unsupported or malformed data."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("format") != "unipie-draft":
        raise ValueError("Not a UniPie draft.")
    if type(payload.get("version")) is not int or payload["version"] != 1:
        raise ValueError("Unsupported draft version.")
    from unipie.document import validate_records

    document = Document(validate_records(payload.get("glyphs")))
    saved = validate_records(payload.get("saved"))
    source, digest = payload.get("path"), payload.get("digest")
    if source is not None and (not isinstance(source, str) or not Path(source).is_absolute()):
        raise ValueError("Draft source must be an absolute path.")
    if (source is None) != (digest is None):
        raise ValueError("A draft source and saved fingerprint must appear together.")
    if digest is not None and (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(c not in "0123456789abcdef" for c in digest)
    ):
        raise ValueError("Invalid saved file fingerprint.")
    active = payload.get("active")
    if active is not None:
        if not isinstance(active, str):
            raise ValueError("Invalid active glyph.")
        document.select(active)
    elif document.records:
        raise ValueError("Draft has no active glyph.")
    document.restore_baseline(saved, Path(source) if source else None, digest)
    return document
