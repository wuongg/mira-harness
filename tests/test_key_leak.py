"""Khóa không vào argv, không vào log, không vào shell con."""
from __future__ import annotations

import io
import json
import os
import shlex
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from frog import keys  # noqa: E402
from frog.cli import build_parser, note_argv_key  # noqa: E402
from frog.tools import Session, _shell_env  # noqa: E402

SECRET = "sk-test-EXPOSE-0123456789"
ROOT = Path(__file__).resolve().parents[1]


class KeyLeakTest(unittest.TestCase):
    def test_save_ghi_file_va_readme_khong_noi_doi(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("không bao giờ ghi ra tệp", readme)
        old = keys.KEYS_PATH
        buf = io.StringIO()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                keys.KEYS_PATH = Path(tmp) / "keys.json"
                with redirect_stdout(buf):
                    keys.save({"anthropic": SECRET})
                    keys.print_status()
                self.assertTrue(keys.KEYS_PATH.is_file())
                self.assertIn(SECRET, keys.KEYS_PATH.read_text(encoding="utf-8"))
        finally:
            keys.KEYS_PATH = old
        self.assertNotIn("EXPOSE", buf.getvalue())

    def test_argv_key_bi_canh_bao_khong_lot_trace(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            args = build_parser().parse_args(["run", "--api-key", SECRET, "--n", "0", "--quiet"])
            trace = note_argv_key(args)
        text = buf.getvalue() + json.dumps(trace, ensure_ascii=False)
        self.assertNotIn("EXPOSE", text)
        self.assertEqual(trace[0]["kind"], "argv_key_warning")

    def test_shell_con_khong_thay_khoa(self):
        old = os.environ.get("ANTHROPIC_API_KEY")
        os.environ["ANTHROPIC_API_KEY"] = SECRET
        try:
            with tempfile.TemporaryDirectory() as tmp:
                session = Session(root=Path(tmp), mode="bypass", approve=lambda _t, _a: True)
                cmd = shlex.join([sys.executable, "-c",
                                  "import os; print(os.environ.get('ANTHROPIC_API_KEY', ''))"])
                out = session.run_shell(cmd)
        finally:
            if old is None:
                os.environ.pop("ANTHROPIC_API_KEY", None)
            else:
                os.environ["ANTHROPIC_API_KEY"] = old
        self.assertNotIn("EXPOSE", out)

    def _python_env(self, name: str) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            session = Session(root=Path(tmp), mode="bypass", approve=lambda _t, _a: True)
            cmd = shlex.join([sys.executable, "-c",
                              f"import os; print(os.environ.get({name!r}, ''))"])
            return session.run_shell(cmd)

    def test_printenv_khong_chua_khoa(self):
        old = os.environ.get("ANTHROPIC_API_KEY")
        os.environ["ANTHROPIC_API_KEY"] = SECRET
        try:
            if shutil.which("printenv"):
                with tempfile.TemporaryDirectory() as tmp:
                    session = Session(root=Path(tmp), mode="bypass", approve=lambda _t, _a: True)
                    listed = session.run_shell("printenv")
                self.assertNotIn("EXPOSE", listed)
                self.assertNotIn(f"ANTHROPIC_API_KEY={SECRET}", listed)
            child = self._python_env("ANTHROPIC_API_KEY")
        finally:
            if old is None:
                os.environ.pop("ANTHROPIC_API_KEY", None)
            else:
                os.environ["ANTHROPIC_API_KEY"] = old
        self.assertNotIn("EXPOSE", child)

    def test_hau_to_api_key_bi_bo(self):
        old = os.environ.get("FOO_API_KEY")
        os.environ["FOO_API_KEY"] = "EXPOSE-FOO"
        try:
            child = self._python_env("FOO_API_KEY")
        finally:
            if old is None:
                os.environ.pop("FOO_API_KEY", None)
            else:
                os.environ["FOO_API_KEY"] = old
        self.assertNotIn("EXPOSE-FOO", child)

    def test_path_van_con(self):
        env = _shell_env()
        self.assertTrue("PATH" in env or "Path" in env)


if __name__ == "__main__":
    unittest.main(verbosity=2)
