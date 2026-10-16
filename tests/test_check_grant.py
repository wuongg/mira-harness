"""Model không tự cấp quyền chạy check. Chưa được phép thì không gọi subprocess."""
from __future__ import annotations

import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from frog.obligations import judge_obligations
from frog.tools import Session

SECRET = "sk-test-EXPOSE-0123456789"


def _exit(code: int) -> str:
    return shlex.join([sys.executable, "-c", f"import sys; raise SystemExit({code})"])


class CheckGrantTest(unittest.TestCase):
    def test_model_de_xuat_khong_goi_subprocess(self):
        cmd = _exit(0)
        with tempfile.TemporaryDirectory() as tmp, \
                patch("frog.tools.subprocess.run") as run:
            rows = judge_obligations(
                [f"check: {cmd}"], cwd=Path(tmp), granted=set())
        run.assert_not_called()
        self.assertEqual(rows[0]["state"], "pending")
        self.assertIn("chưa được cấp quyền", rows[0]["reason"])

    def test_nguoi_dung_cap_quyen_thi_chay_qua_run_shell(self):
        cmd = _exit(0)
        with tempfile.TemporaryDirectory() as tmp:
            rows = judge_obligations(
                [f"check: {cmd}"], cwd=Path(tmp), granted={cmd})
        self.assertEqual(rows[0]["state"], "unverified")
        self.assertTrue(rows[0]["check_passed"])
        self.assertFalse(rows[0]["criterion_verified"])
        self.assertEqual(rows[0]["ref"]["exit"], 0)
        self.assertEqual(rows[0]["ref"]["via"], "run_shell")

    def test_path_ngoai_goc_bi_chan_truoc_subprocess(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outside = root.parent / "check-grant-outside.py"
            cmd = shlex.join([sys.executable, str(outside)])
            with patch("frog.tools.subprocess.run") as run:
                rows = judge_obligations(
                    [f"check: {cmd}"], cwd=root, granted={cmd})
        run.assert_not_called()
        self.assertEqual(rows[0]["state"], "blocked")

    def test_qua_gio_khong_thanh_proven(self):
        cmd = _exit(0)
        def boom(*_a, **_k):
            raise subprocess.TimeoutExpired(cmd, 30)
        with tempfile.TemporaryDirectory() as tmp, \
                patch("frog.tools.subprocess.run", side_effect=boom):
            rows = judge_obligations(
                [f"check: {cmd}"], cwd=Path(tmp), granted={cmd})
        self.assertEqual(rows[0]["state"], "unproven")
        self.assertIn("quá", rows[0]["reason"])

    def test_dau_ra_bi_cat_va_khong_co_khoa(self):
        cmd = shlex.join([
            sys.executable, "-c",
            "import os; print('X'*20000); print(os.environ.get('ANTHROPIC_API_KEY',''))",
        ])
        os.environ["ANTHROPIC_API_KEY"] = SECRET
        try:
            with tempfile.TemporaryDirectory() as tmp:
                session = Session(root=Path(tmp), mode="default", approve=lambda *_a: True)
                text = session.run_shell(cmd, timeout=30)
        finally:
            os.environ.pop("ANTHROPIC_API_KEY", None)
        self.assertNotIn(SECRET, text)
        self.assertLessEqual(len(text), 8100)
        self.assertIn("[mã thoát 0]", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
