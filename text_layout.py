import textwrap


CHAR_WIDTH_FACTOR = 0.6
# Taller than fontsize so FFmpeg/Courier descenders are not clipped off the canvas.
LINE_HEIGHT_FACTOR = 1.75


def max_chars_per_line(fontsize: int, maxwidth: int, margin: int) -> int:
    char_pixel_width = max(1, fontsize * CHAR_WIDTH_FACTOR)
    return max(1, int((maxwidth - 2 * margin) // char_pixel_width))


def wrap_units(text: str, fontsize: int, maxwidth: int, margin: int) -> list[tuple[str, bool]]:
    width = max_chars_per_line(fontsize, maxwidth, margin)
    units: list[tuple[str, bool]] = []
    for original_line in (text or "").splitlines() or [""]:
        if original_line == "":
            units.append(("", True))
            continue
        wrapped = textwrap.wrap(original_line, width=width) or [""]
        units.append((wrapped[0], True))
        units.extend((piece, False) for piece in wrapped[1:])
    return units


def wrap_lines(text: str, fontsize: int, maxwidth: int, margin: int) -> list[str]:
    return [line for line, _starts_original in wrap_units(text, fontsize, maxwidth, margin)]


def speech_text_for_units(units: list[tuple[str, bool]]) -> str:
    if not units:
        return ""
    parts = [units[0][0]]
    for line, starts_original in units[1:]:
        if starts_original:
            parts.append("\n")
            parts.append(line)
        elif line:
            if parts[-1]:
                parts.append(" ")
            parts.append(line)
    return "".join(parts)


def line_height(fontsize: int) -> int:
    return max(1, int(fontsize * LINE_HEIGHT_FACTOR))


def max_lines_per_page(fontsize: int, maxheight: int, margin: int) -> int:
    return max(1, int((maxheight - 2 * margin) // line_height(fontsize)))


def content_height(line_count: int, fontsize: int, margin: int) -> int:
    return line_count * line_height(fontsize) + 2 * margin


def paginate_lines(lines: list, fontsize: int, maxheight: int, margin: int) -> list[list]:
    per_page = max_lines_per_page(fontsize, maxheight, margin)
    lines = lines or [""]
    return [lines[index:index + per_page] for index in range(0, len(lines), per_page)]


def canvas_size(maxwidth: int, maxheight: int) -> tuple[int, int]:
    width = max(640, maxwidth + maxwidth % 2)
    height = max(480, maxheight + maxheight % 2)
    return width, height
