"""proves trùng câu không phải bằng chứng. Validator mới được xác minh."""
from __future__ import annotations

import hashlib
import json
import shlex
import sys
import tempfile
import unittest
from pathlib import Path

from mira.obligations import judge_obligations


def _exit(code: int) -> str:
    return shlex.join([sys.executable, "-c", f"import sys; raise SystemExit({code})"])


class ValidatorTest(unittest.TestCase):
    def test_claim_trung_cau_va_hash_khong_verified(self):
        cmd = _exit(0)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "calc.py").write_text("return 4\n", encoding="utf-8")
            digest = hashlib.sha256((root / "calc.py").read_bytes()).hexdigest()
            item = {
                "schema": 1, "id": "wrong-file", "text": "ham cong tra ve nam",
                "cmd": cmd, "proves": "ham cong tra ve nam", "artifact": "calc.py",
            }
            rows = judge_obligations(
                [item], cwd=root, granted={cmd}, run_id="run-a",
                artifacts={"calc.py": {"sha256": digest, "run_id": "run-a"}})
        row = rows[0]
        self.assertTrue(row["command_passed"])
        self.assertTrue(row["artifact_integrity"])
        self.assertFalse(row["criterion_verified"])
        self.assertEqual(row["state"], "unverified")
        self.assertNotIn("xác minh đúng câu", row["reason"])

    def test_contains_that_bai_khi_thieu_chuoi(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "calc.py").write_text("return 4\n", encoding="utf-8")
            item = {
                "schema": 1, "id": "need-5", "text": "ham cong tra ve nam",
                "validator": {
                    "kind": "contains", "path": "calc.py",
                    "must_contain": ["return 5"], "must_not_contain": [],
                },
            }
            rows = judge_obligations([item], cwd=root, run_id="run-a")
        self.assertFalse(rows[0]["criterion_verified"])
        self.assertEqual(rows[0]["state"], "failed")
        self.assertTrue(rows[0]["does_not_prove"])

    def test_contains_dat_khi_du_chuoi(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "calc.py").write_text("return 5\n", encoding="utf-8")
            item = {
                "schema": 1, "id": "has-5", "text": "tep co return 5",
                "validator": {
                    "kind": "contains", "path": "calc.py",
                    "must_contain": ["return 5"], "must_not_contain": ["return 4"],
                },
            }
            rows = judge_obligations([item], cwd=root, run_id="run-a")
        row = rows[0]
        self.assertTrue(row["criterion_verified"])
        self.assertIn("chuỗi", row["proves"])
        self.assertIn("không chạy", row["does_not_prove"])

    def test_json_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "out.json").write_text(json.dumps({"name": "a"}), encoding="utf-8")
            item = {
                "schema": 1, "id": "js", "text": "json co name",
                "validator": {
                    "kind": "json_keys", "path": "out.json",
                    "required": ["name"], "forbidden": ["token"], "expect": "object",
                },
            }
            rows = judge_obligations([item], cwd=root, run_id="run-a")
        self.assertTrue(rows[0]["criterion_verified"])
        self.assertIn("không kiểm giá trị", rows[0]["does_not_prove"])

    def test_shape_dung_duoi(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "note.py").write_text("x = 1\n", encoding="utf-8")
            item = {
                "schema": 1, "id": "sh", "text": "tep py",
                "validator": {"kind": "shape", "path": "note.py", "suffixes": [".py"],
                              "non_empty": True},
            }
            rows = judge_obligations([item], cwd=root, run_id="run-a")
        self.assertTrue(rows[0]["criterion_verified"])
        self.assertIn("không kiểm nội dung", rows[0]["does_not_prove"])

    def test_khong_co_validator_can_xac_nhan(self):
        rows = judge_obligations(
            [{"schema": 1, "id": "m", "text": "doan van co nguon"}], run_id="run-a")
        self.assertEqual(rows[0]["state"], "needs_confirmation")
        self.assertFalse(rows[0]["criterion_verified"])

    def test_behavior_chua_cap_quyen_khong_chay(self):
        cmd = _exit(0)
        item = {
            "schema": 1, "id": "b", "text": "lenh kiem",
            "validator": {
                "kind": "behavior", "cmd": cmd, "expects_exit": 0,
                "expects_stdout": "PASS",
                "does_not_prove": "khong kiem nhanh khac",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            rows = judge_obligations([item], cwd=Path(tmp), granted=set(), run_id="run-a")
        self.assertEqual(rows[0]["state"], "pending")
        self.assertFalse(rows[0]["command_passed"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
