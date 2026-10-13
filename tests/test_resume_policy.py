"""Cờ require-evidence trên checkpoint không tắt khi resume bỏ cờ."""
from __future__ import annotations

import io
import os
import shlex
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from mira.team import cmd_team, write_checkpoint


class _Prov:
    def __init__(self, *_a, **_k):
        self.name = "fake"
        self.attempts = 1

    def available(self):
        return True

    def call(self, _system, _user):
        return "xong", {"in": 2, "out": 1}


def _brief(criteria):
    return {
        "goal": "tóm tắt",
        "deliverables": [],
        "acceptance_criteria": criteria,
        "constraints": [],
        "assumptions": [],
        "questions": [],
        "per_role_hints": {"planner": "", "worker": "", "verifier": ""},
    }


def _checkpoint(root: Path, **extra):
    cmd = shlex.join([sys.executable, "-c", "import sys; raise SystemExit(1)"])
    payload = {
        "id": "run1",
        "version": 1,
        "next_index": 0,
        "task": "tóm tắt tài liệu công khai",
        "steps": [],
        "ledger": {"rows": [], "total_usd": 0.0, "total_in": 0,
                   "total_out": 0, "subagent_runs": 0},
        "staging": None,
        "status": "ok",
        "fail_reason": None,
        "brief": _brief([f"check: {cmd}"]),
        "brief_hash": "giu-nguyen",
        "declared_price": [1000.0, 0.0],
        "hints": {"surface": "read_only", "labels": ["public"], "records": 10,
                  "dollars": 0, "reversibility": "C1", "output_type": "free_string"},
        "workers": 1,
        "require_evidence": True,
    }
    payload.update(extra)
    write_checkpoint(root, payload)


def _resume(root: Path):
    prev = os.getcwd()
    os.chdir(root)
    try:
        buf = io.StringIO()
        with redirect_stdout(buf), patch("mira.team.provider_for", _Prov):
            code = cmd_team(SimpleNamespace(
                resume="run1", task=None, brief=None, provider=None, model=None,
                base_url=None, api_key="k", max_tokens=64, oracle=None,
                require_evidence=False))
    finally:
        os.chdir(prev)
    return code, buf.getvalue()


class ResumePolicyTest(unittest.TestCase):
    def test_cli_resume_khong_tat_co(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _checkpoint(root)
            code, text = _resume(root)
        self.assertEqual(code, 3)
        self.assertIn("bị chặn:", text)
        self.assertIn("Sửa cho lệnh thoát 0", text)
        self.assertIn("GIỮ LẠI", text)

    def test_checkpoint_cu_khong_co_co_van_chay(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _checkpoint(root, require_evidence=False)
            code, _text = _resume(root)
        self.assertEqual(code, 0)

    def test_thieu_brief_khong_vo(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _checkpoint(root, brief=None, brief_hash=None)
            code, _text = _resume(root)
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
