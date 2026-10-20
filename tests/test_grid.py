from unipie import grid


def test_fill_respects_rectangle_and_line_connects_distant_endpoints() -> None:
    blank = [0] * 128
    outline = grid.draw(blank, 8, "rectangle", (1, 1), (6, 14), 1)
    filled = grid.draw(outline, 8, "fill", (2, 2), (2, 2), 1)
    assert sum(outline) == 36
    assert sum(filled) == 84
    assert blank == [0] * 128
    diagonal = grid.draw(blank, 8, "line", (0, 0), (7, 15), 1)
    assert sum(diagonal) == 16
    assert diagonal[0] == diagonal[-1] == 1


def test_width_conversion_preserves_rows_and_shifts_drop_edges() -> None:
    data = [0] * 128
    data[0] = data[15 * 8 + 7] = 1
    wide = grid.transform(data, 8, "width")
    assert wide[0] == wide[15 * 16 + 7] == 1
    assert grid.transform(wide, 16, "width") == data
    shifted = grid.transform(data, 8, "right")
    assert sum(shifted) == 1 and shifted[1] == 1
    flipped = grid.transform(data, 8, "flip horizontal")
    assert flipped[7] == flipped[15 * 8] == 1


def test_selection_copy_paste_is_clipped_without_mutating_sources() -> None:
    data = grid.draw([0] * 128, 8, "filled rectangle", (1, 1), (3, 3), 1)
    pixels, width = grid.extract(data, 8, grid.bounds((3, 3), (1, 1)))
    assert pixels == [1] * 9
    pasted = grid.paste([0] * 128, 8, pixels, width, (7, 15))
    assert sum(pasted) == 1
    assert pixels == [1] * 9
