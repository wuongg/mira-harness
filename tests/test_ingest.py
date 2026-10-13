"""Ingest trace team: nguồn real, không bịa 0, không đè shadow."""
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from mira.ingest import ingest_dir
from mira.stats import render


_NULL_KEYS = (
    "D1_compress_rate",
    "D2_compress_rate",
    "D3_stop_rate",
    "D4_violation_rate",
    "t1b_recall_on_missed",
    "t1b_precision",
    "t1b_false_alarm_rate",
)


class IngestTest(unittest.TestCase):
    def test_ingest_team_ghi_nguon_real(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = {
                "status": "ok",
                "steps": [
                    {"role": "worker", "text": "xong", "seconds": 1.0},
                    {"role": "verifier", "text": "PASS"},
                ],
                "ledger": {"total_usd": 1.5},
                "plan": {"lane": 1},
                "verifier_verdict": "PASS",
                "oracle_score": None,
                "promoted": [],
            }
            (root / "trace.json").write_text(json.dumps(result), encoding="utf-8")
            (root / "result.md").write_text("ket qua", encoding="utf-8")
            code = ingest_dir(root)
            self.assertEqual(code, 0)
            metrics = json.loads((root / "metrics.json").read_text(encoding="utf-8"))
            self.assertEqual(metrics["data_source"], "real")
            self.assertEqual(metrics["ledger"]["total_usd"], 1.5)
            self.assertIsNone(metrics["D1_compress_rate"])
            self.assertEqual(metrics["shadow"]["action_taken"], 1)

    def test_shadow_van_synthetic(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            metrics = {
                "n": 1,
                "labeled_taskset": {"label_source": "NHÃN TỔNG HỢP (synthetic) — KHÔNG phải nhãn người"},
                "ledger": {"total_usd": 1},
                "audit_hours_per_week": 0,
                "VC_escalate_rate": 0,
                "dual_approval_rate": 0,
                "latency_overall": {"p95": 0},
                "lane_distribution": {"0": 1},
                "shadow": {"action_taken": 0, "note": ""},
            }
            blob = json.dumps(metrics, ensure_ascii=False, indent=2) + "\n"
            (root / "metrics.json").write_text(blob, encoding="utf-8")
            (root / "trace.jsonl").write_text(
                json.dumps({"guards": {"D1": 0}, "truth": {"injection_present": False},
                            "stratum": "a", "lane_final": 0}) + "\n",
                encoding="utf-8")
            before = (root / "metrics.json").read_bytes()
            code = ingest_dir(root)
            self.assertEqual(code, 2)
            self.assertEqual((root / "metrics.json").read_bytes(), before)
            buf = io.StringIO()
            with redirect_stdout(buf):
                render(str(root))
            self.assertIn("nguồn dữ liệu: synthetic", buf.getvalue())

    def test_thieu_guards_khong_thanh_so_0(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "trace.json").write_text(json.dumps({
                "status": "ok", "steps": [{"role": "worker", "text": "a"}],
                "ledger": {"total_usd": 0.2}, "plan": {"lane": 0}, "promoted": ["a.py"],
            }), encoding="utf-8")
            self.assertEqual(ingest_dir(root), 0)
            metrics = json.loads((root / "metrics.json").read_text(encoding="utf-8"))
            for key in _NULL_KEYS:
                self.assertIsNone(metrics[key], key)
                self.assertNotEqual(metrics[key], 0)

    def test_khong_goi_provider(self):
        def boom(*_a, **_k):
            raise AssertionError("không được dựng provider")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "trace.json").write_text(json.dumps({
                "status": "withheld", "steps": [], "ledger": {"total_usd": 0},
                "plan": {"lane": 0},
            }), encoding="utf-8")
            with patch("mira.team.provider_for", boom), patch("mira.providers.provider_for", boom):
                self.assertEqual(ingest_dir(root), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
