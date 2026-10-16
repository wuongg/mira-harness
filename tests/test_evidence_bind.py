"""Kết quả tự động hết hiệu lực khi byte đã kiểm đổi. Không gọi model."""
from __future__ import annotations

import hashlib
import shlex
import sys
import tempfile
import unittest
from pathlib import Path

from frog.handoff import _load, _save, approve, confirm, open_run, settle
from frog.intake import brief_hash
from frog.obligations import judge_obligations, refresh_evidence


def _report_brief() -> dict:
    return {
        "goal": "Ghi report.md",
        "deliverables": ["report.md"],
        "acceptance_criteria": [
            {
                "schema": 1, "id": "src", "text": "bao cao co SOURCE",
                "validator": {
                    "kind": "contains", "path": "report.md",
                    "must_contain": ["SOURCE"], "must_not_contain": [],
                },
            },
            {"schema": 1, "id": "tone", "text": "giong van phong de doc"},
        ],
        "constraints": [], "assumptions": [], "questions": [],
        "per_role_hints": {"planner": "", "worker": "", "verifier": ""},
    }


class EvidenceBindTest(unittest.TestCase):
    def test_doi_artifact_sau_validator_khong_song_lai(self):
        brief = _report_brief()
        bound = brief_hash(brief)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            staging = root / ".mira" / "staging" / "box.withheld"
            staging.mkdir(parents=True)
            target = staging / "report.md"
            target.write_text("SOURCE\n", encoding="utf-8")
            rows = judge_obligations(
                brief["acceptance_criteria"], cwd=staging, granted=set(),
                run_id="a" * 12, validators=True, brief_hash=bound)
            auto = next(row for row in rows if row["criterion_id"] == "src")
            self.assertTrue(auto["criterion_verified"])
            evidence = auto["evidence"]
            self.assertEqual(evidence["brief_hash"], bound)
            self.assertEqual(evidence["scope"], "file")
            self.assertEqual(evidence["paths"][0]["sha256"],
                             hashlib.sha256(target.read_bytes()).hexdigest())
            self.assertTrue(evidence["validator_sha256"])
            state = open_run(root, "Ghi report.md", brief)
            approve(root, state["id"])
            saved = _load(root, state["id"])
            saved["phase"] = "awaiting_confirmation"
            saved["hold"] = "needs_confirmation"
            saved["staging"] = str(staging)
            saved["obligations"] = rows
            _save(root, saved)
            target.write_text("NO REQUIRED CONTENT\n", encoding="utf-8")
            confirm(root, state["id"], "tone", "report.md")
            _out_rows, body, code = settle(root, state["id"])
            self.assertNotEqual(code, 0, body)
            self.assertIn("hết hiệu lực", body)
            src = next(row for row in _out_rows if row["criterion_id"] == "src")
            self.assertFalse(src["criterion_verified"])
            self.assertEqual(src["evidence_status"], "hết hiệu lực")
            self.assertFalse((root / "report.md").exists())
            tone = next(row for row in _out_rows if row["criterion_id"] == "tone")
            self.assertEqual(tone["state"], "user_confirmed")

    def test_behavior_doi_dependency_khac_file_chinh(self):
        root_box = None
        with tempfile.TemporaryDirectory() as tmp:
            root_box = Path(tmp)
            (root_box / "main.txt").write_text("keep\n", encoding="utf-8")
            (root_box / "dep.txt").write_text("v1\n", encoding="utf-8")
            cmd = shlex.join([sys.executable, "-c", "print('ok')"])
            brief_rows = [{
                "schema": 1, "id": "run", "text": "lenh in ok",
                "validator": {
                    "kind": "behavior", "cmd": cmd, "expects_exit": 0,
                    "expects_stdout": "ok", "does_not_prove": "khong kiem file khac",
                },
            }]
            # Lệnh giả: không chạy subprocess trong test này nếu judge cần lệnh thật.
            rows = judge_obligations(
                brief_rows, cwd=root_box, granted={cmd}, validators=True,
                brief_hash="b" * 64)
            row = rows[0]
            self.assertTrue(row["criterion_verified"], row)
            self.assertEqual(row["evidence"]["scope"], "tree")
            self.assertTrue(row["evidence"]["tree_sha256"])
            self.assertEqual(row["evidence_status"], "còn hiệu lực")
            (root_box / "dep.txt").write_text("v2\n", encoding="utf-8")
            refreshed = refresh_evidence(rows, root_box, "b" * 64, brief_rows)
            self.assertEqual(refreshed[0]["evidence_status"], "hết hiệu lực")
            self.assertFalse(refreshed[0]["criterion_verified"])
            self.assertNotEqual(refreshed[0]["state"], "verified")

    def test_verified_khong_co_evidence_la_chua_kiem_lai(self):
        rows = [{
            "criterion_id": "src", "criterion_verified": True, "state": "verified",
            "kind": "contains", "reason": "", "does_not_prove": "",
        }]
        criteria = _report_brief()["acceptance_criteria"]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "report.md").write_text("SOURCE\n", encoding="utf-8")
            out = refresh_evidence(rows, root, "c" * 64, criteria)
        self.assertEqual(out[0]["evidence_status"], "chưa kiểm lại")
        self.assertFalse(out[0]["criterion_verified"])
