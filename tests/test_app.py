import asyncio
from pathlib import Path

import pytest
from textual import events
from textual.widgets import Input, OptionList, Select

from unipie.app import UniPie
from unipie.dialogs import Confirm, Form, Unsaved
from unipie.document import Document
from unipie.drafts import DraftStore
from unipie.formats import open_document
from unipie.patterns import PatternScreen


def test_keyboard_tools_history_selection_and_input_isolation(tmp_path: Path) -> None:
    async def scenario():
        document = Document({"0041": "0" * 32})
        app = UniPie(document, draft_dir=tmp_path)
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.press("4", "space", "right", "right", "down", "down", "space")
            assert sum(document.glyph.data) == 3
            await pilot.press("ctrl+z")
            assert not any(document.glyph.data)
            assert not document.dirty
            await pilot.press("ctrl+y")
            assert sum(document.glyph.data) == 3
            await pilot.press("7", "space", "left", "up", "space", "y", "right", "v")
            assert document.dirty
            app.query_one("#search", Input).focus()
            await pilot.press("s", "p", "a", "c", "e")
            assert app.query_one("#search", Input).value == "space"
            assert app.canvas.tool == "select"
            await pilot.press("ctrl+n")
            assert isinstance(app.screen, Form)
            app.screen.query_one("#code", Input).value = "4E2D"
            await pilot.press("enter")
            assert document.active == "4E2D"
            assert document.glyph.width == 16

    asyncio.run(scenario())


def test_mouse_stroke_is_atomic_and_right_button_erases(tmp_path: Path) -> None:
    async def scenario():
        document = Document({"0041": "0" * 32})
        app = UniPie(document, draft_dir=tmp_path)
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.mouse_down("#canvas", offset=(3, 1))
            await pilot.hover("#canvas", offset=(15, 4))
            await pilot.mouse_up("#canvas", offset=(15, 4))
            assert sum(document.glyph.data) >= 7
            await pilot.press("ctrl+z")
            assert not any(document.glyph.data)
            await pilot.press("ctrl+y")
            for event_class in (events.MouseDown, events.MouseUp):
                app.canvas.post_message(event_class(app.canvas, 3, 1, 0, 0, 3, False, False, False))
                await pilot.pause()
            assert document.glyph.data[0] == 0
            await pilot.press("ctrl+z")
            assert document.glyph.data[0] == 1

    asyncio.run(scenario())


def test_bottom_row_is_mouse_accessible_in_small_terminal(tmp_path: Path) -> None:
    async def scenario():
        document = Document({"0041": "0" * 32})
        app = UniPie(document, draft_dir=tmp_path)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.click("#canvas", offset=(17, 16))
            assert document.glyph.data[-1] == 1

    asyncio.run(scenario())


@pytest.mark.parametrize("size", [(80, 24), (100, 40)])
def test_save_and_cancel_quit_work_at_terminal_sizes(tmp_path: Path, size: tuple[int, int]) -> None:
    async def scenario():
        document = Document()
        document.add("0041", 8)
        target = tmp_path / "saved.hex"
        app = UniPie(document, draft_dir=tmp_path / "drafts")
        async with app.run_test(size=size) as pilot:
            await pilot.press("space", "ctrl+q")
            assert isinstance(app.screen, Unsaved)
            await pilot.click("#cancel")
            assert not app._clean_exit
            await pilot.press("ctrl+s")
            assert isinstance(app.screen, Form)
            app.screen.query_one("#path", Input).value = str(target)
            await pilot.press("enter")
            assert not document.dirty
            assert open_document(target).glyph.data[0] == 1
            assert not app.drafts.path.exists()
            await pilot.press("ctrl+q")
            assert app._clean_exit

    asyncio.run(scenario())


def test_failed_save_cannot_quit_or_clear_dirty_work(tmp_path: Path) -> None:
    async def scenario():
        document = Document()
        document.add("0041")
        app = UniPie(document, draft_dir=tmp_path / "drafts")
        async with app.run_test(size=(100, 40)) as pilot:
            app.autosave()
            assert app.drafts.path.exists()
            await pilot.press("ctrl+q")
            await pilot.click("#save")
            app.screen.query_one("#path", Input).value = str(tmp_path / "missing" / "file.hex")
            await pilot.press("enter")
            assert document.dirty
            assert not app._clean_exit
            assert app.drafts.path.exists()

    asyncio.run(scenario())


def test_recovery_restores_original_draft_before_editing(tmp_path: Path) -> None:
    document = Document()
    document.add("4E2D", 16)
    store = DraftStore(tmp_path)
    store.write(document)

    async def scenario():
        app = UniPie(Document(), draft_dir=tmp_path)
        async with app.run_test(size=(100, 40)) as pilot:
            assert isinstance(app.screen, Form)
            await pilot.click("#ok")
            assert app.document.records == document.records
            assert app.document.dirty
            assert app.drafts.path.exists()
            assert not store.path.exists()

    asyncio.run(scenario())


def test_pattern_preview_cancel_and_commit_are_transactional(tmp_path: Path) -> None:
    async def scenario():
        document = Document({"0041": "F" * 32})
        app = UniPie(document, draft_dir=tmp_path)
        async with app.run_test(size=(100, 50)) as pilot:
            app.action_patterns()
            await pilot.pause()
            assert isinstance(app.screen, PatternScreen)
            app.screen.query_one("#pattern-search", Input).value = "111/111/111"
            app.screen.query_one("#pattern-replacement", Input).value = ".../.0./..."
            await pilot.click("#preview")
            await pilot.click("#apply-one")
            assert document.glyph.hex_str == "F" * 32
            await pilot.click("#cancel")
            assert not document.dirty
            app.action_patterns()
            await pilot.pause()
            app.screen.query_one("#pattern-search", Input).value = "111/111/111"
            app.screen.query_one("#pattern-replacement", Input).value = "000/000/000"
            await pilot.click("#apply-all")
            await pilot.click("#done")
            assert not any(document.glyph.data)
            await pilot.press("ctrl+z")
            assert document.glyph.hex_str == "F" * 32

    asyncio.run(scenario())


def test_library_is_paged_searchable_and_navigable(tmp_path: Path) -> None:
    async def scenario():
        document = Document({f"{cp:04X}": "0" * 32 for cp in range(32, 350)})
        app = UniPie(document, draft_dir=tmp_path)
        async with app.run_test(size=(100, 40)) as pilot:
            assert app.query_one("#glyphs", OptionList).option_count == 100
            await pilot.click("#page-next")
            assert app.library_page == 1
            app.query_one("#search", Input).value = "LATIN CAPITAL LETTER A"
            await pilot.pause(0.3)
            assert "0041" in app.matches
            app.query_one("#glyphs", OptionList).focus()
            await pilot.press("home", "enter")
            assert document.active in app.matches
            assert app.canvas.has_focus
            previous = document.active
            await pilot.press("ctrl+pagedown")
            assert document.active != previous

    asyncio.run(scenario())


def test_import_conflicts_export_and_filtered_batch_deletion(tmp_path: Path) -> None:
    source = tmp_path / "import.hex"
    source.write_text("0041:" + "F" * 32 + "\n0042:" + "0" * 32 + "\n", encoding="utf-8")
    target = tmp_path / "backup.json"

    async def scenario():
        document = Document({"0041": "0" * 32})
        app = UniPie(document, draft_dir=tmp_path / "drafts")
        async with app.run_test(size=(100, 45)) as pilot:
            await pilot.press("space")
            edited = document.records

            async def import_dialog():
                await pilot.press("ctrl+i")
                app.screen.query_one("#path", Input).value = str(source)
                app.screen.query_one("#policy", Select).value = "replace"
                await pilot.press("enter")
                assert isinstance(app.screen, Confirm)

            await import_dialog()
            await pilot.click("#cancel")
            assert document.records == edited
            await import_dialog()
            await pilot.click("#yes")
            assert document.glyph.hex_str == "F" * 32
            assert "0042" in document.records
            await pilot.press("ctrl+z")
            assert document.records == edited
            await pilot.press("ctrl+y", "ctrl+e")
            app.screen.query_one("#path", Input).value = str(target)
            await pilot.press("enter")
            assert open_document(target).records == document.records
            assert document.dirty
            app.query_one("#search", Input).value = "U+0042"
            await pilot.pause(0.3)
            app.action_delete_glyph()
            await pilot.pause()
            app.screen.query_one("#scope", Select).value = "filtered"
            await pilot.click("#ok")
            await pilot.pause()
            await pilot.click("#yes")
            assert "0042" not in document.records
            await pilot.press("ctrl+z")
            assert "0042" in document.records

    asyncio.run(scenario())


def test_overwrite_cancellation_and_open_cancellation_keep_work(tmp_path: Path) -> None:
    target = tmp_path / "source.hex"
    document = Document({"0041": "0" * 32})
    document.save(target)

    async def scenario():
        app = UniPie(document, draft_dir=tmp_path / "drafts")
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.press("space")
            target.write_text("external", encoding="utf-8")
            await pilot.press("ctrl+s")
            assert isinstance(app.screen, Confirm)
            await pilot.click("#cancel")
            assert target.read_text(encoding="utf-8") == "external"
            assert document.dirty
            await pilot.press("ctrl+o")
            assert isinstance(app.screen, Unsaved)
            await pilot.click("#discard")
            assert isinstance(app.screen, Form)
            await pilot.press("escape")
            assert document.glyph.data[0] == 1
            assert document.dirty

    asyncio.run(scenario())
