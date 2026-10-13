"""Kiểm vận hành: checkpoint đứt, trần không nhân theo đội con, trace không chứa khóa."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mira import config, team
from mira.team import (
    ROLES_BY_LANE, TeamPlan, execute_plan, load_checkpoint, make_task,
    resume_team, write_checkpoint, CheckpointError,
)

SECRET = "sk-test-EXPOSE-0123456789"


class _Prov:
    name = "fake"

    def __init__(self, model, **_kw):
        self.model = model
        self.attempts = 1

    def available(self):
        return True

    def call(self, system, _user):
        if "VERIFIER" in system or "ORACLE" in system:
            text = '{"verdict":"PASS","reasons":["khop"],"evidence":[],"confidence":0.9}'
        else:
            text = "xong"
        return text, {"in": 10, "out": 0}


def _plan(cap: float) -> TeamPlan:
    plan = TeamPlan(
        task_text="lam viec X", lane=2, floor=2, floor_reason="thu",
        capability="write_external", gate_tier=3, gate_minutes=25.0,
        dual_approval=True, roles=ROLES_BY_LANE[2], roles_reason="thu",
        task=make_task("lam viec X", surface="write_external"), cap_usd=cap)
    plan.declared_price = (100000.0, 0.0)
    return plan


class OpsAuditTest(unittest.TestCase):
    def test_file_tam_dut_khong_de_len_checkpoint_cu(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_checkpoint(root, {
                "id": "r", "version": 1,
                "ledger": {"rows": [], "total_usd": 0.0},
            })
            team.checkpoint_path(root, "r").with_suffix(".json.tmp").write_text(
                "{dut", encoding="utf-8")
            self.assertEqual(load_checkpoint(root, "r")["id"], "r")

    def test_checkpoint_json_dut_thi_resume_thoat_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_checkpoint(root, {
                "id": "r", "version": 1,
                "ledger": {"rows": [], "total_usd": 0.0},
            })
            team.checkpoint_path(root, "r").write_text("{dut", encoding="utf-8")
            with self.assertRaises(CheckpointError):
                load_checkpoint(root, "r")
            code, res = resume_team(root, "r")
        self.assertEqual(code, 2)
        self.assertEqual(res["error"], "checkpoint hỏng")

    def test_hai_doi_con_khong_keo_verifier_qua_tran(self):
        old = dict(config.PRICES.get("sonnet-5.5") or {})
        config.PRICES["sonnet-5.5"] = {"in": 100000.0, "out": 0.0}
        try:
            with patch.object(team, "provider_for", lambda model, name=None, **kw: _Prov(model)):
                res = execute_plan(_plan(3.0), workers=2, depth=1, api_key="k")
        finally:
            if old:
                config.PRICES["sonnet-5.5"] = old
            else:
                config.PRICES.pop("sonnet-5.5", None)
        self.assertLessEqual(res["ledger"]["total_usd"], 3.0)
        self.assertNotIn("verifier", [s["role"] for s in res["steps"]])
        self.assertEqual(res["status"], "stopped_budget")

    def test_khoa_khong_vao_checkpoint(self):
        os.environ["ANTHROPIC_API_KEY"] = SECRET
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                with patch.object(team, "provider_for", lambda model, name=None, **kw: _Prov(model)):
                    res = execute_plan(
                        _plan(0.0), workers=1, depth=0, api_key=SECRET, root=root)
                blob = json.dumps(res)
                runs = list((root / ".mira" / "runs").glob("*/checkpoint.json"))
                disk = runs[0].read_text(encoding="utf-8")
        finally:
            os.environ.pop("ANTHROPIC_API_KEY", None)
        self.assertNotIn(SECRET, blob)
        self.assertNotIn(SECRET, disk)


if __name__ == "__main__":
    unittest.main()
