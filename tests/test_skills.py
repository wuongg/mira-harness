import tempfile
import unittest
from pathlib import Path

from r0.skills import load_skills, remember_fact, repo_map
from r0.tools import Session


class SkillTest(unittest.TestCase):
    def test_mot_than_va_tu_choi_ten_la(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / ".mira" / "skills" / "mot"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: mot\ndescription: Khi cần bước mở đầu.\n---\nTHAN-MOT\n",
                encoding="utf-8")
            hai = root / ".mira" / "skills" / "hai"
            hai.mkdir(parents=True)
            (hai / "SKILL.md").write_text(
                "---\nname: hai\ndescription: Khi bước mở đầu đã xong.\n---\nTHAN-HAI\n",
                encoding="utf-8")
            (root / "app.py").write_text("def main():\n    return 1\n", encoding="utf-8")
            session = Session(root=root, mode="acceptEdits", approve=lambda _t, _a: True)
            self.assertIn("mot", session.plan_skills(["mot"]))
            early = session.use_skill("khong-co")
            self.assertTrue(early.startswith("LỖI"))
            self.assertNotIn("THAN-MOT", early)
            blocked = session.read_file(".mira/skills/mot/SKILL.md")
            self.assertTrue(blocked.startswith("BỊ CHẶN"))
            self.assertNotIn("THAN-MOT", blocked)
            session.plan_skills(["mot"])
            early_body = session.use_skill("hai")
            self.assertTrue(early_body.startswith("LỖI"))
            self.assertNotIn("THAN-HAI", early_body)
            self.assertEqual(session.skills_opened, [])
            body = session.use_skill("mot")
            self.assertIn("THAN-MOT", body)
            self.assertEqual(session.skills_opened, ["mot"])
            mapped = repo_map(root, "app")
            self.assertIn("def main()", mapped)
            before = (root / "app.py").read_text(encoding="utf-8")
            repo_map(root, "app")
            self.assertEqual((root / "app.py").read_text(encoding="utf-8"), before)
            self.assertEqual(len(load_skills(root)), 2)

    def test_fact_chi_khi_goi_nho(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remember_fact(root, "hàm main ở đâu", "hàm main nằm trong app.py")
            text = (root / ".mira" / "facts.jsonl").read_text(encoding="utf-8")
            self.assertIn("main", text)


if __name__ == "__main__":
    unittest.main()
