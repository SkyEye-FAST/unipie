"""Independent UniPie command line entry point."""

import argparse
from pathlib import Path

from unipie import __version__
from unipie.document import Document


def main() -> None:
    """Launch the terminal editor for a hex file, a bitmap, or an empty glyph."""
    parser = argparse.ArgumentParser(description="UniPie — GNU Unifont terminal editor")
    parser.add_argument("path", nargs="?", type=Path, help="Unifont .hex library to open")
    parser.add_argument(
        "--code-point", help="Initial code point (hex or character; blank glyph defaults to 0041)"
    )
    parser.add_argument("--width", type=int, choices=(8, 16), default=16, help="Blank glyph width")
    parser.add_argument("--hex", dest="bitmap", help="Initial glyph bitmap (32 or 64 hex digits)")
    parser.add_argument("--version", action="version", version=f"UniPie {__version__}")
    args = parser.parse_args()
    try:
        if args.path:
            from unipie.formats import open_document

            if args.bitmap:
                parser.error("A file path and --hex cannot be combined.")
            document = open_document(args.path)
            if args.code_point is not None:
                document.select(args.code_point)
        else:
            document = Document()
            document.add(args.code_point or "0041", args.width)
            if args.bitmap:
                document.commit({document.active: args.bitmap})
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    from unipie.app import UniPie

    UniPie(document).run()
