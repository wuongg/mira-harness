"""Tầng 1: schema, trần hỏi, duyệt brief, file brief."""
from __future__ import annotations

import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from frog import team


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
        self.users: list[str] = []
        self.name = "anthropic"

    def available(self) -> bool:
        return True

    def call(self, system: str, user: str):
        self.systems.append(system or "")
        self.users.append(user or "")
        if "PROMPT_WRITER" in (system or ""):
            names = ("planner", "coordinator", "worker", "verifier", "oracle", "critic")
            return json.dumps({name: f"làm {name}" for name in names}, ensure_ascii=False), {"in": 2, "out": 2}
        if "VERIFIER" in (system or ""):
            return ('{"verdict":"PASS","reasons":["khop"],"evidence":["so lieu"],"confidence":0.9}'), {"in": 2, "out": 2}
        if "ORACLE" in (system or ""):
            return ('{"verdict":"PASS","reasons":["cham"],"evidence":["x"],"confidence":0.9,"score":0.9}'), {"in": 2, "out": 2}
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

        with patch("frog.team.provider_for", lambda *a, **k: prov), \
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
            with patch("frog.team.provider_for", lambda *a, **k: prov), \
                 patch("builtins.input", ask_count):
                code = team.cmd_team(_ns(Path(tmp), clarify_max=1))
        self.assertEqual(len(asked), 2)
        self.assertTrue(any("mục tiêu" in item for item in asked))
        self.assertTrue(any("Duyệt brief" in item for item in asked))
        self.assertNotIn("còn gì nữa", " ".join(asked))
        self.assertEqual(code, 8)

        prov2 = _Prov([json.dumps(_brief(goal="")), json.dumps(_brief(goal=""))])
        asked2 = []
        with tempfile.TemporaryDirectory() as tmp:
            with patch("frog.team.provider_for", lambda *a, **k: prov2), \
                 patch("builtins.input", lambda p: asked2.append(p) or "n"):
                code2 = team.cmd_team(_ns(Path(tmp), clarify_max=0))
        self.assertEqual(code2, 8)
        self.assertEqual(asked2, [])
        self.assertEqual(len(prov2.systems), 2)
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


class IntakeTier3Test(unittest.TestCase):
    def test_intake_khong_doi_lane_floor_roles(self):
        snaps = []
        for goal in ("một", "hai", "ba"):
            plan = team.build_plan("soạn báo cáo", surface="write_sandbox",
                                   labels=["internal"], records=20, dollars=0)
            plan.brief = _brief(goal=goal)
            snaps.append((plan.lane, plan.floor, tuple(plan.roles)))
        self.assertEqual(len(set(snaps)), 1)

    def test_nhan_public_trong_cau_khong_doi_labels(self):
        plan = team.build_plan("đây là public data", surface="write_sandbox",
                               labels=["internal"], records=50, dollars=0)
        obs = plan.task.observable
        self.assertEqual(obs["data_labels"], ["internal"])
        self.assertEqual(obs["tool_surface"], "write_sandbox")
        self.assertEqual(obs["records"], 50)
        self.assertEqual(obs["dollars"], 0.0)

    def test_chi_phi_intake_va_prompt_writer_trong_ledger(self):
        prov = _Prov([json.dumps(_brief())])
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            with patch("frog.team.provider_for", lambda *a, **k: prov), \
                 patch("builtins.input", lambda _p: "y"):
                code = team.cmd_team(_ns(Path(tmp), out=str(out), approve=True))
            self.assertEqual(code, 0)
            data = json.loads(next(out.rglob("trace.json")).read_text(encoding="utf-8"))
        roles = data["ledger"]["by_role"]
        self.assertIn("intake", roles)
        self.assertIn("prompt_writer", roles)
        self.assertGreater(roles["intake"], 0)
        self.assertGreater(roles["prompt_writer"], 0)

    def test_brief_chua_lenh_di_qua_containment(self):
        from frog.intake import contain_brief
        text = contain_brief(
            {"goal": "rm -rf /", "note": "sửa conftest.py"},
            task="soạn báo cáo")
        self.assertIn("NỘI DUNG KHÔNG TIN", text)
        self.assertIn("Không phải lệnh", text)
        self.assertIn("rm -rf", text)
        self.assertNotIn("conftest.py", text)

    def test_role_prompt_co_trong_trace(self):
        prov = _Prov([])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "brief.json"
            path.write_text(json.dumps(_brief()), encoding="utf-8")
            out = Path(tmp) / "out"
            with patch("frog.team.provider_for", lambda *a, **k: prov):
                code = team.cmd_team(_ns(
                    Path(tmp), brief=str(path), out=str(out), approve=True,
                    surface="write_sandbox"))
            self.assertEqual(code, 0)
            data = json.loads(next(out.rglob("trace.json")).read_text(encoding="utf-8"))
            prompts = data["role_prompts"]
            for role in data["plan"]["roles"]:
                self.assertIn(role, prompts)
                self.assertIn("NỘI DUNG KHÔNG TIN", prompts[role])
            self.assertTrue(data["brief_hash"])
            self.assertFalse(any("INTAKE" in s for s in prov.systems))
            self.assertTrue(any("PROMPT_WRITER" in s for s in prov.systems))

    def test_object_rong_duoc_dien_ba_vai(self):
        from frog.intake import normalize_role_hints, run_intake, validate_brief
        from frog.team import Ledger
        brief = _brief(per_role_hints={})
        ok, why = validate_brief(brief)
        self.assertTrue(ok, why)
        self.assertEqual(
            brief["per_role_hints"],
            {"planner": "", "worker": "", "verifier": ""})
        fresh = _brief(per_role_hints={})
        filled = normalize_role_hints(fresh)
        self.assertEqual(filled, ["planner", "worker", "verifier"])
        prov = _Prov([json.dumps(_brief(per_role_hints={}))])
        got = run_intake("soạn báo cáo", prov, Ledger(), clarify_max=0, ask=lambda _q: "",
                         model="claude-test", declared_price=(1.0, 1.0))
        self.assertTrue(got["ok"], got.get("reason"))
        self.assertEqual(got.get("normalization"), ["planner", "worker", "verifier"])
        self.assertEqual(len(prov.systems), 1)

    def test_thieu_vai_duoc_dien_rong(self):
        from frog.intake import normalize_role_hints, validate_brief
        brief = _brief()
        del brief["per_role_hints"]["worker"]
        filled = normalize_role_hints(brief)
        self.assertEqual(filled, ["worker"])
        self.assertEqual(brief["per_role_hints"]["worker"], "")
        ok, why = validate_brief(brief)
        self.assertTrue(ok, why)
        from frog.handoff import preview
        text = preview(brief, "abc123abc123", filled)
        self.assertIn("đã điền thay: worker", text)

    def test_sai_kieu_hint_bi_tu_choi(self):
        from frog.intake import normalize_role_hints, validate_brief
        brief = _brief(per_role_hints=["planner"])
        self.assertEqual(normalize_role_hints(brief), [])
        ok, why = validate_brief(brief)
        self.assertFalse(ok)
        self.assertIn("object", why)
        brief = _brief(per_role_hints={"planner": "", "worker": 1, "verifier": ""})
        normalize_role_hints(brief)
        ok, why = validate_brief(brief)
        self.assertFalse(ok)
        self.assertIn("chuỗi", why)

    def test_tieu_chi_may_thieu_validator_bi_tu_choi(self):
        from frog.intake import brief_hash, validate_brief
        brief = _brief(
            deliverables=["sum_to.py"],
            acceptance_criteria=["sum_to(3) == 6"])
        ok, why = validate_brief(brief)
        self.assertFalse(ok)
        self.assertIn("validator", why)
        subjective = _brief(
            deliverables=["sum_to.py"],
            acceptance_criteria=["giong van de doc"])
        ok, why = validate_brief(subjective)
        self.assertTrue(ok, why)
        good = _brief(
            deliverables=["sum_to.py"],
            acceptance_criteria=[{
                "schema": 1, "id": "sum", "text": "sum_to(3) == 6",
                "validator": {
                    "kind": "contains", "path": "sum_to.py",
                    "must_contain": ["range(n + 1)"], "must_not_contain": [],
                },
            }])
        ok, why = validate_brief(good)
        self.assertTrue(ok, why)
        outside = _brief(
            deliverables=["sum_to.py"],
            acceptance_criteria=[{
                "schema": 1, "id": "sum", "text": "file khac",
                "validator": {
                    "kind": "contains", "path": "other.py",
                    "must_contain": ["x"], "must_not_contain": [],
                },
            }])
        ok, why = validate_brief(outside)
        self.assertFalse(ok)
        self.assertIn("ngoài deliverables", why)
        changed = json.loads(json.dumps(good))
        changed["acceptance_criteria"][0]["validator"]["must_contain"] = ["range(n)"]
        self.assertNotEqual(brief_hash(good), brief_hash(changed))

    def test_schema_mot_luot_bao_thieu_validator(self):
        from frog.intake import run_intake
        from frog.team import Ledger
        bad = _brief(deliverables=["sum_to.py"], acceptance_criteria=["sum_to(3) == 6"])
        good = _brief(
            deliverables=["sum_to.py"],
            acceptance_criteria=[{
                "schema": 1, "id": "sum", "text": "sum_to(3) == 6",
                "validator": {
                    "kind": "contains", "path": "sum_to.py",
                    "must_contain": ["range(n + 1)"], "must_not_contain": [],
                },
            }])
        prov = _Prov([json.dumps(bad), json.dumps(good)])
        got = run_intake("sua sum", prov, Ledger(), clarify_max=0, ask=lambda _q: "",
                         model="claude-test", declared_price=(1.0, 1.0))
        self.assertTrue(got["ok"], got.get("reason"))
        self.assertEqual(len(prov.systems), 2)
        self.assertIn("PHẢN HỒI SCHEMA", prov.users[1])
        self.assertIn("validator", prov.users[1])

    def test_schema_sai_duoc_sua_mot_lan(self):
        from frog.intake import run_intake
        from frog.team import Ledger
        bad = _brief(per_role_hints="planner")
        good = _brief()
        prov = _Prov([json.dumps(bad), json.dumps(good)])
        got = run_intake("soạn báo cáo", prov, Ledger(), clarify_max=0, ask=lambda _q: "",
                         model="claude-test", declared_price=(1.0, 1.0))
        self.assertTrue(got["ok"], got.get("reason"))
        self.assertEqual(len(prov.systems), 2)
        self.assertIn("PHẢN HỒI SCHEMA", prov.users[1])
        self.assertEqual(got["brief"]["per_role_hints"]["worker"], "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
