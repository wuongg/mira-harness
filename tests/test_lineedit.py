import unittest

from r0 import lineedit as L


class GhostTest(unittest.TestCase):
    def test_ghost_single(self):
        self.assertEqual(L.ghost("/he"), "lp")
        self.assertEqual(L.ghost("/hel"), "p")

    def test_ghost_shows_top_when_ambiguous(self):
        self.assertEqual(L.ghost("/"), "help")
        self.assertEqual(L.ghost("/co"), "st")

    def test_ghost_cycle(self):
        first = L.ghost("/co", 0)
        second = L.ghost("/co", 1)
        self.assertNotEqual(first, second)

    def test_ghost_args(self):
        self.assertEqual(L.ghost("/mode p"), "lan")
        self.assertEqual(L.ghost("/team o"), "n")

    def test_ghost_empty_and_plain(self):
        self.assertEqual(L.ghost(""), "")
        self.assertEqual(L.ghost("hello"), "")

    def test_accept_single_fills_and_spaces(self):
        self.assertEqual(L.accept("/he")[0], "/help ")
        self.assertEqual(L.accept("/mode p")[0], "/mode plan ")

    def test_accept_extends_common_prefix(self):
        # /s -> /save, /sessions : tiền tố chung "/s" đã bằng phần gõ -> điền khả năng đầu
        self.assertEqual(L.accept("/s")[0], "/save ")
        # /mo -> /mode, /model : tiền tố chung "/mod"
        self.assertEqual(L.accept("/mo")[0], "/mod")

    def test_accept_no_match(self):
        self.assertEqual(L.accept("xyz"), ("xyz", 0))

    def test_accept_cycles(self):
        a = L.accept("/co", 0)[0]
        b = L.accept("/co", 1)[0]
        self.assertNotEqual(a, b)
        self.assertTrue(a.endswith(" ") and b.endswith(" "))

    def test_common_prefix(self):
        self.assertEqual(L.common_prefix(["/co", "/cost", "/compact"]), "/co")
        self.assertEqual(L.common_prefix([]), "")

    def test_read_line_falls_back_when_not_tty(self):
        import io
        import sys
        old = sys.stdin
        sys.stdin = io.StringIO("abc\n")
        try:
            self.assertEqual(L.read_line("› "), "abc")
        finally:
            sys.stdin = old


if __name__ == "__main__":
    unittest.main()
