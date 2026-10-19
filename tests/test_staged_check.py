"""Verifier và obligations đọc staging, không đọc cây nguồn."""
from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from frog.handoff import render_table, verifier_delivery
from frog.obligations import judge_obligations
from frog.team import promote_staging, staging_prompt, withhold_staging


def _criterion(must: str, ban: str) -> dict:
    return {
        "schema": 1,
        "id": "c1",
        "text": "noi dung file",
        "cmd": "",
        "proves": "",
        "artifact": "sum_to.py",
        "validator": {
            "kind": "contains",
            "path": "sum_to.py",
            "must_contain": [must],
            "must_not_contain": [ban],
        },
    }


def _pair(source_body: str, staged_body: str):
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    source = root / "src"
    staging = root / "staging"
    source.mkdir()
    staging.mkdir()
    (source / "sum_to.py").write_text(source_body, encoding="utf-8")
    (staging / "sum_to.py").write_text(staged_body, encoding="utf-8")
    return tmp, source, staging


class VerifierDeliveryTest(unittest.TestCase):
    def test_khong_ban_giao_theo_verifier(self):
        manual = {"kind": "manual", "state": "needs_confirmation", "criterion_verified": False}
        verified = {"kind": "contains", "state": "verified", "criterion_verified": True}
        self.assertFalse(verifier_delivery(
            [verified, manual], "walk-away", "PASS", "abc", "abc"))
        self.assertFalse(verifier_delivery(
            [verified, manual], "direct", "PASS", "abc", "abc"))
        self.assertFalse(verifier_delivery(
            [verified, manual], "watch", "PASS", "abc", "abc"))


class StagedCheckTest(unittest.TestCase):
    def test_nguon_sai_staged_dung_thi_verified_va_ban_giao(self):
        tmp, source, staging = _pair("SOURCE_WRONG\n", "STAGED_RIGHT\n")
        self.addCleanup(tmp.cleanup)
        rows = judge_obligations(
            [_criterion("STAGED_RIGHT", "SOURCE_WRONG")],
            cwd=staging, validators=True, surface="staged")
        self.assertTrue(rows[0]["criterion_verified"], rows[0])
        prompt = staging_prompt(source, staging)
        self.assertIn("STAGED_RIGHT", prompt)
        self.assertNotIn("SOURCE_WRONG", prompt)
        audit: list = []
        promoted = promote_staging(source, staging, audit)
        self.assertEqual(promoted, ["sum_to.py"])
        self.assertIn("STAGED_RIGHT", (source / "sum_to.py").read_text(encoding="utf-8"))

    def test_nguon_dung_staged_sai_thi_khong_verified(self):
        tmp, source, staging = _pair("STAGED_RIGHT\n", "SOURCE_WRONG\n")
        self.addCleanup(tmp.cleanup)
        rows = judge_obligations(
            [_criterion("STAGED_RIGHT", "SOURCE_WRONG")],
            cwd=staging, validators=True, surface="staged")
        self.assertFalse(rows[0]["criterion_verified"], rows[0])
        prompt = staging_prompt(source, staging)
        self.assertIn("SOURCE_WRONG", prompt)
        self.assertNotIn("STAGED_RIGHT", prompt)
        self.assertIn("STAGED_RIGHT", (source / "sum_to.py").read_text(encoding="utf-8"))
        self.assertNotIn("SOURCE_WRONG", (source / "sum_to.py").read_text(encoding="utf-8"))

    def test_hash_trong_bang_khop_byte_staged_va_fail_giu_staging(self):
        body = "STAGED_RIGHT\n"
        tmp, source, staging = _pair("SOURCE_WRONG\n", body)
        self.addCleanup(tmp.cleanup)
        digest = hashlib.sha256((staging / "sum_to.py").read_bytes()).hexdigest()
        rows = judge_obligations(
            [_criterion("STAGED_RIGHT", "SOURCE_WRONG")],
            cwd=staging, validators=True, surface="staged")
        table = render_table("viec", rows)
        self.assertIn(f"kiểm trên bản staged (hash {digest})", table)
        self.assertEqual(rows[0]["staged_hash"], digest)
        held = withhold_staging(staging)
        self.assertTrue((held / "sum_to.py").is_file())
        self.assertEqual(hashlib.sha256((held / "sum_to.py").read_bytes()).hexdigest(), digest)
        self.assertIn("SOURCE_WRONG", (source / "sum_to.py").read_text(encoding="utf-8"))
