import tempfile
import unittest
from pathlib import Path

from r0.tools import TOOL_SPECS, Session


class ToolsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "a.py").write_text("x = 1\ny = 2\nx = 3\n", encoding="utf-8")
        (self.root / "sub").mkdir()
        (self.root / "sub" / "b.txt").write_text("hi", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def _sess(self, mode="default", approve=True):
        return Session(root=self.root, mode=mode,
                       approve=(lambda t, a: True) if approve else (lambda t, a: False))

    def test_catalog_has_new_tools(self):
        for t in ("glob", "edit_file", "delete_file", "fetch_url", "todo_write"):
            self.assertIn(t, TOOL_SPECS)

    def test_glob(self):
        self.assertIn("a.py", self._sess().glob("**/*.py"))

    def test_edit_nhieu_cho_thi_loi(self):
        r = self._sess().edit_file("a.py", "x = ", "z = ")
        self.assertTrue(r.startswith("LỖI"))
        self.assertEqual((self.root / "a.py").read_text(), "x = 1\ny = 2\nx = 3\n")

    def test_edit_count(self):
        self._sess().edit_file("a.py", "x = ", "z = ", count=1)
        self.assertEqual((self.root / "a.py").read_text(), "z = 1\ny = 2\nx = 3\n")

    def test_edit_missing_old(self):
        self.assertTrue(self._sess().edit_file("a.py", "KHONGCO", "y").startswith("LỖI"))

    def test_read_window(self):
        lines = "\n".join(f"dong {i}" for i in range(1, 121))
        (self.root / "dai.txt").write_text(lines, encoding="utf-8")
        s = self._sess()
        first = s.read_file("dai.txt")
        self.assertIn("dòng 1-100 / 120", first)
        self.assertIn("1|dong 1", first)
        self.assertNotIn("dong 101", first)
        rest = s.read_file("dai.txt", start=101, n=100)
        self.assertIn("101|dong 101", rest)
        self.assertIn("120|dong 120", rest)

    def test_grep_lists_files_not_lines(self):
        hit = self._sess().grep("x = ", ".")
        self.assertIn("a.py", hit)
        self.assertIn("2 chỗ", hit)
        self.assertNotIn("y = 2", hit)

    def test_edit_rejects_bad_python(self):
        before = (self.root / "a.py").read_text(encoding="utf-8")
        out = self._sess().edit_file("a.py", "y = 2", "y = ")
        self.assertTrue(out.startswith("LỖI"))
        self.assertEqual((self.root / "a.py").read_text(encoding="utf-8"), before)

    def test_shell_empty_output(self):
        import shlex, sys
        cmd = shlex.join([sys.executable, "-c", "pass"])
        out = self._sess().run_shell(cmd)
        self.assertIn("lệnh chạy xong, không có đầu ra", out)
        self.assertIn("mã thoát 0", out)

    def test_edit_gated(self):
        self.assertIn("TỪ CHỐI", self._sess(approve=False).edit_file("a.py", "y = 2", "y = 9"))

    def test_plan_blocks_edit(self):
        self.assertTrue(self._sess(mode="plan").edit_file("a.py", "y = 2", "y = 9").startswith("BỊ CHẶN"))

    def test_delete_works_and_gated(self):
        s = self._sess()
        self.assertIn("đã xoá", s.delete_file("sub/b.txt"))
        self.assertFalse((self.root / "sub" / "b.txt").exists())
        self.assertIn("TỪ CHỐI", self._sess(approve=False).delete_file("a.py"))

    def test_delete_dir_refused(self):
        self.assertTrue(self._sess().delete_file("sub").startswith("LỖI"))

    def test_fetch_gated_and_scheme(self):
        self.assertIn("TỪ CHỐI", self._sess(approve=False).fetch_url("https://example.com"))
        self.assertTrue(self._sess().fetch_url("ftp://x").startswith("LỖI"))

    def test_todo_write(self):
        s = self._sess()
        self.assertIn("đọc", s.todo_write(["đọc", "sửa"]))
        self.assertEqual(len(s.todos), 2)

    def test_call_dispatch(self):
        res, ev = self._sess().call("glob", {"pattern": "*.py"})
        self.assertIn("a.py", res)
        self.assertTrue(ev.ok)


class ExtraToolsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "a.py").write_text("x = 1\ny = 2\n", encoding="utf-8")
        (self.root / "b.py").write_text("z = 9\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def _sess(self, **kw):
        kw.setdefault("mode", "default")
        kw.setdefault("approve", lambda t, a: True)
        return Session(root=self.root, **kw)

    def test_multi_edit_two_files(self):
        s = self._sess()
        r = s.multi_edit([{"path": "a.py", "old": "x = 1", "new": "x = 10"},
                          {"path": "b.py", "old": "z = 9", "new": "z = 0"}])
        self.assertIn("đã sửa", r)
        self.assertIn("x = 10", (self.root / "a.py").read_text())
        self.assertIn("z = 0", (self.root / "b.py").read_text())

    def test_multi_edit_aborts_all_on_one_bad(self):
        s = self._sess()
        r = s.multi_edit([{"path": "a.py", "old": "x = 1", "new": "x = 10"},
                          {"path": "a.py", "old": "KHONGCO", "new": "y"}])
        self.assertTrue(r.startswith("LỖI"))
        self.assertIn("x = 1", (self.root / "a.py").read_text())

    def test_multi_edit_gated_and_plan(self):
        self.assertIn("TỪ CHỐI", self._sess(approve=lambda t, a: False)
                      .multi_edit([{"path": "a.py", "old": "x", "new": "y"}]))
        self.assertTrue(self._sess(mode="plan")
                        .multi_edit([{"path": "a.py", "old": "x", "new": "y"}]).startswith("BỊ CHẶN"))

    def test_web_search_no_key(self):
        import os
        from r0 import keys
        old = keys.KEYS_PATH
        keys.KEYS_PATH = self.root / "khong-co-keys.json"
        try:
            for v in ("TAVILY_API_KEY", "BRAVE_API_KEY", "SERPER_API_KEY"):
                os.environ.pop(v, None)
            self.assertTrue(self._sess().web_search("hello", provider="tavily").startswith("LỖI"))
        finally:
            keys.KEYS_PATH = old

    def test_web_search_with_stub(self):
        import os
        os.environ["TAVILY_API_KEY"] = "x"
        import r0.tools as T
        orig = T._do_search
        T._do_search = lambda prov, key, q, n: [{"title": "T", "url": "u", "snippet": "s"}]
        try:
            session = self._sess()
            session.task_text = "tìm hello"
            r = session.web_search("hello")
            self.assertTrue(session.saw_untrusted)
            blocked = session.write_file("khac.py", "y = 9\n")
            self.assertTrue(blocked.startswith("BỊ CHẶN"))
            self.assertEqual(session.lane_seen, 2)
        finally:
            T._do_search = orig
            os.environ.pop("TAVILY_API_KEY", None)
        self.assertIn("1. T", r)

    def test_web_search_gated_and_plan(self):
        self.assertIn("TỪ CHỐI", self._sess(approve=lambda t, a: False).web_search("q"))
        self.assertTrue(self._sess(mode="plan").web_search("q").startswith("BỊ CHẶN"))

    def test_task_formats(self):
        s = self._sess()
        s.spawn = lambda t, d, mt, mb: {"status": "ok", "turns": 2, "costUsd": 0.01,
                                        "final": "xong"}
        r = s.task("việc nhỏ")
        self.assertIn("ok", r)
        self.assertIn("xong", r)

    def test_task_depth_limit(self):
        s = self._sess()
        s.spawn = lambda *a: {"status": "ok", "final": "x"}
        s.depth = s.max_depth
        self.assertTrue(s.task("x").startswith("LỖI"))

    def test_task_no_spawn(self):
        self.assertTrue(self._sess().task("x").startswith("LỖI"))

    def test_catalog_and_schemas_synced(self):
        from r0.native import SCHEMAS
        self.assertEqual(set(TOOL_SPECS), set(SCHEMAS))

    def test_skill_mang_chi_mot_file(self):
        import r0.tools as T
        doc = "---\nname: tim-mua\ndescription: Khi cần tìm mưa.\n---\nchạy scripts/run.py\n"
        orig_block, orig_text = T._https_block_reason, T._https_text
        T._https_block_reason = lambda url: None
        T._https_text = lambda url, limit: doc
        try:
            session = self._sess(mode="bypass")
            session.shape = "hoi"
            out = session.install_skill("https://example.com/SKILL.md")
            self.assertIn("đã cài skill tim-mua", out)
            base = self.root / ".mira" / "skills" / "tim-mua"
            self.assertTrue((base / "SKILL.md").is_file())
            self.assertFalse((base / "scripts").exists())
            self.assertTrue(session.install_skill("https://example.com/SKILL.md").startswith("LỖI"))
            refused = self._sess(approve=False)
            self.assertIn("TỪ CHỐI", refused.install_skill("https://example.com/SKILL.md"))
        finally:
            T._https_block_reason, T._https_text = orig_block, orig_text

    def test_tim_html_va_mcp_khong_them_tool(self):
        from r0.tools import _mcp_payload, _mcp_text, parse_search_html
        rows = parse_search_html(
            '<a href="https://duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fskill">mưa</a>', 3)
        self.assertEqual(rows[0]["url"], "https://example.com/skill")
        payload = _mcp_payload('data: {"jsonrpc":"2.0","result":{"tools":[{"name":"tra","description":"tra cứu"}]}}')
        text = _mcp_text(payload["result"])
        self.assertIn("NỘI DUNG KHÔNG TIN", text)
        self.assertIn("tra", text)
        self.assertTrue(self._sess().mcp_call("https://example.com/mcp", "rm -rf", {}).startswith("LỖI"))


if __name__ == "__main__":
    unittest.main()
