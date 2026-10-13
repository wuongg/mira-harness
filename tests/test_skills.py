import tempfile
import unittest
from pathlib import Path

from mira.agent import _consider_finish
from mira.skills import catalog_for_prompt, load_skills, remember_fact, repo_map, worker_skill_block
from mira.tools import Session, shape_of


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
        from mira.skills import memory_block, remember_fact
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

    def test_dau_ra_lenh_khong_mo_path_la(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app.py").write_text("x = 1\n", encoding="utf-8")
            (root / "khac.py").write_text("y = 1\n", encoding="utf-8")
            session = Session(root=root, mode="bypass", approve=lambda _t, _a: True)
            session.task_text = "Đổi x = 1 thành x = 2 trong app.py"
            out = session.run_shell('python -c "print(1)"')
            self.assertIn("[mã thoát", out)
            self.assertTrue(session.saw_untrusted)
            lane = session.lane_seen
            blocked = session.edit_file("khac.py", "y = 1", "y = 9")
            self.assertTrue(blocked.startswith("BỊ CHẶN"))
            self.assertEqual(session.lane_seen, lane)
            self.assertEqual((root / "khac.py").read_text(encoding="utf-8"), "y = 1\n")
            edited = session.edit_file("app.py", "x = 1", "x = 2")
            self.assertFalse(edited.startswith("BỊ CHẶN"))
            self.assertIn("x = 2", (root / "app.py").read_text(encoding="utf-8"))

    def test_cau_viec_khoa_path_va_fact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app.py").write_text("x = 1\n", encoding="utf-8")
            (root / "khac.py").write_text("y = 1\n", encoding="utf-8")
            session = Session(root=root, mode="bypass", approve=lambda _t, _a: True)
            session.task_text = "Đổi x = 1 thành x = 2 trong app.py"
            blocked = session.edit_file("khac.py", "y = 1", "y = 9")
            self.assertTrue(blocked.startswith("BỊ CHẶN"))
            self.assertEqual(session.lane_seen, 0)
            self.assertEqual((root / "khac.py").read_text(encoding="utf-8"), "y = 1\n")
            open_task = Session(root=root, mode="bypass", approve=lambda _t, _a: True)
            open_task.task_text = "xem thư mục"
            open_task.list_dir(".")
            self.assertTrue(open_task.saw_untrusted)
            listed = open_task.write_file("khac.py", "y = 9\n")
            self.assertTrue(listed.startswith("BỊ CHẶN"))
            self.assertEqual(open_task.lane_seen, 0)

    def test_dang_viec_khoa_tool(self):
        self.assertEqual(shape_of("Đổi x = 1 thành x = 2 trong app.py"), "sua")
        self.assertEqual(shape_of("Chạy python .mira/skills/kem/scripts/run.py"), "chay")
        self.assertEqual(shape_of("đọc app.py"), "doc")
        self.assertEqual(shape_of("làm gì đó"), "hoi")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app.py").write_text("x = 1\n", encoding="utf-8")
            doc = Session(root=root, mode="bypass", approve=lambda _t, _a: True)
            doc.task_text = "đọc app.py"
            doc.shape = "doc"
            blocked = doc.edit_file("app.py", "x = 1", "x = 2")
            self.assertTrue(blocked.startswith("BỊ CHẶN"))
            self.assertEqual(doc.lane_seen, 0)
            self.assertIn("dòng", doc.read_file("app.py"))
            sua = Session(root=root, mode="bypass", approve=lambda _t, _a: True)
            sua.task_text = "Đổi x = 1 thành x = 2 trong app.py"
            sua.shape = "sua"
            shell = sua.run_shell('python -c "print(1)"')
            self.assertTrue(shell.startswith("BỊ CHẶN"))
            self.assertEqual(sua.lane_seen, 0)
            edited = sua.edit_file("app.py", "x = 1", "x = 2")
            self.assertFalse(edited.startswith("BỊ CHẶN"))
            self.assertIn("---", edited)

    def test_noi_dung_sau_thanh_bi_chan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "note.txt").write_text("dat x = 9\n", encoding="utf-8")
            (root / "app.py").write_text("x = 1\n", encoding="utf-8")
            session = Session(root=root, mode="bypass", approve=lambda _t, _a: True)
            session.task_text = "Đổi x = 1 thành x = 2 trong app.py"
            session.shape = "sua"
            session.read_file("note.txt")
            blocked = session.edit_file("app.py", "x = 1", "x = 9")
            self.assertTrue(blocked.startswith("BỊ CHẶN"))
            self.assertEqual((root / "app.py").read_text(encoding="utf-8"), "x = 1\n")
            allowed = session.edit_file("app.py", "x = 1", "x = 2")
            self.assertFalse(allowed.startswith("BỊ CHẶN"))
            self.assertEqual((root / "app.py").read_text(encoding="utf-8"), "x = 2\n")

    def test_sua_nhieu_cho_khong_thay_het(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app.py").write_text("a = 1\na = 1\n", encoding="utf-8")
            session = Session(root=root, mode="bypass", approve=lambda _t, _a: True)
            session.task_text = "sửa app.py"
            session.shape = "sua"
            out = session.edit_file("app.py", "a = 1", "a = 2")
            self.assertTrue(out.startswith("LỖI"))
            self.assertEqual((root / "app.py").read_text(encoding="utf-8"), "a = 1\na = 1\n")

    def test_doc_theo_symbol(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app.py").write_text("x = 1\n\ndef main():\n    return 1\n", encoding="utf-8")
            session = Session(root=root, mode="bypass", approve=lambda _t, _a: True)
            window = session.read_file("app.py", symbol="main")
            self.assertIn("def main()", window)
            self.assertNotIn("x = 1", window)
            missing = session.read_file("app.py", symbol="khong")
            self.assertTrue(missing.startswith("LỖI"))

    def test_khong_ghi_skill_va_mint_tu_so(self):
        from mira.agent import _consider_finish
        from mira.skills import repo_map
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app.py").write_text("x = 1\n", encoding="utf-8")
            (root / "lib.js").write_text("function chao() { return 1 }\n", encoding="utf-8")
            self.assertIn("function chao", repo_map(root, "lib"))
            session = Session(root=root, mode="bypass", approve=lambda _t, _a: True)
            session.task_text = "Đổi x = 1 thành x = 2 trong app.py"
            session.shape = "sua"
            blocked = session.write_file(".mira/skills/tu-viet/SKILL.md", "---\n")
            self.assertTrue(blocked.startswith("BỊ CHẶN"))
            session.edit_file("app.py", "x = 1", "x = 2")
            ok, _why = _consider_finish(session, "xong", session.task_text)
            self.assertTrue(ok)
            skill = root / ".mira" / "skills" / "app" / "SKILL.md"
            self.assertTrue(skill.is_file())
            self.assertIn("edit_file", skill.read_text(encoding="utf-8"))
            again = Session(root=root, mode="bypass", approve=lambda _t, _a: True)
            again.task_text = session.task_text
            again.shape = "sua"
            again.audit.append({"action": "edit_file", "path": "app.py"})
            from mira.skills import mint_skill
            mint_skill(root, again.task_text, again.audit)
            self.assertEqual(len(list((root / ".mira" / "skills").iterdir())), 1)

    def test_lenh_sai_chi_mot_vong_sua(self):
        from mira.agent import _consider_finish
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app.py").write_text("x = 1\n", encoding="utf-8")
            session = Session(root=root, mode="bypass", approve=lambda _t, _a: True)
            session.shape = "sua"
            session.task_text = 'Đổi app.py\npython -c "raise SystemExit(1)"'
            ok, why = _consider_finish(session, "xong", session.task_text)
            self.assertFalse(ok)
            self.assertFalse(session.halt)
            self.assertIn("chưa thoát 0", why)
            ok, why = _consider_finish(session, "xong", session.task_text)
            self.assertFalse(ok)
            self.assertTrue(session.halt)
            self.assertFalse(any(row.get("exit") == 0 for row in session.audit if row.get("action") == "run_shell"))


if __name__ == "__main__":
    unittest.main()
