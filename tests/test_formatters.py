"""
Unit tests for table formatting and Korean display width calculation.
"""

import unittest

from budget_app.formatters import (
    format_currency,
    format_table,
    get_display_width,
    pad_string,
)


class TestFormatters(unittest.TestCase):

    def test_get_display_width_ascii_and_cjk(self):
        # ASCII: 1 column per character
        self.assertEqual(get_display_width("abc"), 3)
        self.assertEqual(get_display_width("12345"), 5)

        # Hangul: 2 columns per character
        self.assertEqual(get_display_width("한글"), 4)
        self.assertEqual(get_display_width("식비"), 4)

        # Mixed
        self.assertEqual(get_display_width("식비 (food)"), 11)  # 4 + 1 + 6 = 11

    def test_pad_string(self):
        # Left align
        padded = pad_string("식비", 8, align="left")
        self.assertEqual(get_display_width(padded), 8)
        self.assertTrue(padded.startswith("식비"))

        # Right align
        padded_r = pad_string("식비", 8, align="right")
        self.assertEqual(get_display_width(padded_r), 8)
        self.assertTrue(padded_r.endswith("식비"))

    def test_format_table(self):
        headers = ["카테고리", "금액"]
        rows = [
            ["식비", "15,000원"],
            ["교통", "2,500원"],
        ]
        table = format_table(headers, rows, ["left", "right"])
        self.assertIn("카테고리", table)
        self.assertIn("15,000원", table)

    def test_format_currency(self):
        self.assertEqual(format_currency(15000), "15,000원")
        self.assertEqual(format_currency(3000000), "3,000,000원")


if __name__ == "__main__":
    unittest.main()
