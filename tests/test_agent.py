"""Kiểm chứng agent CLI bằng SERVER GIẢ có streaming + vòng lặp công cụ.

Kiểm được cả nhánh: streaming SSE, gọi công cụ rồi lặp, cổng xin phép,
chế độ plan chặn ghi, chặn thoát khỏi thư mục gốc, và dạng envelope JSON.
"""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from r0 import agent, tools                     # noqa: E402
from r0.providers import AnthropicProvider      # noqa: E402
from r0.stream import stream                    # noqa: E402
from r0.tools import Session                    # noqa: E402

SEEN: list[dict] = []


class _Stub(BaseHTTPRequestHandler):
    """Trả lời theo vòng: lượt đầu gọi công cụ, lượt sau kết thúc."""

    def log_message(self, *a):
        pass

    def _sse(self, chunks: list[str], usage_in=100, usage_out=20):
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.end_headers()
        ev = [("message_start", {"type": "message_start",
                                 "message": {"usage": {"input_tokens": usage_in}}})]
        for c in chunks:
            ev.append(("content_block_delta",
                       {"type": "content_block_delta",
                        "delta": {"type": "text_delta", "text": c}}))
        ev.append(("message_delta", {"type": "message_delta",
                                     "usage": {"output_tokens": usage_out}}))
        for name, data in ev:
            self.wfile.write(f"event: {name}\ndata: {json.dumps(data)}\n\n".encode())
            self.wfile.flush()
        self.wfile.write(b"event: message_stop\ndata: {\"type\":\"message_stop\"}\n\n")
        self.wfile.flush()

    def do_POST(self):
        n = int(self.headers.get("content-length", 0))
        req = json.loads(self.rfile.read(n) or b"{}")
        blob = json.dumps(req, ensure_ascii=False)
        SEEN.append({"path": self.path, "req": req})
        streamed = bool(req.get("stream"))
        # Lượt đầu: yêu cầu đọc tệp. Lượt sau (đã có <result>): kết thúc.
        if "<result>" in blob:
            text = 'XONG\n<tool>{"name":"finish","args":{"summary":"đã đọc tệp và tóm tắt"}}</tool>'
        elif "STREAM_TEXT" in blob:
            text = "chỉ văn bản, không gọi công cụ"
        else:
            text = 'Đọc tệp nhé.\n<tool>{"name":"read_file","args":{"path":"a.txt"}}</tool>'
        if streamed:
            return self._sse([text[i:i + 12] for i in range(0, len(text), 12)])
        raw = json.dumps({"content": [{"type": "text", "text": text}],
                          "usage": {"input_tokens": 100, "output_tokens": 20}}).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def _serve():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Stub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


class TestStreaming(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv, cls.base = _serve()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def test_doc_dung_sse_va_ghep_van_ban(self):
        got: list[str] = []
        p = AnthropicProvider(model="claude-x", api_key="k", base_url=self.base)
        text, u = stream(p, "SYS", "STREAM_TEXT", on_text=got.append)
        self.assertIn("chỉ văn bản", text)
        self.assertEqual("".join(got), text, "ghép từng mảnh phải bằng toàn văn")
        self.assertEqual(u, {"in": 100, "out": 20})
        self.assertTrue(SEEN[-1]["req"]["stream"])


class TestVongLapCongCu(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv, cls.base = _serve()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def _session(self, mode="default", approve=None, files=None):
        d = tempfile.TemporaryDirectory()
        root = Path(d.name)
        for name, content in (files or {}).items():
            (root / name).write_text(content, encoding="utf-8")
        return d, Session(root=root, mode=mode, approve=approve)

    def test_doc_tep_roi_ket_thuc(self):
        d, s = self._session(files={"a.txt": "NỘI DUNG THẬT"})
        seen_tools = []
        res = agent.run_turn(task="đọc a.txt", session=s, model="claude-x",
                             provider_name="anthropic", base_url=self.base, api_key="k",
                             protocol="text", price_in=(1.0, 1.0),
                             on_text=lambda _t: None, on_tool=lambda n, a: seen_tools.append(n))
        self.assertEqual(res["status"], "ok")
        self.assertEqual(seen_tools, ["read_file"], "phải gọi đúng một công cụ")
        self.assertEqual(res["turns"], 2, "lượt 1 gọi công cụ, lượt 2 kết thúc")
        self.assertIn("đã đọc tệp", res["final"])
        self.assertIn("read_file", res["toolSummary"]["tools"])
        d.cleanup()

    def test_ket_qua_cong_cu_duoc_tra_lai_model(self):
        d, s = self._session(files={"a.txt": "NỘI DUNG THẬT"})
        SEEN.clear()
        agent.run_turn(task="đọc a.txt", session=s, model="claude-x",
                       provider_name="anthropic", base_url=self.base, api_key="k",
                       protocol="text", price_in=(1.0, 1.0),
                       on_text=lambda _t: None)
        self.assertEqual(len(SEEN), 2)
        self.assertIn("<result>", json.dumps(SEEN[-1]["req"], ensure_ascii=False),
                      "lượt 2 phải mang kết quả công cụ")
        self.assertIn("NỘI DUNG THẬT", json.dumps(SEEN[-1]["req"], ensure_ascii=False))
        d.cleanup()

    def test_envelope_co_du_truong(self):
        d, s = self._session(files={"a.txt": "x"})
        res = agent.run_turn(task="đọc a.txt", session=s, model="sonnet-5.5",
                             provider_name="anthropic", base_url=self.base, api_key="k",
                             protocol="text",
                             on_text=lambda _t: None)
        env = agent.envelope("đọc a.txt", res, s, "sess-1")
        for k in ("ok", "status", "final", "usage", "costUsd", "assistantTurns",
                  "toolSummary", "model", "provider", "sessionId", "mode"):
            self.assertIn(k, env, f"thiếu {k}")
        self.assertTrue(env["ok"])
        self.assertEqual(env["usage"]["total"], 240)
        self.assertEqual(env["assistantTurns"], 2)
        self.assertIsNotNone(env["costUsd"])
        d.cleanup()


class TestCongXinPhep(unittest.TestCase):
    def _session(self, mode, approve, files=None):
        d = tempfile.TemporaryDirectory()
        root = Path(d.name)
        for name, content in (files or {}).items():
            (root / name).write_text(content, encoding="utf-8")
        return d, Session(root=root, mode=mode, approve=approve)

    def test_plan_chan_ghi_va_tao_tep_khong_ton_tai(self):
        d, s = self._session("plan", None)
        out = s.write_file("moi.txt", "x")
        self.assertIn("BỊ CHẶN", out)
        self.assertFalse((Path(d.name) / "moi.txt").exists(), "chế độ plan KHÔNG được tạo tệp")
        d.cleanup()

    def test_default_tu_choi_thi_khong_ghi(self):
        d, s = self._session("default", lambda t, a: False)
        out = s.write_file("moi.txt", "x")
        self.assertIn("TỪ CHỐI", out)
        self.assertFalse((Path(d.name) / "moi.txt").exists())
        d.cleanup()

    def test_accept_edits_thi_ghi_va_co_audit(self):
        d, s = self._session("acceptEdits", None)
        out = s.write_file("moi.txt", "nội dung")
        self.assertIn("đã ghi", out)
        self.assertTrue((Path(d.name) / "moi.txt").exists())
        self.assertEqual(s.audit[-1]["action"], "write_file")
        self.assertFalse(s.audit[-1]["overwrote"])
        d.cleanup()

    def test_run_shell_luon_phai_duoc_duyet(self):
        d, s = self._session("acceptEdits", lambda t, a: False)
        out = s.run_shell("echo xin-chao")
        self.assertIn("TỪ CHỐI", out)
        d.cleanup()

    def test_run_shell_chay_that_khi_duoc_duyet(self):
        d, s = self._session("default", lambda t, a: True)
        import shlex
        cmd = shlex.join([sys.executable, "-c", "print('xin-chao')"])
        out = s.run_shell(cmd)
        self.assertIn("xin-chao", out)
        self.assertIn("mã thoát 0", out)
        d.cleanup()

    def test_chan_thoat_khoi_thu_muc_goc(self):
        d, s = self._session("acceptEdits", None)
        with self.assertRaises(PermissionError):
            s.read_file("../../../etc/passwd")
        with self.assertRaises(PermissionError):
            s.write_file("../ngoai.txt", "x")
        d.cleanup()

    def test_grep_va_list_dir(self):
        d, s = self._session("default", None, files={"a.txt": "dòng một\nkim cương\n"})
        self.assertIn("a.txt", s.grep("kim", "."))
        self.assertIn("1 chỗ", s.grep("kim", "."))
        self.assertNotIn("kim cương", s.grep("kim", "."))
        self.assertIn("a.txt", s.list_dir("."))
        d.cleanup()


class TestParseTool(unittest.TestCase):
    def test_doc_khoi_tool(self):
        self.assertEqual(tools.parse_tool('x <tool>{"name":"read_file","args":{"path":"a"}}</tool>'),
                         ("read_file", {"path": "a"}))

    def test_khong_co_khoi_thi_tra_none(self):
        self.assertIsNone(tools.parse_tool("chỉ là văn bản"))

    def test_json_hong_thi_tra_none(self):
        self.assertIsNone(tools.parse_tool("<tool>{khong phai json}</tool>"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
