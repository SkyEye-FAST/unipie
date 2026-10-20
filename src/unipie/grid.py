"""Pure bitmap operations; Pillow provides established raster drawing primitives."""

from PIL import Image, ImageDraw

Point = tuple[int, int]
Rect = tuple[int, int, int, int]


def draw(data: list[int], width: int, tool: str, start: Point, end: Point, value: int) -> list[int]:
    """Draw a stroke, line, rectangle, or flood fill on a detached bitmap."""
    with Image.new("L", (width, 16)) as image:
        image.putdata(data)
        painter = ImageDraw.Draw(image)
        if tool in {"pencil", "eraser", "line"}:
            painter.line((start, end), fill=value)
        elif tool in {"rectangle", "filled rectangle"}:
            box = bounds(start, end)
            painter.rectangle(
                box, outline=value, fill=value if tool == "filled rectangle" else None
            )
        elif tool == "fill":
            ImageDraw.floodfill(image, start, value)
        else:
            raise ValueError(f"Unknown drawing tool: {tool}")
        return [image.getpixel((x, y)) for y in range(16) for x in range(width)]


def bounds(start: Point, end: Point) -> Rect:
    """Normalize an inclusive selection rectangle."""
    return (
        min(start[0], end[0]),
        min(start[1], end[1]),
        max(start[0], end[0]),
        max(start[1], end[1]),
    )


def transform(data: list[int], width: int, operation: str) -> list[int]:
    """Invert, clear, flip, resize, or shift a bitmap; shifts discard edge pixels."""
    if operation == "invert":
        return [1 - pixel for pixel in data]
    if operation == "clear":
        return [0] * len(data)
    if operation == "width":
        new_width = 8 if width == 16 else 16
        return [
            data[y * width + x] if x < width else 0 for y in range(16) for x in range(new_width)
        ]
    offsets = {"left": (-1, 0), "right": (1, 0), "up": (0, -1), "down": (0, 1)}
    result = [0] * len(data)
    for y in range(16):
        for x in range(width):
            if operation == "flip horizontal":
                source_x, source_y = width - 1 - x, y
            elif operation == "flip vertical":
                source_x, source_y = x, 15 - y
            elif operation in offsets:
                dx, dy = offsets[operation]
                source_x, source_y = x - dx, y - dy
            else:
                raise ValueError(f"Unknown transform: {operation}")
            if 0 <= source_x < width and 0 <= source_y < 16:
                result[y * width + x] = data[source_y * width + source_x]
    return result


def extract(data: list[int], width: int, rect: Rect) -> tuple[list[int], int]:
    """Copy an inclusive rectangle for the internal selection clipboard."""
    left, top, right, bottom = rect
    return [data[y * width + x] for y in range(top, bottom + 1) for x in range(left, right + 1)], (
        right - left + 1
    )


def paste(
    data: list[int], width: int, pixels: list[int], clip_width: int, point: Point
) -> list[int]:
    """Paste a rectangular bitmap, clipping pixels at the document edges."""
    result = data.copy()
    for index, pixel in enumerate(pixels):
        x, y = point[0] + index % clip_width, point[1] + index // clip_width
        if 0 <= x < width and 0 <= y < 16:
            result[y * width + x] = pixel
    return result
