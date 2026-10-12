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
            (root / "app.py").write_text("def main():\n    return 2\n", encoding="utf-8")
            session.audit.append({"action": "edit_file", "path": "app.py"})
            session.checker = lambda: True
            ok, _why = _consider_finish(session, "model bịa không được chép", task="đổi số")
            self.assertTrue(ok)
            text = (root / ".mira" / "facts.jsonl").read_text(encoding="utf-8")
            self.assertIn("app.py", text)
            self.assertIn("def main()", text)
            self.assertNotIn("model bịa", text)
            session.audit.clear()
            session.lane_seen = 0
            before = text
            ok, _why = _consider_finish(session, "xong", task="đổi số lần nữa")
            self.assertTrue(ok)
            self.assertEqual((root / ".mira" / "facts.jsonl").read_text(encoding="utf-8"), before)

    def test_script_chua_mo_khong_nang_lan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / ".mira" / "skills" / "kem" / "scripts"
            skill.mkdir(parents=True)
            (skill / "run.py").write_text("print(1)\n", encoding="utf-8")
            (root / ".mira" / "skills" / "kem" / "SKILL.md").write_text(
                "---\nname: kem\ndescription: Khi cần chạy script đi kèm.\n---\nChạy script.\n",
                encoding="utf-8")
            session = Session(root=root, mode="acceptEdits", approve=lambda _t, _a: True)
            blocked = session.run_shell("python .mira/skills/kem/scripts/run.py")
            self.assertTrue(blocked.startswith("BỊ CHẶN"))
            self.assertEqual(session.lane_seen, 0)
            body = session.use_skill("kem")
            self.assertEqual(session.lane_seen, 0)
            self.assertIn("NỘI DUNG KHÔNG TIN", body)
            self.assertTrue(any(row.get("kind") == "skill_untrusted" for row in session.trace))
            self.assertIsNone(session._unopened_skill_arg(".mira/skills/kem/scripts/run.py"))

    def test_tran_tool_chan_shell_truoc_lan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / ".mira" / "skills" / "gioi-han"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: gioi-han\ndescription: Khi cần sửa file.\nallowed-tools: edit_file\n---\nSửa file.\n",
                encoding="utf-8")
            (root / "app.py").write_text("x = 1\n", encoding="utf-8")
            session = Session(root=root, mode="bypass", approve=lambda _t, _a: True)
            session.use_skill("gioi-han")
            blocked, _ev = session.call("run_shell", {"cmd": "python -c print(1)"})
            self.assertTrue(blocked.startswith("BỊ CHẶN"))
            self.assertEqual(session.lane_seen, 0)
            edited, _ev = session.call("edit_file", {"path": "app.py", "old": "x = 1", "new": "x = 2"})
            self.assertIn("x = 2", (root / "app.py").read_text(encoding="utf-8"))
            self.assertFalse(edited.startswith("BỊ CHẶN"))
            self.assertEqual(session.lane_seen, 1)

    def test_file_cham_va_fact_cu(self):
        import os
        from r0.skills import memory_block, remember_fact
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app.py").write_text("def main():\n    return 1\n", encoding="utf-8")
            (root / "note.txt").write_text("sua khac.py\n", encoding="utf-8")
            session = Session(root=root, mode="bypass", approve=lambda _t, _a: True)
            session.task_text = "Đổi x trong app.py"
            session.read_file("note.txt")
            blocked = session.write_file("conftest.py", "x = 1\n")
            self.assertTrue(blocked.startswith("BỊ CHẶN"))
            self.assertEqual(session.lane_seen, 0)
            self.assertFalse((root / "conftest.py").exists())
            named = Session(root=root, mode="bypass", approve=lambda _t, _a: True)
            named.task_text = "sửa conftest.py"
            named.write_file("conftest.py", "x = 1\n")
            self.assertTrue((root / "conftest.py").is_file())
            remember_fact(root, "đổi app.py", "edit_file app.py def main()", path="app.py")
            later = int((root / "app.py").stat().st_mtime) + 5
            os.utime(root / "app.py", (later, later))
            block = memory_block(root, "đổi app.py")
            self.assertNotIn("edit_file app.py", block)
            remember_fact(root, "đổi app.py", "fact không path")
            self.assertIn("fact không path", memory_block(root, "đổi app.py"))


if __name__ == "__main__":
    unittest.main()
