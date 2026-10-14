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
            failed = [row["id"] for row in data["current"] if row.get("fail")]
            self.assertEqual(failed, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
