# UniPie

A standalone terminal editor for GNU Unifont, extracted from Unifont Utils.
Inspired by UniCucumber's document history and pixel editing workflow.

Requires Python 3.10 or later and a terminal with color support. Mouse input is optional.

## Local development

```shell
uv sync --locked
uv run --locked unipie
uv run --locked unipie ../unifont_utils/unifont_all-17.0.03.hex
uv run --locked unipie --code-point 0041 --width 8
uv run --locked unipie --code-point 0041 --hex 0000000018242442427E424242420000
```

To test changes to both projects together, use `uv run --with-editable
../unifont_utils unipie` (or replace `unipie` with `pytest`). The sibling core
checkout is optional; the lockfile resolves the released core package from PyPI.
UniPie uses only the public `unifont_utils` API; the core package does not import
UniPie. Install this checkout with `uv tool install .` for a system-level command.

## Features

- 8×16 and 16×16 glyphs, mouse dragging and keyboard editing.
- Pencil, eraser, flood fill, line, outlined/filled rectangle, rectangular selection.
- Internal pixel clipboard, cut/copy/paste, invert, flips, shifts, and width changes.
- Atomic undo/redo for strokes, shapes, imports, and batch deletion (100 edits).
- Search by code point, character, Unicode name, or bitmap; paged glyph browsing.
- Add, duplicate, delete active or filtered glyphs; navigate filtered results.
- Hex and versioned JSON import/export, with explicit error/skip/replace conflicts.
- Image import with fit/crop, threshold, transparency on white, and inversion.
- Single-glyph PNG/BMP/SVG export, 1–64× scaling and PNG/SVG transparency.
- Pattern match/replacement preview, previous/next match, apply one/all, and cancel.
- Dirty-state tracking, Save/Discard/Cancel prompts, atomic library saves, external
  file change detection, and independent crash drafts for each session.
- Light/dark themes. All controls work with Tab, Shift+Tab, and Enter.

## Controls

Use a terminal of at least 80×24 cells; the editor panel and dialogs scroll on short
screens. F1 shows help. Arrow keys/WASD move the canvas cursor; Space toggles a
pixel. For shapes and selections, press Space at each endpoint. Left mouse drag
draws; right drag or Ctrl+left drag erases. Tools 1–7 select pencil, eraser, fill,
line, rectangle, filled rectangle, and selection while the canvas has focus.

| Keys | Action |
| --- | --- |
| Y / X / V | Copy / cut / paste selection (whole glyph if no selection) |
| Delete / Escape | Clear selected pixels or cursor pixel / cancel preview or selection |
| Ctrl+arrows | Shift bitmap; pixels beyond the edges are discarded |
| Ctrl+Z / Ctrl+Y | Undo / redo |
| Ctrl+N / Ctrl+D | Add / duplicate glyph |
| Ctrl+PageUp / Ctrl+PageDown | Previous / next filtered glyph |
| Ctrl+O / Ctrl+I / Ctrl+E | Open / import / export |
| Ctrl+S / Ctrl+Shift+S | Save / save as |
| F8 / Ctrl+Q | Change theme / quit |

Code points accept 1–6 hex digits, `U+hex`, or a non-hex character such as `中`.
Hex characters `A`–`F` and digits are interpreted as hexadecimal numbers; use
`0041` for the letter A. Ctrl+C also uses the guarded quit flow. Text inputs retain
their own editing keys. Selection paste clips at bitmap edges.

Pattern rows use `/`, e.g. `010/111/010`. A search `1` must match a set pixel;
search `0` is a wildcard, following Unifont Utils semantics. Replacement `.` keeps
the original pixel. Both patterns must have the same 3–16 pixel dimensions.
Preview and replacements remain staged until Done; Cancel leaves the document
untouched, and Done creates one undo entry.

## Files and recovery

Working libraries save as `.hex`. Open also accepts a UniPie JSON backup and
treats it as an unsaved import. Export can include all, active, or filtered glyphs;
image export always uses the active glyph. Exports do not mark the document saved.
Hex import accepts a UTF-8 BOM, comments beginning with `#`, and blank lines.
Malformed or duplicate records abort the whole import with a line error.

Crash drafts are written every two seconds and on normal teardown, using atomic
replacement. They contain the library, saved baseline, source path, fingerprint,
and active glyph. A new session offers restore, keep, or discard for each previous
draft. Unsupported/corrupt drafts remain on disk. Undo history starts anew after
recovery. Explicitly discarding work removes only that session's draft.

- Windows: `%LOCALAPPDATA%\UniPie\drafts`
- Linux/macOS: `${XDG_STATE_HOME:-~/.local/state}/unipie/drafts`

Changes since the last two-second checkpoint can be lost on a hard process kill.
Saving checks for external file changes before replacing a source. Concurrent
editing of the same source still requires coordination between sessions.

## Architecture and checks

`document.py` owns validated glyph data, saved state, and bounded delta history.
`grid.py` contains pure raster/selection operations. `formats.py` and `drafts.py`
handle file boundaries. `canvas.py` owns transient cursor/gesture state. `app.py`
coordinates UI workflows, with focused dialogs and transactional pattern previews.

```shell
uv run --locked pytest -q
uv run --locked ruff check .
uv run --locked ruff format --check .
uv build --no-build-isolation
```

UniPie starts at version `0.1.0`. Keep changes in `CHANGELOG.md` under Unreleased
until a release is explicitly prepared. UniCucumber remains a reference only;
this project does not depend on its source, generated data, or browser APIs.

## License

GPL-3.0-or-later, like Unifont Utils and UniCucumber. Copyright © 2024–2026
SkyEye_FAST. See [LICENSE](LICENSE).
