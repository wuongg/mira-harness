"""Đổi tiêu chí thì resume không chạy tiếp kế hoạch cũ."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mira.contract import contract_diff
from mira.intake import canonical_brief
from mira.team import resume_team, write_checkpoint


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
            with patch("mira.team.provider_for", boom):
                code, res = resume_team(root, "run1", brief=new)
        self.assertEqual(code, 2)
        self.assertIn("yêu cầu đã đổi", res["error"])
        self.assertEqual(calls, [])
        self.assertTrue(res["contract_diff"]["invalidates"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
