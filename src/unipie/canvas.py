"""Keyboard and mouse bitmap editing with one history entry per gesture."""

from rich.text import Text
from textual import events
from textual.binding import Binding
from textual.message import Message
from textual.widgets import Static

from unipie import grid
from unipie.document import Document

TOOLS = ("pencil", "eraser", "fill", "line", "rectangle", "filled rectangle", "select")


class Canvas(Static, can_focus=True):
    """Render a bitmap and keep transient cursor/gesture state outside history."""

    BINDINGS = [
        Binding("up,w", "move(0,-1)", "Up", show=False),
        Binding("down,s", "move(0,1)", "Down", show=False),
        Binding("left,a", "move(-1,0)", "Left", show=False),
        Binding("right,d", "move(1,0)", "Right", show=False),
        Binding("space", "draw", "Draw"),
        Binding("escape", "cancel", "Cancel"),
        Binding("y", "copy", "Copy selection", show=False),
        Binding("x", "cut", "Cut selection", show=False),
        Binding("v", "paste", "Paste", show=False),
        Binding("delete,backspace", "delete", "Clear selection", show=False),
        Binding("ctrl+left", "transform('left')", "Shift left", show=False),
        Binding("ctrl+right", "transform('right')", "Shift right", show=False),
        Binding("ctrl+up", "transform('up')", "Shift up", show=False),
        Binding("ctrl+down", "transform('down')", "Shift down", show=False),
    ]

    class Changed(Message):
        """A complete document edit is ready for the surrounding UI to refresh."""

    class ToolChanged(Message):
        """Request a tool change from a keyboard digit on the canvas."""

        def __init__(self, tool: str) -> None:
            super().__init__()
            self.tool = tool

    def on_key(self, event: events.Key) -> None:
        if len(event.key) == 1 and event.key in "1234567":
            event.stop()
            self.post_message(self.ToolChanged(TOOLS[int(event.key) - 1]))

    def __init__(self, document: Document) -> None:
        super().__init__(id="canvas")
        self.document = document
        self.cursor = (0, 0)
        self.tool = "pencil"
        self.anchor: grid.Point | None = None
        self.selection: grid.Rect | None = None
        self.clipboard: tuple[list[int], int] | None = None
        self.preview: list[int] | None = None
        self._stroke: list[int] | None = None
        self._mouse_tool = "pencil"
        self._value = 1
        self._last = (0, 0)

    def reset(self) -> None:
        """Cancel gestures when switching glyphs or applying history."""
        self.action_cancel()
        glyph = self.document.glyph
        self.cursor = (min(self.cursor[0], glyph.width - 1) if glyph else 0, self.cursor[1])
        self.refresh()

    def render(self) -> Text:
        glyph = self.document.glyph
        if glyph is None:
            return Text("Empty library. Ctrl+N adds a glyph.")
        data = self.preview if self.preview is not None else glyph.data
        text = Text("   " + "".join(f"{x:X} " for x in range(glyph.width)) + "\n", style="#91a1b0")
        rect = (
            grid.bounds(self.anchor, self.cursor)
            if self.anchor and self.tool == "select"
            else self.selection
        )
        for y in range(16):
            text.append(f"{y:X}  ", style="#91a1b0")
            for x in range(glyph.width):
                selected = rect and rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]
                background = "#dce5ed" if data[y * glyph.width + x] else "#19232d"
                foreground = "#00d4a0" if selected else "#ffbb66"
                text.append(
                    "◆ " if self.cursor == (x, y) else "  ", style=f"{foreground} on {background}"
                )
                if selected and self.cursor != (x, y):
                    text.stylize("underline #00d4a0", len(text) - 2, len(text))
            if y != 15:
                text.append("\n")
        return text

    def action_move(self, dx: int, dy: int) -> None:
        """Move the keyboard cursor within the active glyph."""
        glyph = self.document.glyph
        if glyph:
            self.cursor = (
                max(0, min(glyph.width - 1, self.cursor[0] + dx)),
                max(0, min(15, self.cursor[1] + dy)),
            )
            self._update_preview()
            self.refresh()

    def _update_preview(self) -> None:
        glyph = self.document.glyph
        if glyph and self.anchor and self.tool in {"line", "rectangle", "filled rectangle"}:
            self.preview = grid.draw(
                glyph.data, glyph.width, self.tool, self.anchor, self.cursor, 1
            )

    def action_draw(self) -> None:
        """Space toggles a pixel or sets/confirms a shape endpoint."""
        glyph = self.document.glyph
        if glyph is None:
            return
        if self.tool in {"line", "rectangle", "filled rectangle", "select"}:
            if self.anchor is None:
                self.anchor = self.cursor
                self._update_preview()
            else:
                self._finish(self.tool, self.anchor, self.cursor, glyph.data, 1)
        else:
            value = (
                0
                if self.tool == "eraser"
                else 1 - glyph.data[self.cursor[1] * glyph.width + self.cursor[0]]
            )
            self._commit(
                grid.draw(glyph.data, glyph.width, self.tool, self.cursor, self.cursor, value)
            )
        self.refresh()

    def _commit(self, pixels: list[int]) -> None:
        self.document.set_pixels(pixels)
        self.preview = None
        self.post_message(self.Changed())
        self.refresh()

    def _finish(
        self, tool: str, start: grid.Point, end: grid.Point, data: list[int], value: int
    ) -> None:
        glyph = self.document.glyph
        if glyph:
            if tool == "select":
                self.selection = grid.bounds(start, end)
            else:
                self._commit(grid.draw(data, glyph.width, tool, start, end, value))
        self.anchor = None
        self.preview = None

    def action_cancel(self) -> None:
        """Discard transient previews without changing document contents."""
        self.anchor, self.selection, self.preview, self._stroke = None, None, None, None
        self.release_mouse()
        self.refresh()

    def action_transform(self, operation: str) -> None:
        """Apply a glyph transform as one undoable operation."""
        glyph = self.document.glyph
        if glyph:
            self.action_cancel()
            self._commit(grid.transform(glyph.data, glyph.width, operation))
            self.cursor = (min(self.cursor[0], self.document.glyph.width - 1), self.cursor[1])

    def action_copy(self) -> None:
        """Copy the selection, or the entire glyph, to the internal clipboard."""
        glyph = self.document.glyph
        if glyph:
            self.clipboard = grid.extract(
                glyph.data, glyph.width, self.selection or (0, 0, glyph.width - 1, 15)
            )
            self.notify("Copied pixels. Move the cursor and press V to paste.")

    def action_delete(self) -> None:
        """Clear selected pixels, or the pixel at the cursor."""
        glyph = self.document.glyph
        if glyph:
            rect = self.selection or (*self.cursor, *self.cursor)
            pixels, clip_width = grid.extract(glyph.data, glyph.width, rect)
            self._commit(
                grid.paste(glyph.data, glyph.width, [0] * len(pixels), clip_width, rect[:2])
            )

    def action_cut(self) -> None:
        """Copy then clear the selection as one document edit."""
        self.action_copy()
        if self.selection:
            self.action_delete()
        else:
            self.action_transform("clear")

    def action_paste(self) -> None:
        """Paste at the cursor, clipping to the active glyph's dimensions."""
        glyph = self.document.glyph
        if glyph and self.clipboard:
            self._commit(grid.paste(glyph.data, glyph.width, *self.clipboard, self.cursor))

    def _point(self, event: events.MouseEvent) -> grid.Point | None:
        glyph = self.document.glyph
        x, y = int((event.x - 3) // 2), int(event.y - 1)
        return (x, y) if glyph and 0 <= x < glyph.width and 0 <= y < 16 else None

    def on_mouse_down(self, event: events.MouseDown) -> None:
        point, glyph = self._point(event), self.document.glyph
        if point is None or glyph is None or event.button not in {1, 3}:
            return
        event.stop()
        self.focus()
        self.anchor = self.cursor = self._last = point
        self._stroke = glyph.data
        self._mouse_tool = "eraser" if event.button == 3 or event.ctrl else self.tool
        self._value = 0 if self._mouse_tool == "eraser" else 1
        self.capture_mouse()
        self._mouse_preview()

    def _mouse_preview(self) -> None:
        glyph = self.document.glyph
        if glyph is None or self._stroke is None or self.anchor is None:
            return
        if self._mouse_tool in {"pencil", "eraser"}:
            self._stroke = grid.draw(
                self._stroke, glyph.width, self._mouse_tool, self._last, self.cursor, self._value
            )
            self.preview = self._stroke
        elif self._mouse_tool != "select":
            end = self.anchor if self._mouse_tool == "fill" else self.cursor
            self.preview = grid.draw(
                self._stroke, glyph.width, self._mouse_tool, self.anchor, end, self._value
            )
        self._last = self.cursor
        self.refresh()

    def on_mouse_move(self, event: events.MouseMove) -> None:
        point = self._point(event)
        if point is not None:
            self.cursor = point
            if self._stroke is not None:
                self._mouse_preview()
            else:
                self._update_preview()
            self.refresh()

    def on_mouse_up(self, event: events.MouseUp) -> None:
        if self._stroke is None:
            return
        point = self._point(event)
        if point:
            self.cursor = point
            self._mouse_preview()
        if self._mouse_tool == "select" and self.anchor:
            self.selection = grid.bounds(self.anchor, self.cursor)
        elif self.preview is not None:
            self._commit(self.preview)
        self.anchor, self._stroke, self.preview = None, None, None
        self.release_mouse()
        self.refresh()
