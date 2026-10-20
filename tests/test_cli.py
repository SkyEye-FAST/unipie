import sys

import pytest

from unipie.app import UniPie
from unipie.cli import main


@pytest.mark.parametrize(
    "arguments,code,width",
    [
        (["--width", "8"], "0041", 8),
        (["--code-point", "中"], "4E2D", 16),
        (["--code-point", "0041", "--hex", "0000000018242442427E424242420000"], "0041", 8),
    ],
)
def test_launch_arguments_create_expected_document(monkeypatch, arguments, code, width) -> None:
    documents = []
    monkeypatch.setattr(sys, "argv", ["unipie", *arguments])
    monkeypatch.setattr(UniPie, "run", lambda app: documents.append(app.document))
    main()
    assert documents[0].active == code
    assert documents[0].glyph.width == width
    assert documents[0].dirty


def test_missing_explicit_code_point_is_reported(monkeypatch, tmp_path, capsys) -> None:
    source = tmp_path / "font.hex"
    source.write_text("0041:" + "0" * 32 + "\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["unipie", str(source), "--code-point", "0042"])
    with pytest.raises(SystemExit) as exit_info:
        main()
    assert exit_info.value.code == 2
    assert "does not exist" in capsys.readouterr().err
