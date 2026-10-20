"""Textual application coordinating document, file, and editor workflows."""

from collections.abc import Callable
from contextlib import suppress
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Footer, Header, Input, Label, OptionList, Select, Static
from textual.widgets.option_list import Option
from unifont_utils import Glyph

from unipie.canvas import TOOLS, Canvas
from unipie.dialogs import Confirm, Form, Unsaved
from unipie.document import Document, normalize_code_point
from unipie.drafts import DraftStore, read_draft
from unipie.formats import export_image, export_library, import_image, open_document, read_library


class UniPie(App):
    """A terminal glyph editor with a searchable library and crash-safe drafts."""

    TITLE = "UniPie"
    CSS_PATH = "app.tcss"
    BINDINGS = [
        Binding("ctrl+q,ctrl+c", "quit", "Quit", priority=True),
        Binding("ctrl+s", "save", "Save"),
        Binding("ctrl+shift+s", "save_as", "Save as", show=False),
        Binding("ctrl+o", "open", "Open"),
        Binding("ctrl+i", "import_file", "Import", show=False),
        Binding("ctrl+e", "export", "Export", show=False),
        Binding("ctrl+n", "add", "Add", show=False),
        Binding("ctrl+d", "duplicate", "Duplicate", show=False),
        Binding("ctrl+z", "undo", "Undo"),
        Binding("ctrl+y", "redo", "Redo"),
        Binding("f1", "help", "Help"),
        Binding("f8", "theme", "Theme", show=False),
        Binding("ctrl+pageup", "previous_glyph", "Previous glyph", show=False),
        Binding("ctrl+pagedown", "next_glyph", "Next glyph", show=False),
    ]

    def __init__(self, document: Document, *, draft_dir: Path | None = None) -> None:
        super().__init__()
        self.document = document
        self.drafts = DraftStore(draft_dir)
        self.canvas = Canvas(document)
        self.matches: list[str] = []
        self.library_page = 0
        self._list_updating = False
        self._clean_exit = False
        self._recovering = True
        self._last_draft_revision = -1
        self._draft_error = ""
        self._search_timer = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="workspace"):
            with Vertical(id="library"):
                yield Input(placeholder="Code / character / name / hex", id="search")
                yield OptionList(id="glyphs")
                yield Label("", id="library-count")
                with Horizontal(classes="buttons"):
                    yield Button("‹", id="page-prev")
                    yield Button("›", id="page-next")
            with VerticalScroll(id="editor"):
                yield Static("", id="details", markup=False)
                yield Select(
                    [(f"{index + 1}  {tool.title()}", tool) for index, tool in enumerate(TOOLS)],
                    value="pencil",
                    allow_blank=False,
                    id="tool",
                )
                yield self.canvas
                yield Static(
                    "Arrows/WASD move · Space draws · Shapes: two endpoints\n"
                    "Y copy · X cut · V paste · Del clear · Ctrl+arrows shift",
                    id="hints",
                )
                with Horizontal(classes="buttons"):
                    yield Button("Invert", id="invert")
                    yield Button("Flip H", id="flip-h")
                    yield Button("Flip V", id="flip-v")
                with Horizontal(classes="buttons"):
                    yield Button("Clear", id="clear")
                    yield Button("8 ↔ 16", id="width")
                    yield Button("Patterns", id="patterns")
                with Horizontal(classes="buttons"):
                    yield Button("Add", id="add")
                    yield Button("Duplicate", id="duplicate")
                    yield Button("Delete", id="delete-glyph")
                with Horizontal(classes="buttons"):
                    yield Button("Open", id="open")
                    yield Button("Import", id="import")
                    yield Button("Export", id="export")
                yield Static("", id="hex", markup=False)
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_document(library=True)
        self.canvas.focus()
        self.set_interval(2, self.autosave)
        try:
            candidates = self.drafts.candidates()
        except OSError as exc:
            self.notify(f"Cannot inspect crash drafts: {exc}", severity="error")
            candidates = []
        if candidates:
            self.push_screen(
                Form(
                    "Previous session drafts",
                    [
                        ("draft", "Choose a draft", [str(path) for path in candidates]),
                        (
                            "choice",
                            "Action",
                            ["Restore", "Keep for later", "Discard selected draft"],
                        ),
                    ],
                ),
                self._recover,
            )
        else:
            self._recovering = False

    def _recover(self, values: dict | None) -> None:
        self._recovering = False
        if not values or values["choice"] == "Keep for later":
            return
        path = Path(values["draft"])
        try:
            if values["choice"] == "Restore":
                recovered = read_draft(path)
                # Write our own copy before retiring the recovered file.
                self.drafts.write(recovered)
                self.document = recovered
                self.canvas.document = recovered
                self.canvas.reset()
                self.refresh_document(library=True)
                self.notify("Draft restored. Undo history starts with this recovered snapshot.")
            path.unlink(missing_ok=True)
        except (OSError, ValueError) as exc:
            self.notify(f"Draft kept: {exc}", severity="error", timeout=10)

    def autosave(self) -> None:
        """Persist dirty work every two seconds; keep editing on storage failure."""
        if self._recovering or self._clean_exit:
            return
        try:
            if self.document.dirty:
                if self.document.revision != self._last_draft_revision:
                    self.drafts.write(self.document)
                    self._last_draft_revision = self.document.revision
            else:
                self.drafts.clear()
                self._last_draft_revision = -1
            self._draft_error = ""
        except OSError as exc:
            if str(exc) != self._draft_error:
                self.notify(f"Draft autosave failed: {exc}", severity="error", timeout=10)
                self._draft_error = str(exc)

    def on_unmount(self) -> None:
        if not self._clean_exit and not self._recovering:
            # A forced shutdown still gets a final attempt to preserve work.
            with suppress(OSError):
                self.drafts.write(self.document)

    def refresh_document(self, *, library: bool = False) -> None:
        """Refresh presentation without changing authoritative document state."""
        self.sub_title = f"{'● ' if self.document.dirty else ''}{self.document.path or 'Untitled'}"
        glyph = self.document.glyph
        self.canvas.styles.width = glyph.width * 2 + 3 if glyph else 38
        self.query_one("#details", Static).update(
            f"U+{glyph.code_point} · {glyph.width}×16\n{glyph.unicode_name or 'Unnamed character'}"
            if glyph
            else "Empty glyph library"
        )
        self.query_one("#hex", Static).update(
            f"{glyph.code_point}:{glyph.hex_str}" if glyph else ""
        )
        self.canvas.refresh()
        if library or self.query_one("#search", Input).value:
            self.refresh_library()

    def refresh_library(self) -> None:
        """Render at most 100 results, even when a complete Unifont is loaded."""
        self.matches = self.document.search(self.query_one("#search", Input).value)
        self.library_page = min(self.library_page, max(0, (len(self.matches) - 1) // 100))
        start = self.library_page * 100
        listing = self.query_one("#glyphs", OptionList)
        self._list_updating = True
        listing.clear_options()
        records = self.document.records
        for cp in self.matches[start : start + 100]:
            glyph = Glyph.init_from_hex(cp, records[cp])
            listing.add_option(Option(f"U+{cp} {glyph.unicode_name or 'Unnamed'}", id=cp))
        if self.document.active in self.matches[start : start + 100]:
            listing.highlighted = self.matches[start : start + 100].index(self.document.active)
        self._list_updating = False
        total = len(self.matches)
        self.query_one("#library-count", Label).update(
            f"{min(start + 1, total)}–{min(start + 100, total)} / {total}"
        )

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "search":
            self.library_page = 0
            if self._search_timer:
                self._search_timer.stop()
            self._search_timer = self.set_timer(0.2, self.refresh_library)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id == "glyphs" and not self._list_updating and event.option.id:
            self.document.select(event.option.id)
            self.canvas.reset()
            self.canvas.focus()
            self.refresh_document()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "tool" and event.value in TOOLS:
            self.canvas.action_cancel()
            self.canvas.tool = str(event.value)
            self.canvas.focus()

    def on_canvas_changed(self) -> None:
        self.refresh_document()

    def on_canvas_tool_changed(self, event: Canvas.ToolChanged) -> None:
        self.query_one("#tool", Select).value = event.tool

    def _navigate(self, delta: int) -> None:
        if self.matches:
            index = (
                self.matches.index(self.document.active)
                if self.document.active in self.matches
                else 0
            )
            index = (index + delta) % len(self.matches)
            self.document.select(self.matches[index])
            self.library_page = index // 100
            self.canvas.reset()
            self.refresh_document(library=True)

    def action_previous_glyph(self) -> None:
        self._navigate(-1)

    def action_next_glyph(self) -> None:
        self._navigate(1)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button = event.button.id
        transforms = {
            "invert": "invert",
            "flip-h": "flip horizontal",
            "flip-v": "flip vertical",
            "clear": "clear",
            "width": "width",
        }
        if button in transforms:
            if button in {"clear", "width"}:
                self.push_screen(
                    Confirm("This changes the active bitmap. Continue?", "Apply"),
                    lambda yes: self.canvas.action_transform(transforms[button]) if yes else None,
                )
            else:
                self.canvas.action_transform(transforms[button])
            self.canvas.focus()
        elif button in {"page-prev", "page-next"}:
            self.library_page = max(0, self.library_page + (1 if button == "page-next" else -1))
            self.refresh_library()
        else:
            actions = {
                "add": self.action_add,
                "duplicate": self.action_duplicate,
                "delete-glyph": self.action_delete_glyph,
                "open": self.action_open,
                "import": self.action_import_file,
                "export": self.action_export,
                "patterns": self.action_patterns,
            }
            if button in actions:
                actions[button]()

    def _attempt(self, operation: Callable[[], None]) -> bool:
        try:
            operation()
        except (OSError, ValueError, KeyError) as exc:
            self.notify(str(exc), severity="error", timeout=10)
            return False
        return True

    def _guard(self, continuation: Callable[[], None]) -> None:
        self.canvas.action_cancel()
        if self.document.dirty:

            def decided(choice: str) -> None:
                if choice == "save":
                    self.save_document(then=continuation)
                elif choice == "discard":
                    continuation()

            self.push_screen(Unsaved(), decided)
        else:
            continuation()

    def action_save(self) -> None:
        self.save_document()

    def action_save_as(self) -> None:
        self.save_document(save_as=True)

    def save_document(
        self, *, save_as: bool = False, then: Callable[[], None] | None = None
    ) -> None:
        """Save successfully before invoking any navigation or quit continuation."""
        self.canvas.action_cancel()

        def save(path: Path, overwrite: bool = False) -> None:
            try:
                if path.suffix.lower() != ".hex":
                    raise ValueError("Working documents must be saved with a .hex extension.")
                self.document.save(path, overwrite=overwrite)
            except FileExistsError as exc:
                self.push_screen(
                    Confirm(str(exc), "Overwrite"), lambda yes: save(path, True) if yes else None
                )
                return
            except (OSError, ValueError) as exc:
                self.notify(f"Save failed: {exc}", severity="error", timeout=10)
                return
            self.autosave()
            self.refresh_document()
            self.notify(f"Saved {self.document.path}")
            if then:
                then()

        if self.document.path and not save_as:
            save(self.document.path)
        else:
            self.push_screen(
                Form(
                    "Save library",
                    [
                        (
                            "path",
                            "Hex file path",
                            str(self.document.path or Path.cwd() / "untitled.hex"),
                        )
                    ],
                ),
                lambda values: (
                    save(Path(values["path"]).expanduser().resolve()) if values else None
                ),
            )

    def action_open(self) -> None:
        def prompt() -> None:
            self.push_screen(
                Form("Open library", [("path", "Hex or JSON file path", str(Path.cwd()) + "/")]),
                self._open,
            )

        self._guard(prompt)

    def _open(self, values: dict | None) -> None:
        if not values:
            return

        def load() -> None:
            document = open_document(Path(values["path"]))
            self.drafts.clear()
            self.document = document
            self.canvas.document = document
            self._last_draft_revision = -1
            self.canvas.reset()
            self.query_one("#search", Input).value = ""
            self.library_page = 0
            self.refresh_document(library=True)
            self.canvas.focus()

        self._attempt(load)

    def _add(self, duplicate: bool) -> None:
        if duplicate and self.document.glyph is None:
            return

        def add(values: dict | None) -> None:
            if values and self._attempt(
                lambda: self.document.add(values["code"], int(values["width"]), duplicate=duplicate)
            ):
                self.canvas.reset()
                self.refresh_document(library=True)
                self.canvas.focus()

        self.push_screen(
            Form(
                "Duplicate glyph" if duplicate else "Add glyph",
                [
                    ("code", "New code point (hex, U+hex, or character)", "0042"),
                    ("width", "Width (duplicate retains original width)", ["16", "8"]),
                ],
            ),
            add,
        )

    def action_add(self) -> None:
        self._add(False)

    def action_duplicate(self) -> None:
        self._add(True)

    def action_delete_glyph(self) -> None:
        self.canvas.action_cancel()
        if not self.document.records:
            return
        self.refresh_library()

        def choose(values: dict | None) -> None:
            if not values:
                return
            codes = [self.document.active] if values["scope"] == "active" else self.matches.copy()
            codes = [cp for cp in codes if cp is not None]
            if not codes:
                return

            def delete(yes: bool) -> None:
                if yes:
                    self.document.delete(codes)
                    self.canvas.reset()
                    self.refresh_document(library=True)

            self.push_screen(
                Confirm(f"Delete {len(codes)} glyph(s)? Undo restores the entire batch.", "Delete"),
                delete,
            )

        self.push_screen(
            Form("Delete glyphs", [("scope", "Delete scope", ["active", "filtered"])]), choose
        )

    def action_import_file(self) -> None:
        self.canvas.action_cancel()
        self.push_screen(
            Form(
                "Import library or image",
                [
                    ("path", "File path (.hex / .json / image)", str(Path.cwd()) + "/"),
                    ("policy", "Library conflicts", ["error", "skip", "replace"]),
                    ("code", "Image target code point", self.document.active or "0041"),
                    (
                        "width",
                        "Image width",
                        ["8", "16"]
                        if self.document.glyph and self.document.glyph.width == 8
                        else ["16", "8"],
                    ),
                    ("threshold", "Image threshold (0–255)", "128"),
                    ("mode", "Image sizing", ["fit", "crop"]),
                    ("invert-image", "Invert image pixels", False),
                ],
            ),
            self._import,
        )

    def _import(self, values: dict | None) -> None:
        if not values:
            return

        def load() -> None:
            path = Path(values["path"]).expanduser()
            if path.suffix.lower() in {".hex", ".json"}:
                records = read_library(path)
            else:
                records = {
                    normalize_code_point(values["code"]): import_image(
                        path,
                        int(values["width"]),
                        int(values["threshold"]),
                        mode=values["mode"],
                        invert=values["invert-image"],
                    )
                }

            def merge() -> None:
                self.document.merge(records, values["policy"])
                self.canvas.reset()
                self.refresh_document(library=True)
                self.notify(
                    f"Imported {len(records)} record(s), conflict policy: {values['policy']}."
                )

            conflicts = records.keys() & self.document.records.keys()
            if conflicts and values["policy"] == "replace":
                self.push_screen(
                    Confirm(
                        f"Replace {len(conflicts)} glyph(s)? Undo restores the whole import.",
                        "Replace",
                    ),
                    lambda yes: self._attempt(merge) if yes else None,
                )
            else:
                merge()

        self._attempt(load)

    def action_export(self) -> None:
        self.canvas.action_cancel()
        self.refresh_library()
        self.push_screen(
            Form(
                "Export",
                [
                    (
                        "path",
                        "Output path (.hex / .json / .png / .bmp / .svg)",
                        str(Path.cwd() / "export.hex"),
                    ),
                    (
                        "scope",
                        "Library scope (images always use active glyph)",
                        ["all", "active", "filtered"],
                    ),
                    ("scale", "Image scale (1–64)", "8"),
                    ("transparent", "Transparent background (PNG / SVG)", True),
                ],
            ),
            self._export,
        )

    def _export(self, values: dict | None) -> None:
        if not values:
            return
        path = Path(values["path"]).expanduser().resolve()

        def write() -> None:
            if path == self.document.path:
                raise ValueError("Use Save to write the working library.")
            if path.suffix.lower() in {".hex", ".json"}:
                records = self.document.records
                if values["scope"] != "all":
                    codes = [self.document.active] if values["scope"] == "active" else self.matches
                    records = {cp: records[cp] for cp in codes if cp in records}
                export_library(path, records)
            else:
                glyph = self.document.glyph
                if glyph is None:
                    raise ValueError("Select a glyph before exporting an image.")
                export_image(
                    path, glyph.data, glyph.width, int(values["scale"]), values["transparent"]
                )
            self.notify(f"Exported {path}")

        if path.exists():
            self.push_screen(
                Confirm(f"Overwrite {path}?", "Overwrite"),
                lambda yes: self._attempt(write) if yes else None,
            )
        else:
            self._attempt(write)

    def action_undo(self) -> None:
        self.canvas.action_cancel()
        self.document.undo()
        self.canvas.reset()
        self.refresh_document(library=True)

    def action_redo(self) -> None:
        self.canvas.action_cancel()
        self.document.redo()
        self.canvas.reset()
        self.refresh_document(library=True)

    def action_patterns(self) -> None:
        from unipie.patterns import PatternScreen

        glyph = self.document.glyph
        if glyph:
            self.canvas.action_cancel()

            def applied(bitmap: str | None) -> None:
                if bitmap is not None:
                    self.document.commit({glyph.code_point: bitmap})
                    self.refresh_document()

            self.push_screen(PatternScreen(glyph), applied)

    def action_theme(self) -> None:
        self.theme = "textual-light" if self.theme == "textual-dark" else "textual-dark"

    def action_help(self) -> None:
        self.push_screen(
            Confirm(
                "UniPie keyboard and mouse\n\n"
                "Tab / Shift+Tab: focus controls; Enter: activate\n"
                "Canvas: arrows/WASD move; Space toggles/draws\n"
                "1–7: pencil, eraser, fill, line, rectangle, solid, select\n"
                "Line/rectangle/selection: Space at each endpoint\n"
                "Left drag: draw; right drag or Ctrl+left: erase\n"
                "Y / X / V: copy / cut / paste internal pixel selection\n"
                "Delete: clear selection or cursor pixel; Escape: cancel\n"
                "Ctrl+arrows: shift bitmap (edge pixels are discarded)\n"
                "Ctrl+N/D: add/duplicate; Ctrl+I/E: import/export\n"
                "Ctrl+PageUp/PageDown: previous/next filtered glyph\n"
                "Ctrl+S: save; Ctrl+Shift+S: save as; Ctrl+O: open\n"
                "Ctrl+Z/Y: undo/redo; F8: theme; Ctrl+Q/C: quit\n\n"
                "Drafts autosave every 2 seconds and can be restored at startup.\n"
                "Image/JSON export does not mark the working library as saved.",
                "Close",
            )
        )

    def action_quit(self) -> None:
        if len(self.screen_stack) > 1:
            return

        def finish() -> None:
            if self._attempt(self.drafts.clear):
                self._clean_exit = True
                self.exit()

        self._guard(finish)
