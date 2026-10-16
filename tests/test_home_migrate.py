"""Đổi nhà ~/.r0 sang ~/.frog mà không đè bản đã có và không đụng nhà thật."""
from __future__ import annotations

import io
import os
import subprocess
import sys
import tempfile
import unittest
from argparse import Namespace
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import frog.activity as activity  # noqa: E402
import frog.keys as keys  # noqa: E402
import frog.repl as repl  # noqa: E402
from frog.cli import cmd_doctor  # noqa: E402
from frog.keys import migrate_user_home  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


class HomeMigrateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self._key = keys.KEYS_PATH
        self._repl = repl.SESS_DIR
        self._act = activity.SESS_DIR

    def tearDown(self):
        keys.KEYS_PATH = self._key
        repl.SESS_DIR = self._repl
        activity.SESS_DIR = self._act
        self.tmp.cleanup()

    def _go(self):
        with patch("frog.keys.Path.home", return_value=self.home):
            migrate_user_home()

    def test_chi_co_khoa_cu_thi_copy_dung_byte(self):
        old = self.home / ".r0"
        old.mkdir()
        raw = b'{"anthropic":"sk-cu"}\n'
        (old / "keys.json").write_bytes(raw)
        self._go()
        self.assertEqual((self.home / ".frog" / "keys.json").read_bytes(), raw)
        self.assertFalse((old / "keys.json").exists())
        self.assertEqual((old / "keys.json.migrated").read_bytes(), raw)

    def test_da_co_khoa_moi_khac_noi_dung_thi_khong_de(self):
        old = self.home / ".r0"
        new = self.home / ".frog"
        old.mkdir()
        new.mkdir()
        (old / "keys.json").write_text('{"anthropic":"sk-cu"}\n', encoding="utf-8")
        (new / "keys.json").write_text('{"anthropic":"sk-moi"}\n', encoding="utf-8")
        buf = io.StringIO()
        with redirect_stdout(buf):
            self._go()
        self.assertIn("sk-moi", (new / "keys.json").read_text(encoding="utf-8"))
        self.assertTrue((old / "keys.json").is_file())
        self.assertIn("sk-cu", (old / "keys.json").read_text(encoding="utf-8"))

    def test_goi_lan_hai_khong_de(self):
        old = self.home / ".r0"
        old.mkdir()
        raw = b'{"anthropic":"sk-cu"}\n'
        (old / "keys.json").write_bytes(raw)
        self._go()
        self._go()
        self.assertEqual((self.home / ".frog" / "keys.json").read_bytes(), raw)
        self.assertTrue((old / "keys.json.migrated").is_file())
        self.assertFalse((old / "keys.json").exists())

    def test_rename_loi_sau_khi_copy(self):
        old = self.home / ".r0"
        old.mkdir()
        raw = b'{"anthropic":"sk-cu"}\n'
        (old / "keys.json").write_bytes(raw)

        def boom(*_a, **_k):
            raise OSError("khoa")

        with patch("frog.keys.os.replace", boom):
            self._go()
        self.assertEqual((self.home / ".frog" / "keys.json").read_bytes(), raw)
        self.assertTrue((old / "keys.json").is_file())
        self._go()
        self.assertEqual((self.home / ".frog" / "keys.json").read_bytes(), raw)
        self.assertTrue((old / "keys.json").is_file())

    def test_phien_thieu_o_dich_thi_copy_file_thieu(self):
        old = self.home / ".r0" / "sessions"
        new = self.home / ".frog" / "sessions"
        old.mkdir(parents=True)
        new.mkdir(parents=True)
        (old / "a.jsonl").write_text("cu-a\n", encoding="utf-8")
        (old / "b.jsonl").write_text("cu-b\n", encoding="utf-8")
        (new / "a.jsonl").write_text("moi-a\n", encoding="utf-8")
        self._go()
        self.assertEqual((new / "a.jsonl").read_text(encoding="utf-8"), "moi-a\n")
        self.assertEqual((new / "b.jsonl").read_text(encoding="utf-8"), "cu-b\n")
        self.assertTrue((old / "a.jsonl").is_file())
        self.assertTrue((old / "b.jsonl").is_file())

    def test_khong_co_thu_muc_cu(self):
        self._go()
        self.assertFalse((self.home / ".frog").exists())

    def test_khoa_mira_sang_frog_giu_file_migrated(self):
        old = self.home / ".mira"
        old.mkdir()
        raw = b'{"anthropic":"sk-mira"}\n'
        (old / "keys.json").write_bytes(raw)
        self._go()
        self.assertEqual((self.home / ".frog" / "keys.json").read_bytes(), raw)
        self.assertFalse((old / "keys.json").exists())
        self.assertEqual((old / "keys.json.migrated").read_bytes(), raw)

    def test_khoa_r0_da_migrated_van_duoc_chep(self):
        old = self.home / ".r0"
        old.mkdir()
        raw = b'{"anthropic":"sk-r0"}\n'
        (old / "keys.json.migrated").write_bytes(raw)
        self._go()
        self.assertEqual((self.home / ".frog" / "keys.json").read_bytes(), raw)
        self.assertEqual((old / "keys.json.migrated").read_bytes(), raw)

    def test_shim_in_canh_bao(self):
        env = os.environ.copy()
        env["HOME"] = str(self.home)
        env["USERPROFILE"] = str(self.home)
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        proc = subprocess.run(
            [sys.executable, "-m", "r0", "doctor", "--out", str(self.home / "out")],
            cwd=ROOT, env=env, capture_output=True, text=True,
            encoding="utf-8", errors="replace", check=False)
        self.assertIn("Hãy gọi frog", proc.stderr)
        self.assertIn("2027-04-16", proc.stderr)
        self.assertEqual(proc.returncode, 0)
        proc_mira = subprocess.run(
            [sys.executable, "-m", "mira", "doctor", "--out", str(self.home / "out-mira")],
            cwd=ROOT, env=env, capture_output=True, text=True,
            encoding="utf-8", errors="replace", check=False)
        self.assertIn("Hãy gọi frog", proc_mira.stderr)
        self.assertNotIn("r0", proc_mira.stderr)
        self.assertEqual(proc_mira.returncode, 0)
        proc_frog = subprocess.run(
            [sys.executable, "-m", "frog", "doctor", "--out", str(self.home / "out2")],
            cwd=ROOT, env=env, capture_output=True, text=True,
            encoding="utf-8", errors="replace", check=False)
        self.assertNotIn("Hãy gọi frog", proc_frog.stderr)
        self.assertEqual(proc_frog.returncode, 0)

    def test_entry_cu_khong_dung_home_that(self):
        self._go()
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cmd_doctor(Namespace(out=str(self.home / "out")))
        text = buf.getvalue()
        self.assertEqual(code, 0)
        self.assertIn(".frog", text)
        self.assertNotIn(str(Path.home() / ".r0"), text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
