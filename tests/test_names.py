"""Tên shape, hằng tool đọc, slug eval và bảng màu đều là tiếng Anh."""
import unittest
from pathlib import Path

from frog.team import READ_TOOLS
from frog.tools import shape_of

ROOT = Path(__file__).resolve().parents[1]
OLD = (
    "doi_gia_tri", "dung_skill", "file_kem", "gioi_han_tool", "hai_skill",
    "lenh_la", "lenh_xong", "nho_fact", "nho_lan_sau", "noi_dung_la",
    "path_la", "plan_khong_ghi", "script_chua_mo", "tuyen_vai",
)
NEW = (
    "swap_values", "use_skill", "missing_file", "tool_limit", "skill_deleted",
    "stray_command", "command_done", "forgot_fact", "remember_next",
    "stray_content", "stray_path", "plan_no_write", "script_unopened",
    "role_recruit",
)


class NameTest(unittest.TestCase):
    def test_shape_bon_gia_tri_tieng_anh(self):
        self.assertEqual(shape_of("Đổi x = 1 thành x = 2 trong app.py"), "edit")
        self.assertEqual(shape_of("Chạy python .frog/skills/kem/scripts/run.py"), "run")
        self.assertEqual(shape_of("đọc app.py"), "read")
        self.assertEqual(shape_of("làm gì đó"), "ask")

    def test_khong_con_hoi_tools(self):
        import frog.team as team
        self.assertIn("read_file", READ_TOOLS)
        names = sorted(n for n in dir(team) if n.endswith("_TOOLS"))
        self.assertEqual(names, ["READ_TOOLS", "WRITE_TOOLS"])

    def test_eval_slug_moi(self):
        root = ROOT / "eval" / "tasks"
        for name in NEW:
            self.assertTrue((root / name / "task.json").is_file(), name)
        for name in OLD:
            self.assertFalse((root / name).exists(), name)

    def test_palette_doi_ten(self):
        names = sorted(p.name for p in (ROOT / "frog").glob("*.txt"))
        self.assertEqual(names, ["tui_palette_256.txt"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
