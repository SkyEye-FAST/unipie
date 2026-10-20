import json
from pathlib import Path

import pytest
from PIL import Image

from unipie.document import Document
from unipie.drafts import DraftStore, read_draft
from unipie.formats import export_image, export_library, import_image, open_document, read_library


def test_hex_comments_bom_and_strict_line_errors(tmp_path: Path) -> None:
    path = tmp_path / "library.hex"
    path.write_text("\ufeff# Comment\n\nU+41:" + "0" * 32 + "\n", encoding="utf-8")
    assert read_library(path) == {"0041": "0" * 32}
    path.write_text("0041:" + "0" * 32 + "\n0041:" + "F" * 32, encoding="utf-8")
    with pytest.raises(ValueError, match="Line 2: Duplicate"):
        read_library(path)
    path.write_text("invalid line", encoding="utf-8")
    with pytest.raises(ValueError, match="Line 1"):
        read_library(path)


def test_json_backup_is_versioned_and_import_does_not_mark_work_saved(tmp_path: Path) -> None:
    path = tmp_path / "backup.json"
    records = {"0041": "F" * 32, "4E2D": "0" * 64}
    export_library(path, records)
    assert read_library(path) == records
    document = open_document(path)
    assert document.dirty
    assert document.path is None
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["version"] = 2
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="version"):
        read_library(path)


@pytest.mark.parametrize("suffix", ["png", "bmp", "svg"])
def test_scaled_image_exports(tmp_path: Path, suffix: str) -> None:
    path = tmp_path / f"image.{suffix}"
    pixels = [1] + [0] * 127
    export_image(path, pixels, 8, 3, True)
    if suffix == "svg":
        text = path.read_text(encoding="utf-8")
        assert 'viewBox="0 0 8 16"' in text
        assert "M0 0h1v1h-1z" in text
    else:
        with Image.open(path) as image:
            assert image.size == (24, 48)
            assert image.convert("RGBA").getpixel((0, 0)) == (0, 0, 0, 255)
            if suffix == "png":
                assert image.getpixel((23, 47))[3] == 0


def test_image_threshold_transparency_fit_crop_and_invert(tmp_path: Path) -> None:
    path = tmp_path / "source.png"
    with Image.new("RGBA", (32, 16), (0, 0, 0, 0)) as image:
        for y in range(16):
            for x in range(16):
                image.putpixel((x, y), (100, 100, 100, 255))
        image.save(path)
    fit = import_image(path, 16, 128)
    crop = import_image(path, 16, 128, mode="crop")
    assert fit != crop
    assert import_image(path, 16, 50) == "0" * 64
    assert int(import_image(path, 16, 128, invert=True), 16) ^ int(fit, 16) == (1 << 256) - 1


def test_draft_recovers_saved_baseline_widths_and_file_identity(tmp_path: Path) -> None:
    path = tmp_path / "library.hex"
    document = Document({"0041": "0" * 32})
    document.save(path)
    document.add("4E2D", 16)
    document.commit({"0041": "F" * 32})
    store = DraftStore(tmp_path / "drafts")
    store.write(document)
    restored = read_draft(store.path)
    assert restored.records == document.records
    assert restored.saved == document.saved
    assert restored.path == document.path
    assert restored.digest == document.digest
    assert restored.active == "4E2D"
    assert restored.dirty
    other = DraftStore(store.directory)
    assert other.candidates() == [store.path]
    other.clear()
    assert store.path.exists()
    document.save(path)
    store.write(document)
    assert not store.path.exists()


def test_corrupt_draft_is_not_deleted_and_failed_write_preserves_old_draft(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    document = Document()
    document.add("0041", 8)
    store = DraftStore(tmp_path)
    store.write(document)
    original = store.path.read_bytes()

    def fail_replace(*args, **kwargs):
        raise OSError("disk failure")

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(OSError):
        store.write(document)
    assert store.path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [store.path]
    store.path.write_text('{"format":"unipie-draft","version":99}', encoding="utf-8")
    with pytest.raises(ValueError, match="version"):
        read_draft(store.path)
    assert store.path.exists()


@pytest.mark.parametrize("pixels,width", [([0] * 129, 8), ([2] * 128, 8), ([0] * 128, 0)])
def test_invalid_image_export_preserves_existing_file(tmp_path: Path, pixels, width) -> None:
    target = tmp_path / "glyph.png"
    target.write_bytes(b"original")
    with pytest.raises(ValueError):
        export_image(target, pixels, width, 2, False)
    assert target.read_bytes() == b"original"
