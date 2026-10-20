import unittest

from frog import lineedit as L


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
        # /mode là tiền tố của /model, nên tiền tố chung của "/mo" là "/mode".
        self.assertEqual(L.accept("/mo")[0], "/mode")

    def test_accept_no_match(self):
        self.assertEqual(L.accept("xyz"), ("xyz", 0))

    def test_accept_cycles(self):
        a = L.accept("/co", 0)[0]
        b = L.accept("/co", 1)[0]
        self.assertNotEqual(a, b)
        self.assertTrue(a.endswith(" ") and b.endswith(" "))

    def test_chu_a_huyen_la_chu(self):
        buf, _c, _i, action = L.apply_console_key("xin ch", 0, [], 0, 0, "ào")
        self.assertEqual(action, "redraw")
        self.assertEqual(buf, "xin chào")

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

    def test_rewind_len_qua_be_ngang(self):
        self.assertEqual(L.rewind_prefix(0, 40), "\r")
        self.assertEqual(L.rewind_prefix(25, 10), "\x1b[2A\r")
        self.assertEqual(L.rewind_prefix(10, 10), "\x1b[1A\r")

    def test_place_sau_ghost_xuong_hang(self):
        self.assertEqual(L.place_after_typed(25, 28, 10), "\r\x1b[5C")
        self.assertEqual(L.place_after_typed(8, 13, 10), "\x1b[1A\r\x1b[8C")


if __name__ == "__main__":
    unittest.main()
