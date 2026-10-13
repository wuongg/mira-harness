"""PASS không đủ khi tiêu chí chưa có bằng chứng. Không brief thì hành vi cũ."""
from __future__ import annotations

import json
import os
import shlex
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mira import team
from mira.obligations import judge_obligations


_PASS = json.dumps({"verdict": "PASS", "reasons": ["khop"], "evidence": [], "confidence": 0.9})
_PASS_QUOTED = json.dumps({
    "verdict": "PASS", "reasons": ["khop"],
    "evidence": ["app.py có hàm mới"], "confidence": 0.9,
})


class _Prov:
    text = _PASS

    def __init__(self, *_a, **_k):
        self.name = "fake"
        self.attempts = 1

    def available(self):
        return True

    def call(self, system, _user):
        if "VERIFIER" in system:
            return _Prov.text, {"in": 2, "out": 1}
        return "xong", {"in": 2, "out": 1}


def _brief():
    return {
        "goal": "sửa app",
        "deliverables": [],
        "acceptance_criteria": ["app.py có hàm mới"],
        "constraints": ["không xoá test"],
        "assumptions": [],
        "questions": [],
        "per_role_hints": {"planner": "", "worker": "", "verifier": ""},
    }


class ObligationTest(unittest.TestCase):
    def setUp(self):
        self.plan = team.build_plan(
            "cập nhật sổ nội bộ", surface="write_external",
            labels=["internal"], records=10, dollars=0, reversibility="C1")
        self.plan.declared_price = (1000.0, 0.0)
        self.assertEqual(self.plan.roles, ["worker", "verifier"])

    def _run(self):
        with tempfile.TemporaryDirectory() as tmp, patch("mira.team.provider_for", _Prov):
            return team.execute_plan(
                self.plan, provider_name="anthropic", api_key="k",
                root=Path(tmp), on_step=lambda _m: None)

    def test_pass_khong_trich_thi_khong_giao(self):
        _Prov.text = _PASS
        self.plan.brief = _brief()
        self.plan.require_evidence = True
        res = self._run()
        self.assertEqual(res["status"], "withheld")
        self.assertEqual(res["obligations"][0]["state"], "unproven")
        self.assertIn("chưa có bằng chứng", res["fail_reason"])

    def test_khong_brief_van_nhan_pass(self):
        _Prov.text = _PASS
        self.plan.brief = None
        res = self._run()
        self.assertEqual(res["status"], "ok")
        self.assertIsNone(res["obligations"])

    def test_chep_tieu_chi_khong_phai_proof(self):
        rows = judge_obligations(
            ["app.py có hàm mới"],
            [{"verdict_parsed": {"evidence": ["app.py có hàm mới"]}}],
            {"changed": ["app.py"]})
        self.assertEqual(rows[0]["state"], "unproven")
        self.assertIsNone(rows[0]["ref"])

    def test_check_thoat_0_co_tham_chieu(self):
        cmd = shlex.join([sys.executable, "-c", "import sys; raise SystemExit(0)"])
        with tempfile.TemporaryDirectory() as tmp:
            rows = judge_obligations([f"check: {cmd}"], [], None, cwd=Path(tmp))
        self.assertEqual(rows[0]["state"], "proven")
        self.assertEqual(rows[0]["ref"]["exit"], 0)
        self.assertEqual(rows[0]["ref"]["cmd"], cmd)

    def test_check_thoat_0_thi_giao(self):
        cmd = shlex.join([sys.executable, "-c", "import sys; raise SystemExit(0)"])
        self.plan.brief = _brief()
        self.plan.brief["acceptance_criteria"] = [f"check: {cmd}"]
        self.plan.require_evidence = True
        res = self._run()
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["obligations"][0]["state"], "proven")
        self.assertEqual(res["obligations"][0]["ref"]["kind"], "check")

    def test_check_thoat_loi_khong_giao(self):
        cmd = shlex.join([sys.executable, "-c", "import sys; raise SystemExit(1)"])
        self.plan.brief = _brief()
        self.plan.brief["acceptance_criteria"] = [f"check: {cmd}"]
        self.plan.require_evidence = True
        res = self._run()
        self.assertEqual(res["status"], "withheld")
        self.assertEqual(res["obligations"][0]["state"], "failed")
        self.assertEqual(res["obligations"][0]["ref"]["exit"], 1)

    def test_file_doi_that_khong_chung_minh_dung(self):
        _Prov.text = _PASS
        self.plan.brief = _brief()
        self.plan.task_text = "sửa app.py cho gọn"

        def fake_turn(**kw):
            (Path(kw["session"].root) / "app.py").write_text("def moi():\n    return 1\n", encoding="utf-8")
            return {"final": "đã sửa", "usage": {"in": 2, "out": 1}, "seconds": 0}

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app.py").write_text("old\n", encoding="utf-8")
            plan = team.build_plan(
                "sửa app.py cho gọn", surface="write_external",
                labels=["internal"], records=10, dollars=0, reversibility="C1")
            plan.declared_price = (1000.0, 0.0)
            plan.brief = _brief()
            plan.require_evidence = True
            with patch("mira.team.provider_for", _Prov), patch("mira.agent.run_turn", fake_turn):
                res = team.execute_plan(plan, api_key="k", root=root, on_step=lambda _m: None)
        self.assertEqual(res["obligations"][0]["state"], "unproven")
        self.assertEqual(res["status"], "withheld")

    def test_duong_dan_tho_tren_windows_van_chay(self):
        if os.name != "nt":
            self.skipTest("backslash chỉ là escape trên Windows")
        cmd = f'{sys.executable} -c "import sys; raise SystemExit(0)"'
        with tempfile.TemporaryDirectory() as tmp:
            rows = judge_obligations([f"check: {cmd}"], cwd=Path(tmp))
        self.assertEqual(rows[0]["state"], "proven")
        self.assertEqual(rows[0]["ref"]["exit"], 0)
        bad = f'{sys.executable} -c "import sys; raise SystemExit(2)"'
        with tempfile.TemporaryDirectory() as tmp:
            rows = judge_obligations([f"check: {bad}"], cwd=Path(tmp))
        self.assertEqual(rows[0]["state"], "failed")
        self.assertEqual(rows[0]["ref"]["exit"], 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
