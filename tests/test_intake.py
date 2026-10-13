"""Tầng 1: schema, trần hỏi, duyệt brief, file brief."""
from __future__ import annotations

import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from mira import team


def _brief(**kw) -> dict:
    obj = {
        "goal": "soạn báo cáo",
        "deliverables": ["bao cao"],
        "acceptance_criteria": ["có số liệu"],
        "constraints": [],
        "assumptions": [],
        "questions": [],
        "per_role_hints": {"planner": "", "worker": "", "verifier": ""},
    }
    obj.update(kw)
    return obj


class _Prov:
    def __init__(self, replies):
        self.replies = list(replies)
        self.systems: list[str] = []
        self.name = "anthropic"

    def available(self) -> bool:
        return True

    def call(self, system: str, user: str):
        self.systems.append(system or "")
        text = self.replies.pop(0) if self.replies else json.dumps(_brief(), ensure_ascii=False)
        return text, {"in": 2, "out": 2}


def _ns(root: Path, **kw) -> Namespace:
    base = dict(
        task="soạn báo cáo nội bộ", labels="internal", surface="read_only",
        records=20, dollars=0.0, reversibility="C1", output_type="free_string",
        workers=1, sub_depth=0, dry_run=False, provider="anthropic", model=None,
        base_url=None, max_tokens=64, approve=False, out=None, api_key="k",
        price_in="1,1", oracle="off", intake="on", clarify_max=3, brief=None,
    )
    base.update(kw)
    return Namespace(**base)


class IntakeTier1Test(unittest.TestCase):
    def _cmd(self, prov, ns, answers=None):
        pending = list(answers or [])

        def fake_input(_prompt=""):
            return pending.pop(0) if pending else "n"

        with patch("mira.team.provider_for", lambda *a, **k: prov), \
             patch("builtins.input", fake_input):
            return team.cmd_team(ns)

    def test_thieu_goal_thi_dung(self):
        prov = _Prov([json.dumps(_brief(goal="  "))])
        with tempfile.TemporaryDirectory() as tmp:
            code = self._cmd(prov, _ns(Path(tmp)))
        self.assertEqual(code, 8)
        self.assertFalse(any("PLANNER" in s for s in prov.systems))

    def test_thieu_acceptance_thi_dung(self):
        prov = _Prov([json.dumps(_brief(acceptance_criteria=[]))])
        with tempfile.TemporaryDirectory() as tmp:
            code = self._cmd(prov, _ns(Path(tmp)))
        self.assertEqual(code, 8)
        self.assertFalse(any("PLANNER" in s for s in prov.systems))

    def test_vuot_clarify_max_thi_dung_hoi(self):
        asked = []

        def ask_count(prompt):
            asked.append(prompt)
            return "làm rõ rồi"

        first = json.dumps(_brief(questions=["mục tiêu là gì?"]))
        second = json.dumps(_brief(questions=["còn gì nữa?"]))
        prov = _Prov([first, second])
        with tempfile.TemporaryDirectory() as tmp:
            with patch("mira.team.provider_for", lambda *a, **k: prov), \
                 patch("builtins.input", ask_count):
                code = team.cmd_team(_ns(Path(tmp), clarify_max=1))
        self.assertEqual(len(asked), 2)
        self.assertTrue(any("mục tiêu" in item for item in asked))
        self.assertTrue(any("Duyệt brief" in item for item in asked))
        self.assertNotIn("còn gì nữa", " ".join(asked))
        self.assertEqual(code, 8)

        prov2 = _Prov([json.dumps(_brief(goal=""))])
        asked2 = []
        with tempfile.TemporaryDirectory() as tmp:
            with patch("mira.team.provider_for", lambda *a, **k: prov2), \
                 patch("builtins.input", lambda p: asked2.append(p) or "n"):
                code2 = team.cmd_team(_ns(Path(tmp), clarify_max=0))
        self.assertEqual(code2, 8)
        self.assertEqual(asked2, [])
        self.assertFalse(any("PLANNER" in s for s in prov2.systems))

    def test_khong_duyet_brief_thi_khong_goi_planner(self):
        prov = _Prov([json.dumps(_brief())])
        with tempfile.TemporaryDirectory() as tmp:
            code = self._cmd(prov, _ns(Path(tmp)), answers=["n"])
        self.assertEqual(code, 8)
        self.assertTrue(any("INTAKE" in s for s in prov.systems))
        self.assertFalse(any("PLANNER" in s for s in prov.systems))

    def test_brief_file_hop_le_bo_tang_1(self):
        prov = _Prov([])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "brief.json"
            path.write_text(json.dumps(_brief()), encoding="utf-8")
            code = self._cmd(prov, _ns(Path(tmp), brief=str(path), out=str(Path(tmp) / "out")))
        self.assertFalse(any("INTAKE" in s for s in prov.systems))
        self.assertNotEqual(code, 8)

    def test_brief_file_hong_schema(self):
        prov = _Prov([])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "brief.json"
            path.write_text('{"goal":""}', encoding="utf-8")
            code = self._cmd(prov, _ns(Path(tmp), brief=str(path)))
        self.assertEqual(code, 8)
        self.assertEqual(prov.systems, [])

    def test_dry_run_khong_goi_model(self):
        prov = _Prov([])
        with tempfile.TemporaryDirectory() as tmp:
            code = self._cmd(prov, _ns(Path(tmp), dry_run=True))
        self.assertEqual(code, 0)
        self.assertEqual(prov.systems, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
