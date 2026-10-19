"""
String and Table Formatting Utilities with Korean / East Asian Wide Character Support.
Provides clean terminal alignment without any third-party dependencies.
"""

from typing import List, Optional
import unicodedata


def get_display_width(text: str) -> int:
    """
    Calculate the visual terminal column width of a string.
    East Asian Wide ('W') and Fullwidth ('F') characters count as 2 columns,
    while halfwidth and neutral characters count as 1 column.
    """
    width = 0
    for ch in text:
        east_asian = unicodedata.east_asian_width(ch)
        if east_asian in ("W", "F"):
            width += 2
        else:
            width += 1
    return width


def pad_string(text: str, target_width: int, align: str = "left") -> str:
    """
    Pad a string to the given display width, considering multi-byte East Asian characters.
    """
    current_width = get_display_width(text)
    padding_needed = max(0, target_width - current_width)

    if align == "right":
        return (" " * padding_needed) + text
    elif align == "center":
        left_pad = padding_needed // 2
        right_pad = padding_needed - left_pad
        return (" " * left_pad) + text + (" " * right_pad)
    else:  # left
        return text + (" " * padding_needed)


def format_table(
    headers: List[str],
    rows: List[List[str]],
    alignments: Optional[List[str]] = None,
) -> str:
    """
    Format a list of rows into an ASCII/Unicode aligned table string.
    """
    if not headers and not rows:
        return ""

    num_cols = len(headers) if headers else (len(rows[0]) if rows else 0)
    if alignments is None:
        alignments = ["left"] * num_cols

    # Calculate column widths
    col_widths = [get_display_width(h) for h in headers] if headers else [0] * num_cols
    for row in rows:
        for idx, cell in enumerate(row):
            if idx < len(col_widths):
                col_widths[idx] = max(col_widths[idx], get_display_width(str(cell)))

    # Add margin
    padded_widths = [w + 2 for w in col_widths]

    lines: List[str] = []

    # Horizontal separator
    def make_divider(char: str = "-") -> str:
        return "+".join(char * pw for pw in padded_widths)

    divider = make_divider("-")

    # Header
    if headers:
        header_cells = [
            f" {pad_string(headers[i], col_widths[i], alignments[i])} "
            for i in range(num_cols)
        ]
        lines.append(divider)
        lines.append("|".join(header_cells))
        lines.append(divider)

    # Data Rows
    for row in rows:
        row_cells = []
        for i in range(num_cols):
            val = str(row[i]) if i < len(row) else ""
            align = alignments[i] if i < len(alignments) else "left"
            row_cells.append(f" {pad_string(val, col_widths[i], align)} ")
        lines.append("|".join(row_cells))

    lines.append(divider)
    return "\n".join(lines)


def format_currency(amount: int) -> str:
    """Format an integer amount as comma-separated Korean Won currency string."""
    return f"{amount:,}원"
