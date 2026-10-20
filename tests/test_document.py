from pathlib import Path

import pytest

from unipie.document import Document, normalize_code_point, validate_records
from unipie.formats import open_document

BLANK = "0" * 32
FULL = "F" * 32


def test_library_history_is_atomic_and_saved_state_is_content_based(tmp_path: Path) -> None:
    document = Document({"0041": BLANK})
    document.merge({"0041": FULL, "0042": BLANK}, "replace")
    assert document.dirty
    document.undo()
    assert document.records == {"0041": BLANK}
    assert not document.dirty
    document.redo()
    target = tmp_path / "library.hex"
    document.save(target)
    assert not document.dirty
    document.undo()
    assert document.dirty
    document.redo()
    assert not document.dirty
    assert open_document(target).records == document.records


def test_add_delete_undo_and_new_branch_preserve_active_glyph() -> None:
    document = Document({"0041": FULL})
    document.add("U+42", duplicate=True)
    assert document.glyph.hex_str == FULL
    document.delete(["0041", "0042"])
    assert document.glyph is None
    document.undo()
    assert document.active == "0042"
    document.undo()
    assert document.active == "0041"
    document.commit({"0041": BLANK})
    document.redo()
    assert document.records == {"0041": BLANK}


def test_conflict_and_invalid_imports_do_not_partially_mutate() -> None:
    document = Document({"0041": BLANK})
    with pytest.raises(ValueError, match="conflicts"):
        document.merge({"0042": FULL, "0041": FULL})
    assert document.records == {"0041": BLANK}
    with pytest.raises(ValueError):
        document.merge({"0042": FULL, "0043": "broken"}, "replace")
    assert document.records == {"0041": BLANK}
    document.merge({"0041": FULL, "0042": FULL}, "skip")
    assert document.records == {"0041": BLANK, "0042": FULL}
    document.undo()
    assert document.records == {"0041": BLANK}


def test_noop_does_not_destroy_redo_and_exposed_objects_are_detached() -> None:
    document = Document({"0041": BLANK})
    document.commit({"0041": FULL})
    document.undo()
    document.commit({"0041": BLANK})
    document.records["0041"] = FULL
    document.glyph.hex_str = FULL
    assert document.glyph.hex_str == BLANK
    document.redo()
    assert document.glyph.hex_str == FULL


def test_save_detects_external_changes_and_preserves_dirty_on_failure(tmp_path: Path) -> None:
    target = tmp_path / "library.hex"
    document = Document({"0041": BLANK})
    document.save(target)
    document.commit({"0041": FULL})
    target.write_text("external change", encoding="utf-8")
    with pytest.raises(FileExistsError):
        document.save(target)
    assert target.read_text(encoding="utf-8") == "external change"
    assert document.dirty
    with pytest.raises(FileNotFoundError):
        document.save(tmp_path / "missing" / "new.hex")
    assert document.dirty
    document.save(target, overwrite=True)
    assert not document.dirty
    assert open_document(target).glyph.hex_str == FULL


@pytest.mark.parametrize("invalid", ["D800", "110000", "4_1", "-1", "00000041", "U+"])
def test_code_point_validation(invalid: str) -> None:
    with pytest.raises(ValueError):
        normalize_code_point(invalid)


def test_scalar_normalization_search_and_empty_bitmap_rejection() -> None:
    assert normalize_code_point("中") == "4E2D"
    assert normalize_code_point("u+1f600") == "1F600"
    with pytest.raises(ValueError):
        validate_records({"0041": ""})
    document = Document({"0041": FULL, "4E2D": "0" * 64})
    assert document.search("latin capital letter a") == ["0041"]
    assert document.search("中") == ["4E2D"]
    assert document.search("U+0041") == ["0041"]
    assert document.search("FFFF") == ["0041"]


def test_bounded_history_does_not_forget_saved_baseline() -> None:
    document = Document({"0041": BLANK})
    document.history_limit = 2
    document.commit({"0041": FULL})
    document.add("0042", 8)
    document.delete(["0042"])
    for _ in range(3):
        document.undo()
    assert document.records == {"0041": FULL}
    assert document.dirty
