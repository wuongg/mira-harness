import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from frog import activity


def _write(p: Path, meta: dict, msgs: list[dict], evs: list[dict]) -> None:
    with p.open("w", encoding="utf-8") as f:
        f.write(json.dumps({"type": "meta", **meta}, ensure_ascii=False) + "\n")
        for m in msgs:
            f.write(json.dumps({"type": "message", **m}, ensure_ascii=False) + "\n")
        for e in evs:
            f.write(json.dumps({"type": "event", **e}, ensure_ascii=False) + "\n")


class _A:
    session = None
    limit = 0


class ActivityTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._d = activity.SESS_DIR
        activity.SESS_DIR = Path(self.tmp.name)

    def tearDown(self):
        activity.SESS_DIR = self._d
        self.tmp.cleanup()

    def test_empty(self):
        self.assertEqual(activity.list_sessions(), [])

    def test_load_and_totals(self):
        _write(activity.SESS_DIR / "a.jsonl",
               {"session": "a", "model": "sonnet-5.5", "turns": 3,
                "cost_usd": 0.05, "tokens": {"in": 1000, "out": 200},
                "first_task": "viết báo cáo"},
               [{"role": "user", "content": "viết báo cáo"}],
               [{"type": "event", "tool": "read", "path": "x.py"},
                {"type": "event", "tool": "read", "path": "y.py"},
                {"type": "event", "tool": "bash", "cmd": "ls"}])
        sess = activity.list_sessions()
        self.assertEqual(len(sess), 1)
        s = sess[0]
        self.assertEqual(s["turns"], 3)
        self.assertEqual(s["tools"]["read"], 2)
        self.assertAlmostEqual(s["cost"], 0.05)
        t = activity.totals(sess)
        self.assertEqual(t["turns"], 3)
        self.assertEqual(t["tok_in"], 1000)
        self.assertEqual(t["tools"]["bash"], 1)

    def test_render_no_crash(self):
        _write(activity.SESS_DIR / "b.jsonl", {"session": "b"}, [], [])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            activity.render_detail(activity.list_sessions()[0])
            activity.render_dashboard()
            activity.render_list([])
        self.assertTrue(buf.getvalue())

    def test_missing_session_returns_2(self):
        a = _A()
        a.session = "nope"
        self.assertEqual(activity.cmd_logs(a), 2)

    def test_list_returns_2_for_bad_id(self):
        a = _A()
        a.session = "zzz"
        self.assertEqual(activity.cmd_logs(a), 2)

    def test_corrupt_lines_skipped(self):
        p = activity.SESS_DIR / "c.jsonl"
        p.write_text('{"type":"meta","session":"c","turns":1}\nNOT JSON\n',
                     encoding="utf-8")
        s = activity.list_sessions()[0]
        self.assertEqual(s["turns"], 1)


class ExportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._d = activity.SESS_DIR
        activity.SESS_DIR = Path(self.tmp.name)

    def tearDown(self):
        activity.SESS_DIR = self._d
        self.tmp.cleanup()

    def test_export_formats(self):
        _write(activity.SESS_DIR / "d.jsonl",
               {"session": "d", "model": "sonnet-5.5", "turns": 2, "cost_usd": 0.01,
                "tokens": {"in": 500, "out": 100}, "first_task": "x"},
               [{"role": "user", "content": "x"}],
               [{"type": "event", "tool": "read", "path": "a.py"}])
        for fmt in ("md", "json", "csv"):
            p = activity.export_report(what="all", fmt=fmt,
                                       out=str(Path(self.tmp.name) / ("o." + fmt)))
            self.assertTrue(p.exists())
            self.assertIn("d", p.read_text(encoding="utf-8"))

    def test_cmd_export_lab(self):
        from types import SimpleNamespace
        a = SimpleNamespace(what="lab", format="md", run=None,
                            out=str(Path(self.tmp.name) / "lab.md"))
        self.assertEqual(activity.cmd_export(a), 0)
        self.assertTrue((Path(self.tmp.name) / "lab.md").exists())


if __name__ == "__main__":
    unittest.main()
