"""Đổi tiêu chí thì resume không chạy tiếp kế hoạch cũ."""
from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from frog.contract import contract_diff
from frog.intake import canonical_brief
from frog.team import checkpoint_path, cmd_team, resume_team, write_checkpoint


def _brief(goal: str, criteria: list[str], limits: list[str] | None = None) -> dict:
    return {
        "goal": goal,
        "deliverables": [],
        "acceptance_criteria": criteria,
        "constraints": limits or [],
        "assumptions": [],
        "questions": [],
        "per_role_hints": {"planner": "", "worker": "", "verifier": ""},
    }


class ContractTest(unittest.TestCase):
    def test_them_tieu_chi_lam_ke_hoach_cu_het_hieu_luc(self):
        old = _brief("tóm tắt", ["có một đoạn"])
        new = _brief("tóm tắt", ["có một đoạn", "có số liệu"])
        diff = contract_diff(old, new)
        self.assertTrue(diff["invalidates"])
        self.assertEqual(diff["added_criteria"], ["có số liệu"])

    def test_cung_brief_khong_huy(self):
        brief = _brief("tóm tắt", ["có một đoạn"])
        self.assertFalse(contract_diff(brief, json.loads(canonical_brief(brief)))["invalidates"])

    def test_resume_tu_choi_brief_da_doi(self):
        old = _brief("tóm tắt", ["có một đoạn"])
        new = _brief("tóm tắt", ["có số liệu"])
        calls = []

        def boom(*_a, **_k):
            calls.append(1)
            raise AssertionError("không được gọi model")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_checkpoint(root, {
                "id": "run1",
                "version": 1,
                "next_index": 0,
                "task": "tóm tắt tài liệu công khai",
                "steps": [],
                "ledger": {"rows": [], "total_usd": 0.0, "total_in": 0,
                           "total_out": 0, "subagent_runs": 0},
                "staging": None,
                "status": "ok",
                "fail_reason": None,
                "brief": old,
                "brief_hash": "abc",
                "hints": {"surface": "read_only", "labels": ["public"], "records": 10,
                          "dollars": 0, "reversibility": "C1", "output_type": "free_string"},
                "workers": 1,
            })
            with patch("frog.team.provider_for", boom):
                code, res = resume_team(root, "run1", brief=new)
            self.assertEqual(code, 2)
            self.assertIn("yêu cầu đã đổi", res["error"])
            self.assertEqual(calls, [])
            self.assertTrue(res["contract_diff"]["invalidates"])
            saved = json.loads(checkpoint_path(root, "run1").read_text(encoding="utf-8"))
            self.assertEqual(saved["brief"]["acceptance_criteria"], ["có một đoạn"])

    def test_deliverable_doi_lam_het_hieu_luc(self):
        old = _brief("tóm tắt", ["có một đoạn"])
        new = _brief("tóm tắt", ["có một đoạn"])
        new["deliverables"] = ["bảng số"]
        diff = contract_diff(old, new)
        self.assertTrue(diff["invalidates"])
        self.assertIn("deliverable thêm: bảng số", diff["lines"])

    def test_chi_doi_cau_hoi_van_khong_ap_brief_moi(self):
        old = _brief("tóm tắt", ["có một đoạn"])
        new = _brief("tóm tắt", ["có một đoạn"])
        new["questions"] = ["kỳ nào?"]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_checkpoint(root, {
                "id": "run1", "version": 1, "next_index": 0,
                "task": "tóm tắt tài liệu công khai", "steps": [],
                "ledger": {"rows": [], "total_usd": 0.0, "total_in": 0,
                           "total_out": 0, "subagent_runs": 0},
                "staging": None, "status": "ok", "fail_reason": None,
                "brief": old, "brief_hash": "abc",
                "hints": {"surface": "read_only", "labels": ["public"], "records": 10,
                          "dollars": 0, "reversibility": "C1", "output_type": "free_string"},
                "workers": 1,
            })
            code, res = resume_team(root, "run1", brief=new)
            self.assertEqual(code, 2)
            self.assertIn("hash đã lưu", " ".join(res["contract_diff"]["lines"]))
            saved = json.loads(checkpoint_path(root, "run1").read_text(encoding="utf-8"))
            self.assertEqual(saved["brief"]["questions"], [])

    def test_cli_in_ly_do_va_khong_ghi_de_brief(self):
        old = _brief("tóm tắt", ["có một đoạn"])
        new = _brief("tóm tắt", ["có một đoạn"])
        new["deliverables"] = ["bảng số"]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_checkpoint(root, {
                "id": "run1",
                "version": 1,
                "next_index": 0,
                "task": "tóm tắt tài liệu công khai",
                "steps": [],
                "ledger": {"rows": [], "total_usd": 0.0, "total_in": 0,
                           "total_out": 0, "subagent_runs": 0},
                "staging": None,
                "status": "ok",
                "fail_reason": None,
                "brief": old,
                "brief_hash": "abc",
                "contract": {"version": 1, "hash": "abc", "parent": None},
                "hints": {"surface": "read_only", "labels": ["public"], "records": 10,
                          "dollars": 0, "reversibility": "C1", "output_type": "free_string"},
                "workers": 1,
            })
            brief_path = root / "new.json"
            brief_path.write_text(json.dumps(new), encoding="utf-8")
            prev = os.getcwd()
            os.chdir(root)
            try:
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = cmd_team(SimpleNamespace(
                        resume="run1", task=None, brief=str(brief_path),
                        provider=None, model=None, base_url=None, api_key=None,
                        max_tokens=64, oracle=None, require_evidence=False))
            finally:
                os.chdir(prev)
            text = buf.getvalue()
            self.assertEqual(code, 2)
            self.assertIn("deliverable thêm: bảng số", text)
            self.assertIn("không tiếp tục kế hoạch cũ", text)
            saved = json.loads(checkpoint_path(root, "run1").read_text(encoding="utf-8"))
            self.assertEqual(saved["brief"]["deliverables"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
