"""Manifest niêm trước promote. Đổi byte hoặc dừng giữa hai file thì không báo đủ."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mira.handoff import _load, _save, approve, confirm, open_run, promote_sealed, seal_manifest, settle
from mira.intake import brief_hash
from mira.obligations import judge_obligations


def _brief() -> dict:
    return {
        "goal": "Ghi report.md",
        "deliverables": ["report.md", "extra.txt"],
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


def _pending(root: Path) -> tuple[dict, Path]:
    brief = _brief()
    staging = root / ".mira" / "staging" / "box.withheld"
    staging.mkdir(parents=True)
    (staging / "report.md").write_text("SOURCE\n", encoding="utf-8")
    (staging / "extra.txt").write_text("KEEP\n", encoding="utf-8")
    rows = judge_obligations(
        brief["acceptance_criteria"], cwd=staging, granted=set(),
        run_id="a" * 12, validators=True, brief_hash=brief_hash(brief))
    state = open_run(root, "Ghi report.md", brief)
    approve(root, state["id"])
    saved = _load(root, state["id"])
    saved["phase"] = "awaiting_confirmation"
    saved["hold"] = "needs_confirmation"
    saved["staging"] = str(staging)
    saved["obligations"] = rows
    saved["want_deliver"] = False
    saved["promoted"] = False
    _save(root, saved)
    seal_manifest(root, saved["id"])
    return _load(root, saved["id"]), staging


class ManifestTest(unittest.TestCase):
    def test_doi_file_sau_niem_khong_promote(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state, staging = _pending(root)
            (staging / "extra.txt").write_text("TAMPER\n", encoding="utf-8")
            confirm(root, state["id"], "tone", "report.md")
            _rows, body, code = settle(root, state["id"])
            self.assertNotEqual(code, 0, body)
            self.assertNotIn("bàn giao: đủ", body)
            self.assertFalse((root / "extra.txt").exists())
            self.assertFalse((root / "report.md").exists())
            sealed = _load(root, state["id"])["manifest"]
            self.assertEqual(sealed["run_id"], state["id"])
            self.assertEqual(sealed["attempt"], 1)
            self.assertEqual(sealed["brief_hash"], state["brief_hash"])
            names = {item["path"] for item in sealed["files"]}
            self.assertEqual(names, {"report.md", "extra.txt"})

    def test_khong_doi_thi_promote_dung_byte(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state, _staging = _pending(root)
            confirm(root, state["id"], "tone", "report.md")
            _rows, body, code = settle(root, state["id"])
            self.assertEqual(code, 0, body)
            self.assertIn("bàn giao: người dùng xác nhận", body)
            self.assertEqual((root / "report.md").read_text(encoding="utf-8"), "SOURCE\n")
            self.assertEqual((root / "extra.txt").read_text(encoding="utf-8"), "KEEP\n")
            again = promote_sealed(root, _load(root, state["id"]))
            self.assertEqual(again, "")
            self.assertEqual((root / "extra.txt").read_text(encoding="utf-8"), "KEEP\n")

    def test_dung_giua_hai_file_khong_bao_du(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state, _staging = _pending(root)

            def _pause(name: str) -> None:
                if name == "mid-promote":
                    raise RuntimeError("kill")

            with patch("mira.team._test_pause", _pause):
                with self.assertRaises(RuntimeError):
                    promote_sealed(root, _load(root, state["id"]))
            saved = _load(root, state["id"])
            self.assertFalse(saved["promoted"])
            self.assertNotEqual(saved["phase"], "delivered")
            report = root / "report.md"
            extra = root / "extra.txt"
            copied = [path for path in (report, extra) if path.is_file()]
            self.assertEqual(len(copied), 1)
            body = (root / ".mira" / "runs" / state["id"] / "handoff.md").read_text(encoding="utf-8") if (
                root / ".mira" / "runs" / state["id"] / "handoff.md").is_file() else ""
            self.assertNotIn("bàn giao: đủ", body)
