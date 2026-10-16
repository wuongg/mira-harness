"""Cây thật không đổi cho tới khi verifier PASS và người duyệt."""
from __future__ import annotations

import hashlib
import os
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from frog import team  # noqa: E402


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class _Prov:
    def __init__(self, fail: bool):
        self.fail = fail
        self.name = "anthropic"

    def available(self) -> bool:
        return True

    def call(self, system: str, user: str):
        if self.fail and "VERIFIER" in (system or ""):
            return '{"verdict":"FAIL","reasons":["thieu"],"evidence":[],"confidence":0.2}', {"in": 1, "out": 1}
        if "VERIFIER" in (system or ""):
            return '{"verdict":"PASS","reasons":["khop"],"evidence":["so lieu"],"confidence":0.9}', {"in": 1, "out": 1}
        return "ke hoach", {"in": 1, "out": 1}


def _edit(session_root: Path, name: str, text: str):
    def run_turn(**kw):
        session = kw["session"]
        (session.root / name).write_text(text, encoding="utf-8")
        session.audit.append({"action": "edit_file", "path": name})
        return {"final": "da sua", "usage": {"in": 1, "out": 1}, "seconds": 0}
    return run_turn


def _args(task: str, out: str | None, *, approve: bool = False):
    return Namespace(
        task=task, labels="internal", surface="write_external", records=50,
        dollars=0.0, reversibility="C1", output_type="free_string",
        workers=1, sub_depth=0, dry_run=False, provider="anthropic",
        model=None, base_url="http://127.0.0.1:9", max_tokens=64,
        approve=approve, out=out, api_key="k",
    )


class WtsTest(unittest.TestCase):
    def test_verifier_fail_cay_that_khong_doi(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = root / "app.py"
            app.write_text("x = 1\n", encoding="utf-8")
            before = _sha(app)
            plan = team.build_plan(
                "Đổi x = 1 thành x = 2 trong app.py",
                surface="write_external", labels=["internal"])
            with patch("frog.agent.run_turn", _edit(root, "app.py", "x = 9\n")), \
                 patch("frog.team.provider_for", lambda *a, **k: _Prov(True)):
                res = team.execute_plan(plan, provider_name="anthropic", api_key="k",
                                        root=root, on_step=lambda m: None)
            self.assertNotEqual(res["status"], "ok")
            self.assertEqual(_sha(app), before)
            held = list((root / ".frog" / "staging").glob("*.withheld"))
            self.assertTrue(held or (root / ".frog" / "staging").exists())

    def test_pass_nhung_nguoi_tu_choi_khong_promote(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = root / "app.py"
            app.write_text("x = 1\n", encoding="utf-8")
            before = _sha(app)
            out = root / "ket"
            cwd = os.getcwd()
            os.chdir(root)
            try:
                with patch("frog.agent.run_turn", _edit(root, "app.py", "x = 9\n")), \
                     patch("frog.team.provider_for", lambda *a, **k: _Prov(False)), \
                     patch("builtins.input", lambda _p: "n"):
                    code = team.cmd_team(_args(
                        "Đổi x = 1 thành x = 2 trong app.py", str(out)))
            finally:
                os.chdir(cwd)
            self.assertNotEqual(code, 0)
            self.assertEqual(_sha(app), before)
            extra = [p for p in root.iterdir() if p.name not in {"app.py", ".frog", "ket"}]
            self.assertEqual(extra, [])

    def test_pass_va_duyet_promote_dung_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app.py").write_text("x = 1\n", encoding="utf-8")
            (root / "giu.txt").write_text("giu\n", encoding="utf-8")
            out = root / "ket"
            cwd = os.getcwd()
            os.chdir(root)
            try:
                with patch("frog.agent.run_turn", _edit(root, "app.py", "x = 2\n")), \
                     patch("frog.team.provider_for", lambda *a, **k: _Prov(False)), \
                     patch("builtins.input", lambda _p: "y"):
                    code = team.cmd_team(_args(
                        "Đổi x = 1 thành x = 2 trong app.py", str(out)))
            finally:
                os.chdir(cwd)
            self.assertEqual(code, 0)
            self.assertEqual((root / "app.py").read_text(encoding="utf-8"), "x = 2\n")
            self.assertEqual((root / "giu.txt").read_text(encoding="utf-8"), "giu\n")
            traces = list(out.rglob("trace.json"))
            self.assertTrue(traces)
            blob = traces[0].read_text(encoding="utf-8")
            self.assertIn("promote", blob)
            self.assertIn("app.py", blob)

    def test_hai_run_song_song_khong_dung_staging(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "goc.txt").write_text("goc\n", encoding="utf-8")
            a = team.prepare_staging(root)
            b = team.prepare_staging(root)
            self.assertNotEqual(a, b)
            (a / "a.txt").write_text("a\n", encoding="utf-8")
            (b / "b.txt").write_text("b\n", encoding="utf-8")
            self.assertFalse((a / "b.txt").exists())
            self.assertFalse((b / "a.txt").exists())
            self.assertTrue((a / "goc.txt").is_file())
            self.assertTrue((b / "goc.txt").is_file())


if __name__ == "__main__":
    unittest.main(verbosity=2)
