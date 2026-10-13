"""Verifier và oracle chỉ nhận envelope JSON. Chữ trần không còn là verdict."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mira import team  # noqa: E402


def _body(**extra) -> str:
    obj = {"verdict": "PASS", "reasons": ["khop"], "evidence": ["so lieu"], "confidence": 0.9}
    obj.update(extra)
    return json.dumps(obj, ensure_ascii=False)


class _Prov:
    def __init__(self, replies: dict[str, str]):
        self.replies = replies
        self.name = "anthropic"

    def available(self) -> bool:
        return True

    def call(self, system: str, user: str):
        for key, text in self.replies.items():
            if key in (system or ""):
                return text, {"in": 1, "out": 1}
        return "ke hoach", {"in": 1, "out": 1}


def _run(replies: dict[str, str], *, surface="write_external", records=20, dollars=0, oracle=None) -> dict:
    plan = team.build_plan("soạn báo cáo nội bộ", surface=surface,
                           labels=["internal"], records=records, dollars=dollars)
    with patch("mira.team.provider_for", lambda *a, **k: _Prov(replies)):
        return team.execute_plan(plan, provider_name="anthropic", api_key="k",
                                 oracle=oracle, on_step=lambda m: None)


class EnvelopeTest(unittest.TestCase):
    def test_json_pass_duoc_nhan(self):
        raw = _body()
        res = _run({"VERIFIER": raw})
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["verifier_verdict"], "PASS")
        self.assertEqual(res["verdict_parsed"]["confidence"], 0.9)
        self.assertEqual(res["verdict_raw"], raw)

    def test_json_hong_bi_withheld(self):
        bad = [
            "{khong phai json",
            _body(reasons=[]),
            _body(verdict="MAYBE"),
            _body(confidence=2),
        ]
        # reasons=[] still has the key but fails the non-empty rule.
        # _body(reasons=[]) overwrites. confidence 2 overwrites.
        for text in bad:
            res = _run({"VERIFIER": text})
            self.assertEqual(res["status"], "withheld", text)
            self.assertIsNone(res["verifier_verdict"], text)

    def test_pass_tran_khong_con_duoc_nhan(self):
        res = _run({"VERIFIER": "PASS"})
        self.assertIsNone(res["verifier_verdict"])
        self.assertEqual(res["status"], "withheld")

    def test_oracle_json_co_score(self):
        raw = _body(score=0.85)
        res = _run({"VERIFIER": _body(), "ORACLE": raw},
                   surface="write_external", records=5000, dollars=3000, oracle="on")
        self.assertEqual(res["oracle_score"], 0.85)
        self.assertEqual(res["status"], "ok")

    def test_oracle_chu_score_cu_bi_withheld(self):
        res = _run({"VERIFIER": _body(), "ORACLE": "SCORE: 0.9"},
                   surface="write_external", records=5000, dollars=3000, oracle="on")
        self.assertIsNone(res["oracle_score"])
        self.assertEqual(res["status"], "withheld")


if __name__ == "__main__":
    unittest.main(verbosity=2)
