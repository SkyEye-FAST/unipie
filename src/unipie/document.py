"""Validated glyph documents with bounded, atomic edit history."""

import hashlib
from dataclasses import dataclass
from pathlib import Path

from unifont_utils import Converter, Glyph, GlyphSet


def normalize_code_point(value: str) -> str:
    """Accept a hexadecimal scalar value or a literal Unicode character."""
    value = value.strip()
    if len(value) == 1 and value.upper() not in "0123456789ABCDEF":
        number = ord(value)
    else:
        digits = value.removeprefix("U+").removeprefix("u+")
        if not 1 <= len(digits) <= 6 or any(c not in "0123456789abcdefABCDEF" for c in digits):
            raise ValueError("Use 1–6 hexadecimal digits, U+hex, or a single character.")
        number = int(digits, 16)
    if not 0 <= number <= 0x10FFFF or 0xD800 <= number <= 0xDFFF:
        raise ValueError("Code point must be a Unicode scalar value.")
    return f"{number:04X}"


def validate_records(records: object) -> dict[str, str]:
    """Validate a glyph mapping without silently accepting invalid records."""
    if not isinstance(records, dict):
        raise ValueError("Glyphs must be a mapping of code points to hexadecimal bitmaps.")
    result: dict[str, str] = {}
    for code, bitmap in records.items():
        if not isinstance(code, str) or not isinstance(bitmap, str):
            raise ValueError("Code points and bitmaps must be strings.")
        if len(bitmap) not in {32, 64}:
            raise ValueError("Glyph bitmaps must contain 32 or 64 hexadecimal digits.")
        cp = normalize_code_point(code)
        if cp in result:
            raise ValueError(f"Duplicate code point: U+{cp}")
        result[cp] = Glyph.init_from_hex(cp, bitmap).hex_str
    return result


def file_digest(path: Path) -> str:
    """Fingerprint a file so saving can detect external changes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class Edit:
    """One document change, storing only the glyphs affected by that change."""

    before: dict[str, str | None]
    after: dict[str, str | None]
    before_active: str | None
    after_active: str | None


class Document:
    """Own the glyph library, saved snapshot, selection, and undo/redo history."""

    history_limit = 100

    def __init__(self, records: dict[str, str] | None = None) -> None:
        self._records = validate_records(records or {})
        self._saved = self._records.copy()
        self.active = next(iter(self._records), None)
        self.path: Path | None = None
        self.digest: str | None = None
        self._undo: list[Edit] = []
        self._redo: list[Edit] = []
        self.revision = 0

    @property
    def records(self) -> dict[str, str]:
        """Return a detached snapshot of the current library."""
        return self._records.copy()

    @property
    def saved(self) -> dict[str, str]:
        """Return the last successfully saved snapshot."""
        return self._saved.copy()

    @property
    def dirty(self) -> bool:
        """Whether document contents differ from the saved snapshot."""
        return self._records != self._saved

    @property
    def glyph(self) -> Glyph | None:
        """Return a detached active glyph; mutations require an explicit commit."""
        if self.active is None:
            return None
        return Glyph.init_from_hex(self.active, self._records[self.active])

    def select(self, code: str) -> None:
        """Select an existing glyph without creating a history entry."""
        code = normalize_code_point(code)
        if code not in self._records:
            raise ValueError(f"Glyph U+{code} does not exist.")
        self.active = code

    def commit(self, changes: dict[str, str | None], active: str | None = None) -> None:
        """Validate and apply a group of glyph changes as one undoable operation."""
        normalized: dict[str, str | None] = {}
        for code, bitmap in changes.items():
            cp = normalize_code_point(code)
            normalized[cp] = None if bitmap is None else validate_records({cp: bitmap})[cp]
        changes = {cp: value for cp, value in normalized.items() if self._records.get(cp) != value}
        if not changes:
            return
        if active is not None:
            active = normalize_code_point(active)
            if changes.get(active, self._records.get(active)) is None:
                raise ValueError("The requested active glyph does not exist.")
        before = {cp: self._records.get(cp) for cp in changes}
        old_active = self.active
        self._apply(changes)
        self.active = active or (old_active if old_active in self._records else None)
        if self.active is None:
            self.active = next(iter(self._records), None)
        self._undo.append(Edit(before, changes, old_active, self.active))
        del self._undo[: -self.history_limit]
        self._redo.clear()

    def _apply(self, changes: dict[str, str | None]) -> None:
        for code, bitmap in changes.items():
            if bitmap is None:
                self._records.pop(code, None)
            else:
                self._records[code] = bitmap
        self.revision += 1

    def set_pixels(self, pixels: list[int]) -> None:
        """Commit the active bitmap, including any width change."""
        if len(pixels) not in {128, 256}:
            raise ValueError("Glyphs must contain 128 or 256 binary pixels.")
        if self.active is not None:
            self.commit({self.active: Converter.to_hex(pixels)})

    def add(self, code: str, width: int = 16, *, duplicate: bool = False) -> None:
        """Create a blank glyph or duplicate the active glyph to a new code point."""
        cp = normalize_code_point(code)
        if cp in self._records:
            raise ValueError(f"Glyph U+{cp} already exists.")
        if width not in {8, 16}:
            raise ValueError("Glyph width must be 8 or 16.")
        bitmap = self._records[self.active] if duplicate and self.active else "0" * (width * 4)
        self.commit({cp: bitmap}, cp)

    def delete(self, codes: list[str]) -> None:
        """Delete glyphs atomically; undo restores the complete batch."""
        self.commit({normalize_code_point(cp): None for cp in codes})

    def merge(self, records: dict[str, str], policy: str = "error") -> None:
        """Import a validated library using an explicit duplicate policy."""
        records = validate_records(records)
        if policy not in {"error", "skip", "replace"}:
            raise ValueError("Conflict policy must be error, skip, or replace.")
        conflicts = self._records.keys() & records.keys()
        if conflicts and policy == "error":
            raise ValueError(f"Import conflicts with {len(conflicts)} existing glyph(s).")
        changes = {
            cp: data for cp, data in records.items() if policy != "skip" or cp not in conflicts
        }
        self.commit(changes)

    def undo(self) -> None:
        """Undo a logical operation and restore its active glyph."""
        if self._undo:
            edit = self._undo.pop()
            self._apply(edit.before)
            self.active = edit.before_active
            self._redo.append(edit)

    def redo(self) -> None:
        """Redo the most recently undone logical operation."""
        if self._redo:
            edit = self._redo.pop()
            self._apply(edit.after)
            self.active = edit.after_active
            self._undo.append(edit)

    def search(self, query: str) -> list[str]:
        """Search code points, characters, bitmap data, and Unicode names."""
        query = query.strip().upper()
        if not query:
            return sorted(self._records, key=lambda value: int(value, 16))
        result = []
        for cp in sorted(self._records, key=lambda value: int(value, 16)):
            glyph = Glyph.init_from_hex(cp, self._records[cp])
            if not query or any(
                query in value.upper()
                for value in (f"U+{cp}", glyph.character, glyph.unicode_name, glyph.hex_str)
            ):
                result.append(cp)
        return result

    def save(self, path: Path, *, overwrite: bool = False) -> None:
        """Atomically save a hex library, guarding existing or externally changed files."""
        path = path.expanduser().resolve()
        if path.suffix.lower() != ".hex":
            raise ValueError("Working documents must use the .hex extension.")
        if (
            path.exists()
            and not overwrite
            and (path != self.path or file_digest(path) != self.digest)
        ):
            raise FileExistsError(f"{path} exists or changed outside UniPie. Overwrite?")
        glyphs = GlyphSet()
        for cp, bitmap in self._records.items():
            glyphs.add_glyph((cp, bitmap))
        glyphs.save_hex_file(path)
        digest = file_digest(path)
        self.path, self.digest = path, digest
        self._saved = self._records.copy()

    def restore_baseline(
        self, saved: dict[str, str], path: Path | None, digest: str | None
    ) -> None:
        """Restore a validated saved baseline when recovering a crash draft."""
        self._saved = validate_records(saved)
        self.path, self.digest = path, digest
