"""LICENSE, gốc repo, và team.py biên dịch được."""
from __future__ import annotations

import compileall
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class RepoHygieneTest(unittest.TestCase):
    def test_license_ton_tai(self):
        text = (ROOT / "LICENSE").read_text(encoding="utf-8")
        self.assertIn("MIT", text)

    def test_goc_khong_con_labels_csv_trong_git(self):
        tracked = subprocess.run(["git", "ls-files", "labels.csv"], cwd=ROOT,
                                 capture_output=True, text=True, check=False)
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("labels.csv", ignore)
        self.assertEqual(tracked.stdout.strip(), "")

    def test_compileall_team(self):
        path = ROOT / "mira" / "team.py"
        self.assertTrue(compileall.compile_file(str(path), quiet=1))
        lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(lines.count("from pathlib import Path"), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
