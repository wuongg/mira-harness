"""Tập đo đầu-cuối, tách khỏi fixture sửa mã. Provider giả."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TrustEvalTest(unittest.TestCase):
    def test_cay_hien_tai_khong_loi_da_cham(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "trust.json"
            proc = subprocess.run(
                [sys.executable, str(ROOT / "tools" / "trust_eval.py"),
                 "--current-only", "--json-out", str(out)],
                cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
            self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
            data = json.loads(out.read_text(encoding="utf-8"))
            failed = [row["id"] for row in data["current"] if row.get("status") == "fail"]
            self.assertEqual(failed, [])
            self.assertTrue(any(row["status"] == "not_evaluated" for row in data["current"]))
            self.assertFalse(any(row.get("remaining") for row in data["current"]))
            self.assertTrue(all(row["status"] in ("pass", "fail", "not_evaluated")
                                for row in data["current"]))
            self.assertEqual(data["summary"]["failed"], [])
            self.assertIn("T-REAL", data["summary"]["not_evaluated"])

    def test_not_evaluated_khong_keo_exit_va_fail_that_moi_keo(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import trust_eval
        quiet, summary = trust_eval.decide([
            {"id": "T-NOOP", "status": "pass"},
            {"id": "T-REAL", "status": "not_evaluated",
             "detail": "khong co API tra phi duoc duyet"},
        ])
        self.assertEqual(quiet, 0)
        self.assertEqual(summary["not_evaluated"], ["T-REAL"])
        self.assertEqual(summary["failed"], [])
        self.assertEqual(summary["passed"], ["T-NOOP"])
        loud, bad = trust_eval.decide([
            {"id": "T-NOOP", "status": "fail"},
            {"id": "T-REAL", "status": "not_evaluated"},
        ])
        self.assertEqual(loud, 1)
        self.assertEqual(bad["failed"], ["T-NOOP"])
        self.assertEqual(bad["not_evaluated"], ["T-REAL"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
