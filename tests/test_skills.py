import tempfile
import unittest
from pathlib import Path

from r0.agent import _consider_finish
from r0.skills import catalog_for_prompt, load_skills, remember_fact, repo_map, worker_skill_block
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
            note = root / ".mira" / "skills" / "mot" / "references" / "note.md"
            note.parent.mkdir(parents=True)
            note.write_text("NOI-DUNG-KEM\n", encoding="utf-8")
            blocked_note = session.read_file(".mira/skills/mot/references/note.md")
            self.assertTrue(blocked_note.startswith("BỊ CHẶN"))
            self.assertNotIn("NOI-DUNG-KEM", blocked_note)
            session.plan_skills(["mot"])
            early_body = session.use_skill("hai")
            self.assertTrue(early_body.startswith("LỖI"))
            self.assertNotIn("THAN-HAI", early_body)
            self.assertEqual(session.skills_opened, [])
            body = session.use_skill("mot")
            self.assertIn("THAN-MOT", body)
            self.assertIn("references/note.md", body)
            self.assertNotIn("NOI-DUNG-KEM", body)
            self.assertEqual(session.skills_opened, ["mot"])
            outside = session.read_skill_file("mot", "../../app.py")
            self.assertTrue(outside.startswith("LỖI"))
            self.assertNotIn("return 1", outside)
            inside = session.read_skill_file("mot", "references/note.md")
            self.assertIn("NOI-DUNG-KEM", inside)
            self.assertNotIn("THAN-HAI", worker_skill_block(root, "mot"))
            self.assertIn("THAN-HAI", worker_skill_block(root, "hai"))
            self.assertNotIn("THAN-MOT", worker_skill_block(root, "hai"))
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

    def test_catalog_bo_skill_khong_trung(self):
        skills = []
        for index in range(12):
            desc = ("zzzz " * 80).strip()
            if index == 3:
                desc = "khi can bien doi so " + desc
            skills.append({"name": f"s{index}", "description": desc, "body": ""})
        text, stats = catalog_for_prompt(skills, "bien doi")
        self.assertGreater(stats["tokens"], 1000)
        self.assertLess(stats["kept"], stats["skills"])
        self.assertIn("s3", text)
        self.assertNotIn("- s0:", text)

    def test_fact_khi_lan_2_dung(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session = Session(root=root, mode="acceptEdits", approve=lambda _t, _a: True)
            session.lane_seen = 2
            session.checker = lambda: False
            ok, _why = _consider_finish(session, "xong", task="đổi số")
            self.assertFalse(ok)
            self.assertFalse((root / ".mira" / "facts.jsonl").exists())
            session.checker = lambda: True
            ok, _why = _consider_finish(session, "bài worker rất dài không được chép", task="đổi số")
            self.assertTrue(ok)
            text = (root / ".mira" / "facts.jsonl").read_text(encoding="utf-8")
            self.assertIn("đã kiểm", text)
            self.assertNotIn("bài worker", text)
            session.lane_seen = 0
            before = text
            ok, _why = _consider_finish(session, "xong", task="đổi số lần nữa")
            self.assertTrue(ok)
            self.assertEqual((root / ".mira" / "facts.jsonl").read_text(encoding="utf-8"), before)


if __name__ == "__main__":
    unittest.main()
