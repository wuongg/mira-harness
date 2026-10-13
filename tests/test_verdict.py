"""Verifier chỉ được đúng PASS hoặc FAIL. Lệch giao thức thì giữ lại."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from r0 import team  # noqa: E402


class _Prov:
    def __init__(self, verdict: str):
        self.verdict = verdict
        self.name = "anthropic"

    def available(self) -> bool:
        return True

    def call(self, system: str, user: str):
        if "VERIFIER" in (system or ""):
            return self.verdict, {"in": 1, "out": 1}
        return "KẾT QUẢ", {"in": 1, "out": 1}


def _run(text: str) -> dict:
    plan = team.build_plan("soạn báo cáo nội bộ", surface="write_external",
                           labels=["internal"], records=20, dollars=0)
    from unittest.mock import patch
    with patch("r0.team.provider_for", lambda *a, **k: _Prov(text)):
        return team.execute_plan(plan, provider_name="anthropic", api_key="k",
                                 on_step=lambda m: None)


class VerdictTest(unittest.TestCase):
    def test_pass_dung_tung_chu(self):
        res = _run("PASS")
        self.assertEqual(res["verifier_verdict"], "PASS")
        self.assertEqual(res["status"], "ok")

    def test_ket_luan_pass_bi_withheld(self):
        res = _run("Kết luận: PASS")
        self.assertIsNone(res["verifier_verdict"])
        self.assertEqual(res["status"], "withheld")

    def test_pass_thuong_va_passed_va_rong(self):
        for text in (" pass ", "PASSED", ""):
            res = _run(text)
            self.assertIsNone(res["verifier_verdict"], text)
            self.assertEqual(res["status"], "withheld", text)
            self.assertNotEqual(res["status"], "ok")


if __name__ == "__main__":
    unittest.main(verbosity=2)
