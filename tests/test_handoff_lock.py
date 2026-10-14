"""Run id, hash phiếu và grant phải khớp nội dung đã duyệt."""
from __future__ import annotations

import io
import json
import contextlib
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from mira import handoff as handoff_mod
from mira.handoff import _dir, approve, check_only, cmd_giao, open_run, remember_grant

HandoffError = getattr(handoff_mod, "HandoffError", RuntimeError)


def _brief(must: list[str]) -> dict:
    return {
        "goal": "ghi note",
        "deliverables": ["note.txt"],
        "acceptance_criteria": [{
            "schema": 1, "id": "note", "text": "tep co dung chu",
            "validator": {
                "kind": "contains", "path": "note.txt",
                "must_contain": must, "must_not_contain": [],
            },
        }],
        "constraints": [],
        "assumptions": [],
        "questions": [],
        "per_role_hints": {"planner": "", "worker": "", "verifier": ""},
    }


def _behavior_brief(cmd: str, needle: str) -> dict:
    return {
        "goal": "chay lenh",
        "deliverables": [],
        "acceptance_criteria": [{
            "schema": 1, "id": "beh", "text": "lenh in dung chu",
            "validator": {
                "kind": "behavior", "cmd": cmd, "expects_exit": 0,
                "expects_stdout": needle, "does_not_prove": "khong kiem lenh khac",
            },
        }],
        "constraints": [],
        "assumptions": [],
        "questions": [],
        "per_role_hints": {"planner": "", "worker": "", "verifier": ""},
    }


class HandoffLockTest(unittest.TestCase):
    def test_sua_validator_giu_hash_cu_khong_dat(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "note.txt").write_text("hello\n", encoding="utf-8")
            state = open_run(root, "ghi note", _brief(["khong-co"]))
            approve(root, state["id"])
            _rows, _body, code = check_only(root, state["id"])
            self.assertNotEqual(code, 0)
            path = root / ".mira" / "runs" / state["id"] / "handoff.json"
            saved = json.loads(path.read_text(encoding="utf-8"))
            saved["brief"]["acceptance_criteria"][0]["validator"]["must_contain"] = ["hello"]
            path.write_text(json.dumps(saved), encoding="utf-8")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                out = cmd_giao(Namespace(
                    cwd=str(root), run=state["id"], change=None, approve_brief=False,
                    grant=[], task=None, previous=None, provider=None, model=None,
                    base_url=None, max_tokens=64, price_in=None))
            self.assertEqual(out, 2, buf.getvalue())
            self.assertNotIn("verified", buf.getvalue())
            self.assertNotIn("Traceback", buf.getvalue())
            self.assertIn("hash", buf.getvalue())

    def test_run_id_thoat_thu_muc(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for bad in ("../../other", "..", "a/b", "a\\b", "C:\\Windows", "/etc/passwd", "abcd", "abcd1234", ""):
                with self.assertRaises(HandoffError):
                    _dir(root, bad)
            self.assertFalse((root.parent.parent / "other").exists())

    def test_duyet_cu_het_hieu_luc_khi_brief_doi(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "note.txt").write_text("hello\n", encoding="utf-8")
            state = open_run(root, "ghi note", _brief(["khong-co"]))
            approve(root, state["id"])
            from mira.handoff import _load, _save
            saved = _load(root, state["id"])
            saved["brief"]["acceptance_criteria"][0]["validator"]["must_contain"] = ["hello"]
            from mira.intake import brief_hash
            saved["brief_hash"] = brief_hash(saved["brief"])
            _save(root, saved)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                out = cmd_giao(Namespace(
                    cwd=str(root), run=state["id"], change=None, approve_brief=False,
                    grant=[], task=None, previous=None, provider=None, model=None,
                    base_url=None, max_tokens=64, price_in=None))
            self.assertNotEqual(out, 0, buf.getvalue())
            self.assertNotIn("bàn giao: đủ", buf.getvalue())

    def test_grant_ngoai_hop_dong_bi_tu_choi(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = open_run(root, "chay", _behavior_brief("python -c \"print(1)\"", "1"))
            approve(root, state["id"])
            with self.assertRaises(HandoffError):
                remember_grant(root, state["id"], "echo sai")

    def test_json_cut_bao_loi_ro(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = open_run(root, "ghi note", _brief(["hello"]))
            path = root / ".mira" / "runs" / state["id"] / "handoff.json"
            path.write_text("{", encoding="utf-8")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                out = cmd_giao(Namespace(
                    cwd=str(root), run=state["id"], change=None, approve_brief=False,
                    grant=[], task=None, previous=None, provider=None, model=None,
                    base_url=None, max_tokens=64, price_in=None))
            self.assertEqual(out, 2)
            self.assertIn("JSON", buf.getvalue())
            self.assertNotIn("Traceback", buf.getvalue())

    def test_ghi_state_bang_replace(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("mira.handoff.os.replace", wraps=__import__("os").replace) as repl:
                open_run(root, "ghi note", _brief(["hello"]))
            self.assertTrue(repl.called)


if __name__ == "__main__":
    unittest.main(verbosity=2)
