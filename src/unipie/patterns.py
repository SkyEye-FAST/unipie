"""Transactional search/replace preview using the core pattern API."""

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static
from unifont_utils import Glyph, ReplacePattern, SearchPattern


def parse_pattern(text: str, *, replacement: bool = False) -> SearchPattern | ReplacePattern:
    """Parse slash-separated pattern rows; dots retain pixels in replacements."""
    rows = text.strip().split("/")
    width = len(rows[0])
    allowed = "01." if replacement else "01"
    if any(len(row) != width or any(char not in allowed for char in row) for row in rows):
        raise ValueError(
            "Use equal-width rows of 0/1 separated by /. Replacement dots keep pixels."
        )
    data = [-1 if char == "." else int(char) for row in rows for char in row]
    return (ReplacePattern if replacement else SearchPattern)(data, width, len(rows))


class PatternScreen(ModalScreen[str | None]):
    """Stage replacements on a copy; apply all changes as one undoable edit."""

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, glyph: Glyph) -> None:
        super().__init__()
        self.glyph = glyph
        self.matches: list[tuple[int, int]] = []
        self.index = 0
        self.search: SearchPattern | None = None
        self.replacement: ReplacePattern | None = None
        self.preview_valid = False

    def compose(self) -> ComposeResult:
        with VerticalScroll(classes="dialog"):
            yield Label("Pattern replacement · 3–16 pixels per dimension", classes="heading")
            yield Label("Search: 1 must be set; 0 ignores that pixel (core pattern semantics)")
            yield Input("010/111/010", id="pattern-search")
            yield Label("Replacement: 0 clears, 1 sets, . keeps the original pixel")
            yield Input("000/010/000", id="pattern-replacement")
            yield Static("Choose Preview before applying.", id="pattern-status", markup=False)
            yield Static("", id="pattern-preview")
            with Horizontal(classes="buttons"):
                yield Button("Preview", id="preview")
                yield Button("Previous", id="previous")
                yield Button("Next", id="next")
            with Horizontal(classes="buttons"):
                yield Button("Apply one", id="apply-one")
                yield Button("Apply all", id="apply-all")
            with Horizontal(classes="buttons"):
                yield Button("Done", id="done", variant="primary")
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        self.refresh_preview()

    def on_input_changed(self) -> None:
        self.preview_valid = False
        self.matches = []
        if self.is_mounted:
            self.refresh_preview()

    def _prepare(self) -> None:
        search = parse_pattern(self.query_one("#pattern-search", Input).value)
        replacement = parse_pattern(
            self.query_one("#pattern-replacement", Input).value, replacement=True
        )
        if (search.width, search.height) != (replacement.width, replacement.height):
            raise ValueError("Search and replacement must have equal dimensions.")
        self.search, self.replacement = search, replacement
        self.matches = self.glyph.find_matches(search)
        self.index = 0
        self.preview_valid = True

    def refresh_preview(self) -> None:
        pixels = self.glyph.data
        highlighted: set[int] = set()
        if self.preview_valid and self.matches and self.replacement:
            row, col = self.matches[self.index]
            for y in range(self.replacement.height):
                for x in range(self.replacement.width):
                    index = (row + y) * self.glyph.width + col + x
                    value = self.replacement.data[y * self.replacement.width + x]
                    if value != -1:
                        pixels[index] = value
                    highlighted.add(index)
        text = Text()
        for y in range(16):
            for x in range(self.glyph.width):
                index = y * self.glyph.width + x
                color = "#00b88a" if index in highlighted else "#dce5ed"
                text.append("  ", style=f"on {color if pixels[index] else '#19232d'}")
            if y != 15:
                text.append("\n")
        self.query_one("#pattern-preview", Static).update(text)
        status = (
            f"Match {self.index + 1 if self.matches else 0} / {len(self.matches)}"
            if self.preview_valid
            else "Preview required after changing patterns."
        )
        self.query_one("#pattern-status", Static).update(status)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button = event.button.id
        if button == "cancel":
            self.dismiss(None)
            return
        if button == "done":
            self.dismiss(self.glyph.hex_str)
            return
        try:
            if button == "preview" or not self.preview_valid:
                self._prepare()
            if button in {"previous", "next"} and self.matches:
                self.index = (self.index + (1 if button == "next" else -1)) % len(self.matches)
            elif button in {"apply-one", "apply-all"} and self.matches and self.replacement:
                if button == "apply-one":
                    self.glyph.apply_pattern(*self.matches[self.index], self.replacement)
                else:
                    self.glyph.replace(self.search, self.replacement)
                self.matches = self.glyph.find_matches(self.search)
                self.index = min(self.index, max(0, len(self.matches) - 1))
            self.refresh_preview()
        except ValueError as exc:
            self.preview_valid = False
            self.query_one("#pattern-status", Static).update(str(exc))

    def action_cancel(self) -> None:
        self.dismiss(None)
