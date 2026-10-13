"""selftest không được phụ thuộc thư mục out có sẵn."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mira  # noqa: E402
from mira import stats  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


class SelftestIsolatedTest(unittest.TestCase):
    def test_selftest_khong_can_thu_muc_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "metrics.json").write_text('{"n": 1, "ledger": {"total_usd": 0}}', encoding="utf-8")
            (d / "trace.jsonl").write_text('{"id": "T1", "lane_final": 0, "stratum": "a"}\n',
                                           encoding="utf-8")
            metrics, trace, _path = stats._load(str(d))
        self.assertEqual(metrics["n"], 1)
        self.assertEqual(len(trace), 1)
        others = [p for p in (ROOT / "tests").glob("test_*.py") if p.name != "test_selftest_isolated.py"]
        blob = "\n".join(p.read_text(encoding="utf-8") for p in others)
        self.assertNotIn('Path("out")', blob)
        self.assertNotIn("out-v112", blob)

    def test_stats_thieu_file_bao_loi_ro(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError) as caught:
                stats._load(tmp)
        self.assertIn("metrics.json", str(caught.exception))

    def test_ba_nguon_version_khop(self):
        project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn('version = {attr = "mira.__version__"}', project)
        self.assertIn(mira.__version__, readme)
        self.assertEqual(mira.__version__, "2.5.0")
        from mira.cli import VERSION
        self.assertEqual(VERSION, mira.__version__)


if __name__ == "__main__":
    unittest.main(verbosity=2)
