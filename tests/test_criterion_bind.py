"""Lệnh xanh không xác minh tiêu chí khác. Artifact của run khác không được nhận."""
from __future__ import annotations

import hashlib
import shlex
import sys
import tempfile
import unittest
from pathlib import Path

from mira.obligations import judge_obligations


def _exit(code: int) -> str:
    return shlex.join([sys.executable, "-c", f"import sys; raise SystemExit({code})"])


class CriterionBindTest(unittest.TestCase):
    def test_lenh_xanh_khong_xac_minh_tieu_chi(self):
        cmd = _exit(0)
        with tempfile.TemporaryDirectory() as tmp:
            rows = judge_obligations(
                [f"check: {cmd}"], cwd=Path(tmp), granted={cmd}, run_id="run-a")
        row = rows[0]
        self.assertTrue(row["check_passed"])
        self.assertFalse(row["criterion_verified"])
        self.assertEqual(row["state"], "checked")
        self.assertNotEqual(row["proves"], row["criterion"])

    def test_test_xanh_khong_dung_hanh_vi(self):
        cmd = _exit(0)
        item = {
            "schema": 1,
            "id": "c-save",
            "text": "nút lưu ghi đúng một bản",
            "cmd": cmd,
            "proves": "pytest thoát 0",
        }
        with tempfile.TemporaryDirectory() as tmp:
            rows = judge_obligations([item], cwd=Path(tmp), granted={cmd}, run_id="run-a")
        self.assertTrue(rows[0]["check_passed"])
        self.assertFalse(rows[0]["criterion_verified"])
        self.assertEqual(rows[0]["criterion_id"], "c-save")

    def test_artifact_run_khac_bi_tu_choi(self):
        cmd = _exit(0)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app.py").write_text("def f():\n    return 0\n", encoding="utf-8")
            digest = hashlib.sha256((root / "app.py").read_bytes()).hexdigest()
            item = {
                "schema": 1,
                "id": "c-fn",
                "text": "hàm trả 1",
                "cmd": cmd,
                "proves": "hàm trả 1",
                "artifact": "app.py",
            }
            rows = judge_obligations(
                [item], cwd=root, granted={cmd}, run_id="run-a",
                artifacts={"app.py": {"sha256": digest, "run_id": "run-b"}})
        self.assertFalse(rows[0]["criterion_verified"])
        self.assertIsNone(rows[0]["artifact"])

    def test_file_doi_nhung_ham_sai_khong_duoc_xac_minh(self):
        cmd = _exit(0)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app.py").write_text("def f():\n    return 0\n", encoding="utf-8")
            digest = hashlib.sha256((root / "app.py").read_bytes()).hexdigest()
            item = {
                "schema": 1,
                "id": "c-fn",
                "text": "hàm trả 1",
                "cmd": cmd,
                "proves": "pytest thoát 0",
                "artifact": "app.py",
            }
            rows = judge_obligations(
                [item], cwd=root, granted={cmd}, run_id="run-a",
                artifacts={"app.py": {"sha256": digest, "run_id": "run-a"}})
        self.assertTrue(rows[0]["check_passed"])
        self.assertFalse(rows[0]["criterion_verified"])

    def test_model_de_xuat_check_chua_cap_quyen(self):
        cmd = _exit(0)
        with tempfile.TemporaryDirectory() as tmp:
            rows = judge_obligations(
                [f"check: {cmd}"], cwd=Path(tmp), granted=set(), run_id="run-a")
        self.assertEqual(rows[0]["state"], "pending")
        self.assertFalse(rows[0]["check_passed"])
        self.assertFalse(rows[0]["criterion_verified"])

    def test_tieu_chi_khong_tu_dong_can_xac_nhan(self):
        rows = judge_obligations(["đoạn văn có nguồn"], granted=set(), run_id="run-a")
        self.assertEqual(rows[0]["state"], "needs_confirmation")
        self.assertFalse(rows[0]["criterion_verified"])
        self.assertTrue(rows[0]["criterion_id"])

    def test_khop_claim_va_artifact_cung_run_moi_xac_minh(self):
        cmd = _exit(0)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app.py").write_text("def f():\n    return 1\n", encoding="utf-8")
            digest = hashlib.sha256((root / "app.py").read_bytes()).hexdigest()
            item = {
                "schema": 1,
                "id": "c-fn",
                "text": "hàm trả 1",
                "cmd": cmd,
                "proves": "hàm trả 1",
                "artifact": "app.py",
            }
            rows = judge_obligations(
                [item], cwd=root, granted={cmd}, run_id="run-a",
                artifacts={"app.py": {"sha256": digest, "run_id": "run-a"}})
        self.assertTrue(rows[0]["check_passed"])
        self.assertTrue(rows[0]["criterion_verified"])
        self.assertEqual(rows[0]["state"], "verified")
        self.assertEqual(rows[0]["artifact"]["sha256"], digest)
        self.assertEqual(rows[0]["artifact"]["run_id"], "run-a")


if __name__ == "__main__":
    unittest.main(verbosity=2)
