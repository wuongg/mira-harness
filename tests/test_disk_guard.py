"""Khóa đĩa của phiên: symlink, bí mật, shell, undo, https, luôn cho phép."""
import os
import tempfile
import unittest
from pathlib import Path

from r0.agent import _price
from r0.repl import compact_history
from r0.tools import Session


class DiskGuardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "a.txt").write_text("xin chao", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def _sess(self, **kw):
        kw.setdefault("mode", "default")
        kw.setdefault("approve", lambda t, a: True)
        return Session(root=self.root, **kw)

    def test_khong_doc_env(self):
        (self.root / ".env").write_text("TOKEN=bi-mat", encoding="utf-8")
        out = self._sess().read_file(".env")
        self.assertTrue(out.startswith("BỊ CHẶN"))
        self.assertNotIn("bi-mat", out)
        self.assertNotIn("bi-mat", self._sess().grep("TOKEN", "."))

    def test_symlink_thoat_goc(self):
        outside = Path(self.tmp.name).parent / "mira-secret-ngoai.txt"
        outside.write_text("bi-mat", encoding="utf-8")
        link = self.root / "lo.txt"
        try:
            os.symlink(outside, link)
        except OSError:
            self.skipTest("máy không cho tạo symlink")
        try:
            with self.assertRaises(PermissionError):
                self._sess().read_file("lo.txt")
        finally:
            outside.unlink(missing_ok=True)

    def test_shell_khong_ra_ngoai(self):
        out = self._sess().run_shell("python ../ngoai.txt")
        self.assertTrue(out.startswith("BỊ CHẶN"))

    def test_undo_sau_khi_xoa(self):
        s = self._sess()
        s.delete_file("a.txt")
        self.assertFalse((self.root / "a.txt").exists())
        self.assertIn("đã hoàn tác", s.undo_last())
        self.assertEqual((self.root / "a.txt").read_text(encoding="utf-8"), "xin chao")

    def test_https_noi_bo_bi_chan(self):
        out = self._sess().fetch_url("https://127.0.0.1/x")
        self.assertTrue(out.startswith("LỖI"))
        self.assertIn("nội bộ", out)

    def test_luon_cho_phep_nho_trong_phien(self):
        seen = []

        def approve(tool, args):
            seen.append(args.get("cmd"))
            return "always"

        s = Session(root=self.root, approve=approve)
        self.assertTrue(s._allow("run_shell", {"cmd": "py -c 1"}))
        self.assertTrue(s._allow("run_shell", {"cmd": "py -c 1"}))
        self.assertEqual(seen, ["py -c 1"])

    def test_model_la_van_co_gia(self):
        self.assertGreater(_price("khong-co-model", {"in": 1_000_000, "out": 0}), 0)

    def test_compact_gop_tin_cu(self):
        history = [{"role": "user", "content": f"viec {i}"} for i in range(8)]
        out, note, event = compact_history(history)
        self.assertTrue(note.startswith("Đã rút gọn"))
        self.assertIn("TÓM TẮT", out[0]["content"])
        self.assertEqual(len(out), 7)
        self.assertEqual(event["kind"], "condensed")
        self.assertEqual(event["dropped"], 2)
        self.assertIn("viec 0", event["summary"])
