"""P1-02: bằng chứng trong staging trước khi nhận điểm oracle."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from frog import team

_PASS = json.dumps({"verdict": "PASS", "reasons": ["đủ"], "evidence": [], "confidence": 1})
_ORACLE = json.dumps({"verdict": "PASS", "reasons": ["đủ"], "evidence": [],
                      "confidence": 1, "score": 0.9})


class _Prov:
    name = "anthropic"

    def available(self) -> bool:
        return True

    def call(self, system, user, **_k):
        if "VERIFIER" in system:
            text = _PASS
        elif "ORACLE" in system:
            text = _ORACLE
        else:
            text = "1. bước"
        return text, {"in": 2, "out": 2}


def _turn(write: bool, text: str):
    def run_turn(task, session, **_k):
        if write:
            (Path(session.root) / "app.py").write_text("changed\n", encoding="utf-8")
        return {"final": text, "usage": {"in": 2, "out": 2}, "seconds": 0.1}
    return run_turn


def _run(task: str, write: bool, text: str) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "app.py").write_text("old\n", encoding="utf-8")
        plan = team.build_plan(task, surface="write_external", records=5000, dollars=3000)
        with patch("frog.agent.run_turn", _turn(write, text)), \
             patch("frog.team.provider_for", lambda *a, **k: _Prov()):
            return team.execute_plan(plan, root=root, oracle="on")


class EvidenceTest(unittest.TestCase):
    def test_pytest_do_mac_score_cao_van_withheld(self):
        task = 'sửa app.py rồi chạy python -c "import sys; raise SystemExit(1)"'
        res = _run(task, True, "xong")
        self.assertEqual(res["status"], "withheld")
        self.assertGreaterEqual(res["oracle_score"], 0.7)
        self.assertEqual(res["staging_evidence"]["exit"], 1)

    def test_diff_trong_worker_noi_da_sua_bi_fail(self):
        res = _run("sửa app.py cho gọn", False, "đã sửa app.py")
        self.assertEqual(res["status"], "withheld")
        self.assertTrue(res["staging_evidence"]["empty_diff"])
        self.assertTrue(res["staging_evidence"]["claimed"])

    def test_diff_co_va_pytest_xanh_thi_score_duoc_dung(self):
        task = 'sửa app.py rồi chạy python -c "import sys; raise SystemExit(0)"'
        res = _run(task, True, "xong")
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["oracle_score"], 0.9)
        self.assertEqual(res["staging_evidence"]["exit"], 0)
        self.assertFalse(res["staging_evidence"]["empty_diff"])

    def test_lenh_trong_loi_model_khong_duoc_chay(self):
        text = 'python -c "open(\'hacked.txt\',\'w\').write(\'x\')"'
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app.py").write_text("old\n", encoding="utf-8")
            plan = team.build_plan("sửa app.py cho gọn", surface="write_external",
                                   records=5000, dollars=3000)
            with patch("frog.agent.run_turn", _turn(False, text)), \
                 patch("frog.team.provider_for", lambda *a, **k: _Prov()):
                res = team.execute_plan(plan, root=root, oracle="on")
            staging = Path(res["staging"])
            self.assertEqual(res["staging_evidence"]["cmd"], "")
            self.assertFalse((staging / "hacked.txt").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
