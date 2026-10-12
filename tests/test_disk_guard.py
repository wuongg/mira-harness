"""Khóa đĩa của phiên: symlink, bí mật, shell, undo, https, luôn cho phép."""
import os
import tempfile
import unittest
from pathlib import Path

from r0.agent import _price
from r0.repl import condense_trace, view_for_model
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

    def test_shell_ghi_trong_ban_sao(self):
        import shlex
        import sys
        cmd = shlex.join([sys.executable, "-c",
                          "open('created.txt','w',encoding='utf-8').write('x'); print('xin-chao')"])
        out = self._sess().run_shell(cmd)
        self.assertIn("xin-chao", out)
        self.assertFalse((self.root / "created.txt").exists())

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
        trace = [{"kind": "message", "role": "user", "content": f"viec {i}"} for i in range(8)]
        note, event = condense_trace(trace)
        self.assertTrue(note.startswith("Đã rút gọn"))
        self.assertIsNotNone(event)
        trace.append(event)
        view = view_for_model(trace)
        self.assertEqual(len(view), 7)
        self.assertIn("TÓM TẮT", view[0]["content"])
        self.assertIn("viec 0", event["summary"])
        self.assertEqual(trace[0]["content"], "viec 0")

    def test_compact_lay_so_sua(self):
        trace = [{"kind": "message", "role": "user", "content": "x" * 200} for _ in range(8)]
        audit = [{"action": "edit_file", "path": "app.py"}]
        _note, event = condense_trace(trace, audit=audit)
        self.assertIn("edit_file app.py", event["summary"])
        self.assertNotIn("x" * 120, event["summary"])

    def test_plan_khong_nang_lan(self):
        s = self._sess(mode="plan")
        out = s.write_file("moi.txt", "a")
        self.assertTrue(out.startswith("BỊ CHẶN"))
        self.assertEqual(s.lane_seen, 0)
        ok, _why = s.accept_finish()
        self.assertTrue(ok)

    def test_sua_hop_le_thi_finish_duoc(self):
        s = self._sess(mode="acceptEdits")
        s.edit_file("a.txt", "xin chao", "xin")
        self.assertEqual(s.lane_seen, 1)
        ok, _why = s.accept_finish()
        self.assertTrue(ok)

    def test_lan_2_khong_co_checker_thi_khong_dung(self):
        import shlex
        import sys
        from r0.agent import run_turn
        from r0.bench import _Scripted
        s = self._sess()
        cmd = shlex.join([sys.executable, "-c", "pass"])
        s.run_shell(cmd)
        self.assertEqual(s.lane_seen, 2)
        ok, why = s.accept_finish()
        self.assertFalse(ok)
        self.assertIn("kiểm chứng", why)
        replies = ['<tool>{"name":"finish","args":{"summary":"xong"}}</tool>'] * 3
        res = run_turn(task="xong chua", session=s, model="sonnet-5.5",
                       protocol="text", no_stream=True, max_turns=3,
                       provider=_Scripted(replies), on_text=lambda _t: None)
        self.assertEqual(res["status"], "stopped_verification")
