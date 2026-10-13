"""Helper biến log unittest thành annotation, không gọi mạng."""
import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path
import tempfile

from tools.ci_annotate import annotate


class CiAnnotateTest(unittest.TestCase):
    def test_log_xanh_khong_in_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "unittest.txt"
            path.write_text("OK\n", encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = annotate(path, 0)
        self.assertEqual(code, 0)
        self.assertNotIn("::error::", buf.getvalue())

    def test_fail_trich_ten_test(self):
        log = (
            "FAIL: test_vi_du (mod.Class.test_vi_du)\n"
            "----------------------------------------------------------------------\n"
            "Traceback (most recent call last):\n"
            "AssertionError: 1 != 2\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "unittest.txt"
            path.write_text(log, encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = annotate(path, 1)
        text = buf.getvalue()
        self.assertEqual(code, 1)
        self.assertIn("::error::", text)
        self.assertIn("test_vi_du", text)
        self.assertIn("AssertionError", text)

    def test_error_traceback_duoc_giu(self):
        long_line = "x" * 600
        log = (
            "ERROR: test_no (mod.Class.test_no)\n"
            "----------------------------------------------------------------------\n"
            "Traceback (most recent call last):\n"
            + long_line
            + "\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "unittest.txt"
            path.write_text(log, encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = annotate(path, 1)
        text = buf.getvalue()
        self.assertEqual(code, 1)
        self.assertIn("ERROR:", text)
        self.assertIn("Traceback", text)
        self.assertNotIn("x" * 501, text)

    def test_thoat_khong_co_khoi_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "unittest.txt"
            path.write_text("Ran 1 test\n", encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = annotate(path, 1)
        self.assertEqual(code, 1)
        self.assertIn("::error::", buf.getvalue())
        self.assertIn("khong co khoi fail", buf.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
