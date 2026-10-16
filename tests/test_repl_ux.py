import io
import contextlib
import unittest

from frog import repl


class ReplUxTest(unittest.TestCase):
    def test_banner_khong_icon(self):
        import io
        import contextlib
        from pathlib import Path
        from frog import ui
        from frog.tools import Session
        ui.set_color(False)
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                repl.banner(Session(root=Path("."), mode="default"), "sonnet-5.5", False)
        finally:
            ui.set_color(None)
        out = buf.getvalue()
        self.assertIn("frog", out)
        self.assertIn("sonnet-5.5", out)
        self.assertIn("/exit", out)
        self.assertIn("╭", out)
        self.assertIn("╰", out)
        self.assertLessEqual(out.count("\n"), ui.term_height() + 2)
        for ch in ("⏱", "⚠", "⚙", "▸", "✓", "✗"):
            self.assertNotIn(ch, out)

    def test_help_lists_menu_and_keys(self):
        h = repl.HELP
        self.assertIn("/menu", h)
        self.assertIn("/keys", h)

    def test_err_note_auth_is_actionable(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            repl._err_note('anthropic: HTTP 401 — {"error":{"type":"authentication_error"}}')
        out = buf.getvalue()
        self.assertIn("Khoá API", out)
        self.assertIn("/keys", out)

    def test_err_note_generic(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            repl._err_note("timeout mạng")
        self.assertIn("timeout", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
