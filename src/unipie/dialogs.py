"""Focused modal prompts; editor shortcuts never consume dialog text input."""

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Input, Label, Select


class Confirm(ModalScreen[bool]):
    """Ask before destructive actions or overwriting an existing file."""

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, message: str, accept: str = "Discard") -> None:
        super().__init__()
        self.message, self.accept = message, accept

    def compose(self) -> ComposeResult:
        with VerticalScroll(classes="dialog"):
            yield Label(self.message, markup=False)
            with Horizontal(classes="buttons"):
                yield Button(self.accept, id="yes", variant="warning")
                yield Button("Cancel", id="cancel", variant="primary")

    def on_mount(self) -> None:
        self.query_one("#cancel", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")

    def action_cancel(self) -> None:
        self.dismiss(False)


class Form(ModalScreen[dict[str, str | bool] | None]):
    """Display a small labeled form with typed selectors and checkboxes."""

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(
        self,
        title: str,
        fields: list[tuple[str, str, str | bool | list[str]]],
    ) -> None:
        super().__init__()
        self.heading, self.fields = title, fields

    def compose(self) -> ComposeResult:
        with VerticalScroll(classes="dialog"):
            yield Label(self.heading, classes="heading", markup=False)
            for field_id, label, value in self.fields:
                if isinstance(value, bool):
                    yield Checkbox(label, value=value, id=field_id)
                else:
                    yield Label(label, markup=False)
                    if isinstance(value, list):
                        yield Select(
                            [(item, item) for item in value],
                            value=value[0],
                            allow_blank=False,
                            id=field_id,
                        )
                    else:
                        yield Input(value=value, id=field_id)
            yield Label("", id="error", markup=False)
            with Horizontal(classes="buttons"):
                yield Button("OK", id="ok", variant="primary")
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        self.query("Input, Select, Checkbox").first().focus()

    def submit(self) -> None:
        """Collect values without running file operations inside the modal."""
        values: dict[str, str | bool] = {}
        for field_id, _, initial in self.fields:
            if isinstance(initial, bool):
                values[field_id] = self.query_one(f"#{field_id}", Checkbox).value
            elif isinstance(initial, list):
                values[field_id] = str(self.query_one(f"#{field_id}", Select).value)
            else:
                value = self.query_one(f"#{field_id}", Input).value.strip()
                if not value:
                    self.query_one("#error", Label).update("All text fields are required.")
                    return
                values[field_id] = value
        self.dismiss(values)

    def on_input_submitted(self) -> None:
        self.submit()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "ok":
            self.submit()
        else:
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class Unsaved(ModalScreen[str]):
    """Offer save, discard, or cancel before leaving the current document."""

    BINDINGS = [("escape", "cancel", "Cancel")]

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Label("This library has unsaved changes.")
            with Horizontal(classes="buttons"):
                yield Button("Save", id="save", variant="primary")
                yield Button("Discard", id="discard", variant="warning")
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        self.query_one("#cancel", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id)

    def action_cancel(self) -> None:
        self.dismiss("cancel")
