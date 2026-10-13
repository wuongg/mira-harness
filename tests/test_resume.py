"""Checkpoint sau mỗi bước và resume không tính lại tiền."""
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

from mira import team


class _Fake:
    calls: list[str] = []

    def __init__(self, *_a, **_k):
        self.name = "fake"
        self.attempts = 1

    def available(self) -> bool:
        return True

    def call(self, system: str, _user: str):
        _Fake.calls.append("verifier" if "VERIFIER" in system else "worker")
        if "VERIFIER" in system:
            if _Fake.fail:
                text = '{"verdict":"FAIL","reasons":["thieu"],"evidence":[],"confidence":0.2}'
            else:
                text = '{"verdict":"PASS","reasons":["khop"],"evidence":["a"],"confidence":0.9}'
        else:
            text = "KẾT QUẢ xong"
        return text, {"in": 10, "out": 0}


_Fake.fail = False


def _provider(*_a, **_k):
    return _Fake()


class ResumeTest(unittest.TestCase):
    def setUp(self):
        _Fake.calls = []
        _Fake.fail = False
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.plan = team.build_plan(
            "cập nhật sổ nội bộ", surface="write_external",
            labels=["internal"], records=10, dollars=0, reversibility="C1")
        self.plan.declared_price = (1000.0, 0.0)
        self.assertEqual(self.plan.roles, ["worker", "verifier"])

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self):
        with patch("mira.team.provider_for", _provider):
            return team.execute_plan(
                self.plan, provider_name="anthropic", api_key="k",
                root=self.root, on_step=lambda _m: None)

    def test_moi_buoc_ghi_checkpoint(self):
        seen = []
        real = team.write_checkpoint

        def spy(root, payload):
            seen.append(payload["next_index"])
            real(root, payload)

        with patch("mira.team.write_checkpoint", spy):
            res = self._run()
        self.assertEqual(seen[:2], [1, 2])
        data = json.loads(team.checkpoint_path(self.root, res["id"]).read_text(encoding="utf-8"))
        self.assertEqual(data["next_index"], 2)
        rows = data["ledger"]["rows"]
        self.assertEqual(round(sum(row["usd"] for row in rows), 6), data["ledger"]["total_usd"])
        self.assertEqual(data["ledger"]["total_usd"], 0.02)

    def test_resume_khong_charge_lai(self):
        snap = {}
        real = team.write_checkpoint

        def spy(root, payload):
            real(root, payload)
            if payload["next_index"] == 1:
                snap["payload"] = json.loads(json.dumps(payload))

        with patch("mira.team.write_checkpoint", spy):
            self._run()
        self.assertEqual(snap["payload"]["ledger"]["total_usd"], 0.01)
        team.write_checkpoint(self.root, snap["payload"])
        _Fake.calls = []
        with patch("mira.team.provider_for", _provider):
            code, res = team.resume_team(self.root, snap["payload"]["id"], api_key="k")
        self.assertEqual(code, 0)
        self.assertEqual(_Fake.calls, ["verifier"])
        self.assertEqual(res["ledger"]["total_usd"], 0.02)

    def test_resume_giu_staging(self):
        plan = team.build_plan(
            "sửa notes.txt", surface="write_external",
            labels=["internal"], records=10, dollars=0, reversibility="C1")
        plan.declared_price = (1000.0, 0.0)
        snap = {}
        real = team.write_checkpoint

        def spy(root, payload):
            real(root, payload)
            if payload["next_index"] == 1 and payload.get("staging"):
                snap["payload"] = json.loads(json.dumps(payload))

        def fake_turn(**kw):
            target = Path(kw["session"].root) / "notes.txt"
            target.write_text("nội dung mới\n", encoding="utf-8")
            return {"final": "đã sửa", "usage": {"in": 10, "out": 0}, "seconds": 0}

        with patch("mira.team.write_checkpoint", spy), \
                patch("mira.team.provider_for", _provider), \
                patch("mira.agent.run_turn", fake_turn):
            team.execute_plan(plan, provider_name="anthropic", api_key="k",
                              root=self.root, on_step=lambda _m: None)
        self.assertIn("payload", snap)
        staging = Path(snap["payload"]["staging"])
        self.assertTrue(staging.is_dir())
        team.write_checkpoint(self.root, snap["payload"])
        before = sorted(p.name for p in (self.root / ".mira" / "staging").iterdir())
        with patch("mira.team.provider_for", _provider), \
                patch("mira.agent.run_turn", fake_turn):
            code, res = team.resume_team(self.root, snap["payload"]["id"], api_key="k")
        after = sorted(p.name for p in (self.root / ".mira" / "staging").iterdir())
        self.assertEqual(code, 0)
        self.assertEqual(before, after)
        self.assertEqual(Path(res["staging"]).resolve(), staging.resolve())

    def test_resume_thieu_checkpoint_thi_loi(self):
        prev = os.getcwd()
        os.chdir(self.root)
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = team.cmd_team(SimpleNamespace(
                    resume="khong-co", task=None, provider=None, model=None,
                    base_url=None, api_key=None, max_tokens=64, oracle=None))
        finally:
            os.chdir(prev)
        self.assertEqual(code, 2)
        self.assertIn("không có checkpoint cho id này", buf.getvalue())
        self.assertFalse((self.root / ".mira" / "runs" / "khong-co").exists())

    def test_resume_withheld_khong_hoi_sinh(self):
        _Fake.fail = True
        res = self._run()
        self.assertEqual(res["status"], "withheld")
        _Fake.calls = []
        with patch("mira.team.provider_for", _provider):
            code, again = team.resume_team(self.root, res["id"], api_key="k")
        self.assertEqual(code, 3)
        self.assertEqual(again["status"], "withheld")
        self.assertEqual(_Fake.calls, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
