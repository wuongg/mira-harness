"""Máy gác tiêu đề commit, trên repo git tạm."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "check_commits.py"


class CommitLintTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        self._git(["init"])
        self._git(["config", "user.email", "t@example.com"])
        self._git(["config", "user.name", "Test"])
        (self.repo / "a.txt").write_text("a\n", encoding="utf-8")
        self._git(["add", "a.txt"])
        self._commit("init")

    def tearDown(self):
        self.tmp.cleanup()

    def _git(self, args: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], cwd=self.repo, capture_output=True, check=True)

    def _commit(self, subject: str) -> None:
        msg = self.repo / "MSG.txt"
        msg.write_text(subject + "\n", encoding="utf-8")
        self._git(["commit", "--allow-empty", "-F", str(msg)])

    def _lint(self) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(TOOL), "HEAD~1..HEAD"],
            cwd=self.repo, capture_output=True, encoding="utf-8", errors="replace", check=False)

    def test_tieu_de_dung_thi_pass(self):
        self._commit("[S4] Add the lint")
        proc = self._lint()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_thieu_id_thi_fail(self):
        self._commit("Add the lint")
        proc = self._lint()
        self.assertEqual(proc.returncode, 1)
        self.assertIn("thieu", proc.stdout)

    def test_bom_thi_fail(self):
        self._commit("\ufeff[S4] Add the lint")
        proc = self._lint()
        self.assertEqual(proc.returncode, 1)
        self.assertIn("U+FEFF", proc.stdout)

    def test_dai_hon_72_thi_fail(self):
        self._commit("[S4] " + ("a" * 80))
        proc = self._lint()
        self.assertEqual(proc.returncode, 1)

    def test_zero_width_thi_fail(self):
        self._commit("[S4] Add\u200bthe lint")
        proc = self._lint()
        self.assertEqual(proc.returncode, 1)
        self.assertIn("U+200B", proc.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
