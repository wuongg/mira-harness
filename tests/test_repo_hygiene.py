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
        path = ROOT / "frog" / "team.py"
        self.assertTrue(compileall.compile_file(str(path), quiet=1))
        lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(lines.count("from pathlib import Path"), 1)

    def test_ten_file_khong_khoang_trang_hay_ngoac(self):
        tracked = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT,
                                 capture_output=True, check=True)
        bad = []
        for raw in tracked.stdout.split(b"\0"):
            if not raw:
                continue
            name = raw.decode("utf-8", "surrogateescape")
            base = name.replace("\\", "/").rsplit("/", 1)[-1]
            if " " in base or "(" in base or ")" in base or any(ord(ch) > 127 for ch in base):
                bad.append(name)
        self.assertEqual(bad, [])

    def test_khong_file_nang_ngoai_docs(self):
        tracked = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT,
                                 capture_output=True, check=True)
        heavy = []
        for raw in tracked.stdout.split(b"\0"):
            if not raw:
                continue
            name = raw.decode("utf-8", "surrogateescape").replace("\\", "/")
            path = ROOT / name
            if path.is_file() and path.stat().st_size > 200 * 1024 and not name.startswith("docs/"):
                heavy.append(name)
        self.assertEqual(heavy, [])

    def test_goc_khong_ansi_png_labels(self):
        tracked = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT,
                                 capture_output=True, check=True)
        bad = []
        for raw in tracked.stdout.split(b"\0"):
            if not raw or b"/" in raw or b"\\" in raw:
                continue
            name = raw.decode("utf-8", "surrogateescape")
            if name == "labels.csv" or name.endswith(".ansi") or name.endswith(".png"):
                bad.append(name)
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
