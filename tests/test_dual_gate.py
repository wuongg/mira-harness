"""Hai người khác tên khi dual_approval. --approve không được thay hai người."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mira import team  # noqa: E402


CALLS: list[str] = []


class _Prov:
    name = "anthropic"

    def available(self) -> bool:
        return True

    def call(self, system: str, user: str):
        CALLS.append(system[:24])
        if "VERIFIER" in (system or ""):
            return "PASS", {"in": 1, "out": 1}
        return "1. buoc", {"in": 1, "out": 1}


def _run_turn(**kw):
    session = kw["session"]
    (session.root / "app.py").write_text("x = 2\n", encoding="utf-8")
    return {"final": "da sua", "usage": {"in": 1, "out": 1}, "seconds": 0}


def _args(*, approve: bool = False, out: str | None = None):
    return Namespace(
        task="Đổi x = 1 thành x = 2 trong app.py",
        labels="internal", surface="egress_new", records=50, dollars=0.0,
        reversibility="C1", output_type="free_string", workers=1, sub_depth=0,
        dry_run=False, provider="anthropic", model=None,
        base_url="http://127.0.0.1:9", max_tokens=64, approve=approve,
        out=out, api_key="k",
    )


def _inputs(names: list[str], *, wrong_second: bool = False):
    pending = list(names)

    def fake(prompt: str) -> str:
        if "tên" in prompt:
            return pending.pop(0)
        if "cụm" in prompt:
            phrase = prompt.split("cụm:", 1)[1]
            phrase = phrase.replace("\x1b[0m", "").strip()
            if wrong_second and not pending:
                return "sai cụm hết"
            return phrase
        return "n"

    return fake


class DualGateTest(unittest.TestCase):
    def setUp(self):
        CALLS.clear()

    def _tree(self):
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        (root / "app.py").write_text("x = 1\n", encoding="utf-8")
        return tmp, root

    def test_hai_ten_khac_nhau_thi_duoc_ghi(self):
        tmp, root = self._tree()
        out = root / "ket"
        cwd = os.getcwd()
        os.chdir(root)
        try:
            with patch("mira.agent.run_turn", _run_turn), \
                 patch("mira.team.provider_for", lambda *a, **k: _Prov()), \
                 patch("builtins.input", _inputs(["an", "binh"])):
                code = team.cmd_team(_args(out=str(out)))
            self.assertEqual(code, 0)
            traces = list(out.rglob("trace.json"))
            self.assertTrue(traces)
            data = json.loads(traces[0].read_text(encoding="utf-8"))
            people = data.get("gate_person") or []
            self.assertEqual([p["name"] for p in people], ["an", "binh"])
            self.assertEqual(len({p["plan_hash"] for p in people}), 1)
            self.assertTrue(people[0]["plan_hash"])
        finally:
            os.chdir(cwd)
            tmp.cleanup()

    def test_trung_ten_bi_tu_choi(self):
        tmp, root = self._tree()
        out = root / "ket"
        cwd = os.getcwd()
        os.chdir(root)
        try:
            with patch("mira.agent.run_turn", _run_turn), \
                 patch("mira.team.provider_for", lambda *a, **k: _Prov()), \
                 patch("builtins.input", _inputs(["an", "an"])):
                code = team.cmd_team(_args(out=str(out)))
        finally:
            os.chdir(cwd)
        self.assertEqual(code, 5)
        self.assertEqual(list(out.rglob("result.md")), [])
        self.assertEqual((root / "app.py").read_text(encoding="utf-8"), "x = 1\n")
        tmp.cleanup()

    def test_sai_mat_khau_vong_hai(self):
        tmp, root = self._tree()
        out = root / "ket"
        cwd = os.getcwd()
        os.chdir(root)
        try:
            with patch("mira.agent.run_turn", _run_turn), \
                 patch("mira.team.provider_for", lambda *a, **k: _Prov()), \
                 patch("builtins.input", _inputs(["an", "binh"], wrong_second=True)):
                code = team.cmd_team(_args(out=str(out)))
        finally:
            os.chdir(cwd)
        self.assertNotEqual(code, 0)
        self.assertEqual((root / "app.py").read_text(encoding="utf-8"), "x = 1\n")
        self.assertEqual(list(out.rglob("result.md")), [])
        tmp.cleanup()

    def test_approve_bi_chan_khi_dual(self):
        tmp, root = self._tree()
        cwd = os.getcwd()
        os.chdir(root)
        try:
            with patch("mira.agent.run_turn", _run_turn), \
                 patch("mira.team.provider_for", lambda *a, **k: _Prov()):
                code = team.cmd_team(_args(approve=True, out=str(root / "ket")))
        finally:
            os.chdir(cwd)
            tmp.cleanup()
        self.assertEqual(code, 6)
        self.assertEqual(CALLS, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
