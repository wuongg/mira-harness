import tempfile
import unittest
from pathlib import Path

from mira.tools import Session


class UndoDiffMemoryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "a.py").write_text("x = 1\ny = 2\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def _sess(self, mode="default", approve=True):
        return Session(root=self.root, mode=mode,
                       approve=(lambda t, a: True) if approve else (lambda t, a: False))

    def test_undo_restores_previous_text(self):
        s = self._sess()
        s.edit_file("a.py", "x = 1", "x = 99")
        self.assertIn("x = 99", (self.root / "a.py").read_text())
        self.assertIn("đã hoàn tác", s.undo_last())
        self.assertIn("x = 1", (self.root / "a.py").read_text())

    def test_undo_removes_new_file(self):
        s = self._sess()
        s.write_file("new.txt", "hi")
        self.assertTrue((self.root / "new.txt").exists())
        s.undo_last()
        self.assertFalse((self.root / "new.txt").exists())

    def test_undo_empty(self):
        self.assertIn("chưa có", self._sess().undo_last())

    def test_diff_counts(self):
        s = self._sess()
        s.edit_file("a.py", "y = 2", "y = 3")
        d = s.diff_summary()
        self.assertIn("a.py", d)
        self.assertIn("+1", d)

    def test_diff_empty(self):
        self.assertIn("chưa sửa", self._sess().diff_summary())

    def test_memory_roundtrip(self):
        s = self._sess()
        self.assertEqual(s.load_memory(), "")
        s.save_memory("luôn chạy test trước khi giao")
        self.assertIn("test", s.load_memory())
        self.assertEqual(s.memory_path().name, "MIRA.md")

    def test_no_snapshot_on_refusal(self):
        s = self._sess(approve=False)
        s.edit_file("a.py", "x = 1", "x = 2")
        self.assertEqual(len(s.snapshots), 0)

    def test_mascot_and_caption(self):
        from mira import ui
        self.assertGreaterEqual(len(ui.MASCOT), 4)


if __name__ == "__main__":
    unittest.main()
