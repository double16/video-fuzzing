import unittest

from text_layout import canvas_size, content_height, line_height, paginate_lines, wrap_lines


class TextLayoutTests(unittest.TestCase):
    def test_wrap_lines_uses_available_width(self):
        lines = wrap_lines("one two three four", fontsize=10, maxwidth=36, margin=0)

        self.assertEqual(["one", "two", "three", "four"], lines)

    def test_paginate_lines_splits_into_pages(self):
        pages = paginate_lines(["one", "two", "three"], fontsize=10, maxheight=36, margin=1)

        self.assertEqual([["one", "two"], ["three"]], pages)

    def test_layout_clamps_small_dimensions(self):
        lines = wrap_lines("a b", fontsize=10, maxwidth=1, margin=10)
        pages = paginate_lines(lines, fontsize=10, maxheight=1, margin=10)

        self.assertEqual([["a"], ["b"]], pages)
        self.assertEqual((640, 480), canvas_size(1, 1))

    def test_canvas_dimensions_are_even(self):
        self.assertEqual((642, 722), canvas_size(641, 721))

    def test_wrap_preserves_original_line_breaks(self):
        from text_layout import speech_text_for_units, wrap_units

        units = wrap_units("one two three\nfour five", fontsize=10, maxwidth=36, margin=0)
        pages = paginate_lines(units, fontsize=10, maxheight=36, margin=1)

        self.assertEqual(
            ["one two", "three\nfour", "five"],
            [speech_text_for_units(page) for page in pages],
        )
        self.assertEqual(["one", "two", "three", "four", "five"], wrap_lines("one two three\nfour five", 10, 36, 0))

    def test_paginated_lines_fit_canvas_with_tall_glyphs(self):
        fontsize = 32
        maxheight = 720
        margin = 10
        pages = paginate_lines(["x"] * 100, fontsize, maxheight, margin)
        lines_on_page = len(pages[0])
        canvas_h = canvas_size(1280, min(maxheight, content_height(lines_on_page, fontsize, margin)))[1]
        glyph_height = fontsize * 1.2
        drawtext_spacing = fontsize * 0.5
        drawn_bottom = margin + glyph_height + (lines_on_page - 1) * (glyph_height + drawtext_spacing)
        self.assertLessEqual(drawn_bottom, canvas_h)


if __name__ == "__main__":
    unittest.main()
