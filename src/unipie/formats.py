"""File boundaries for hex libraries, JSON backups, and pixel images."""

import hashlib
import json
import os
import tempfile
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps
from unifont_utils import Converter, GlyphSet

from unipie.document import Document, normalize_code_point, validate_records


def atomic_write(path: Path, data: bytes) -> None:
    """Replace a file atomically, cleaning up failed temporary writes."""
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "wb", dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def atomic_json(path: Path, payload: dict) -> None:
    """Save an application JSON payload using the atomic file boundary."""
    atomic_write(
        path, (json.dumps(payload, ensure_ascii=True, separators=(",", ":")) + "\n").encode("utf-8")
    )


def read_library(path: Path) -> dict[str, str]:
    """Read hex or a versioned JSON backup; reject malformed imports in full."""
    return _parse_library(path.read_bytes(), path.suffix.lower())


def _parse_library(data: bytes, suffix: str) -> dict[str, str]:
    text = data.decode("utf-8-sig")
    if suffix == ".json":
        payload = json.loads(text)
        if not isinstance(payload, dict) or payload.get("format") != "unipie-library":
            raise ValueError("Not a UniPie library backup.")
        if type(payload.get("version")) is not int or payload["version"] != 1:
            raise ValueError("Unsupported library backup version.")
        return validate_records(payload.get("glyphs"))
    if suffix != ".hex":
        raise ValueError("A glyph library must use .hex or .json.")
    records: dict[str, str] = {}
    for number, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            cp, bitmap = line.split(":", 1)
            parsed = validate_records({normalize_code_point(cp): bitmap.strip()})
            if records.keys() & parsed.keys():
                raise ValueError("Duplicate code point.")
            records.update(parsed)
        except ValueError as exc:
            raise ValueError(f"Line {number}: {exc}") from exc
    return records


def open_document(path: Path) -> Document:
    """Open a hex document, retaining its file fingerprint for safe saving."""
    path = path.expanduser().resolve()
    data = path.read_bytes()
    document = Document(_parse_library(data, path.suffix.lower()))
    # JSON is an import/backup format; the working document is always saved as hex.
    if path.suffix.lower() == ".hex":
        document.path, document.digest = path, hashlib.sha256(data).hexdigest()
    else:
        document.restore_baseline({}, None, None)
    return document


def import_image(
    path: Path, width: int, threshold: int = 128, *, mode: str = "fit", invert: bool = False
) -> str:
    """Prepare arbitrary images as crisp 8x16 or 16x16 thresholded bitmaps."""
    if width not in {8, 16} or not 0 <= threshold <= 255 or mode not in {"fit", "crop"}:
        raise ValueError("Use width 8/16, threshold 0..255, and fit/crop mode.")
    with Image.open(path) as source, source.convert("RGBA") as rgba:
        background = Image.new("RGBA", rgba.size, "white")
        try:
            background.alpha_composite(rgba)
            gray = background.convert("L")
            try:
                if mode == "crop":
                    prepared = ImageOps.fit(gray, (width, 16), method=Image.Resampling.NEAREST)
                else:
                    fitted = ImageOps.contain(gray, (width, 16), method=Image.Resampling.NEAREST)
                    prepared = Image.new("L", (width, 16), 255)
                    prepared.paste(fitted, ((width - fitted.width) // 2, (16 - fitted.height) // 2))
                    fitted.close()
                try:
                    data = [
                        int((prepared.getpixel((x, y)) < threshold) != invert)
                        for y in range(16)
                        for x in range(width)
                    ]
                finally:
                    prepared.close()
            finally:
                gray.close()
        finally:
            background.close()
    return Converter.to_hex(data)


def export_library(path: Path, records: dict[str, str]) -> None:
    """Export a complete or scoped library as hex or versioned JSON."""
    records = validate_records(records)
    if path.suffix.lower() == ".json":
        atomic_json(path, {"format": "unipie-library", "version": 1, "glyphs": records})
    elif path.suffix.lower() == ".hex":
        glyphs = GlyphSet()
        for cp, bitmap in records.items():
            glyphs.add_glyph((cp, bitmap))
        glyphs.save_hex_file(path)
    else:
        raise ValueError("Library export requires .hex or .json.")


def export_image(path: Path, data: list[int], width: int, scale: int, transparent: bool) -> None:
    """Export the active glyph as PNG, BMP, or SVG without smoothing."""
    if type(width) is not int or width not in {8, 16} or len(data) != width * 16:
        raise ValueError("Image data must match an 8x16 or 16x16 glyph.")
    if any(type(pixel) is not int or pixel not in {0, 1} for pixel in data):
        raise ValueError("Image pixels must be binary integers.")
    if type(scale) is not int or not 1 <= scale <= 64:
        raise ValueError("Scale must be between 1 and 64.")
    suffix = path.suffix.lower()
    if suffix == ".svg":
        background = "" if transparent else f'<path fill="white" d="M0 0h{width}v16H0z"/>'
        pixels = "".join(
            f"M{x} {y}h1v1h-1z" for y in range(16) for x in range(width) if data[y * width + x]
        )
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width * scale}" '
            f'height="{16 * scale}" viewBox="0 0 {width} 16" shape-rendering="crispEdges">'
            f'{background}<path fill="black" d="{pixels}"/></svg>\n'
        )
        atomic_write(path, svg.encode("utf-8"))
    elif suffix in {".png", ".bmp"}:
        alpha = 0 if transparent and suffix == ".png" else 255
        with Image.new("RGBA", (width, 16)) as image:
            image.putdata([(0, 0, 0, 255) if pixel else (255, 255, 255, alpha) for pixel in data])
            with (
                image.resize((width * scale, 16 * scale), Image.Resampling.NEAREST) as scaled,
                BytesIO() as buffer,
            ):
                scaled.save(buffer, format=suffix[1:].upper())
                atomic_write(path, buffer.getvalue())
    else:
        raise ValueError("Image export requires .png, .bmp, or .svg.")
