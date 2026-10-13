"""Kiểm native tool-calling — server giả nói đúng định dạng dây của từng hãng.

Kiểm được: dịch tham số hai chiều, đọc tool_use/tool_calls cả streaming lẫn
không, gọi SONG SONG nhiều công cụ trong một lượt, và tool_result quay lại model.
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

from mira import agent, native                      # noqa: E402
from mira.providers import AnthropicProvider, OpenAICompatProvider  # noqa: E402
from mira.tools import Session                      # noqa: E402

SEEN: list[dict] = []


class _Stub(BaseHTTPRequestHandler):
    """Nói cả hai định dạng. Lượt đầu gọi công cụ, lượt sau finish."""

    def log_message(self, *a):
        pass

    def _payload(self, req):
        blob = json.dumps(req, ensure_ascii=False)
        has_result = ('"tool_result"' in blob) or ('"role": "tool"' in blob)
        if has_result:
            return [{"type": "text", "text": "Đã xong."},
                    {"type": "tool_use", "id": "c_fin", "name": "finish",
                     "input": {"summary": "đã đọc hai tệp"}}]
        return [{"type": "tool_use", "id": "c1", "name": "read_file", "input": {"path": "a.txt"}},
                {"type": "tool_use", "id": "c2", "name": "read_file", "input": {"path": "b.txt"}}]

    def _anthropic(self, blocks, streamed):
        if not streamed:
            data = {"content": [({"type": "text", "text": b["text"]} if b["type"] == "text"
                                 else {"type": "tool_use", "id": b["id"], "name": b["name"],
                                       "input": b["input"]}) for b in blocks],
                    "usage": {"input_tokens": 150, "output_tokens": 30}}
            raw = json.dumps(data).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.end_headers()

        def ev(name, data):
            self.wfile.write(f"event: {name}\ndata: {json.dumps(data)}\n\n".encode())
            self.wfile.flush()

        ev("message_start", {"type": "message_start",
                             "message": {"usage": {"input_tokens": 150}}})
        for i, b in enumerate(blocks):
            if b["type"] == "text":
                ev("content_block_start", {"type": "content_block_start", "index": i,
                                           "content_block": {"type": "text", "text": ""}})
                ev("content_block_delta", {"type": "content_block_delta", "index": i,
                                           "delta": {"type": "text_delta", "text": b["text"]}})
            else:
                ev("content_block_start", {"type": "content_block_start", "index": i,
                                           "content_block": {"type": "tool_use", "id": b["id"],
                                                             "name": b["name"], "input": {}}})
                frag = json.dumps(b["input"], ensure_ascii=False)
                for k in range(0, len(frag), 7):
                    ev("content_block_delta",
                       {"type": "content_block_delta", "index": i,
                        "delta": {"type": "input_json_delta",
                                  "partial_json": frag[k:k + 7]}})
            ev("content_block_stop", {"type": "content_block_stop", "index": i})
        ev("message_delta", {"type": "message_delta", "usage": {"output_tokens": 30}})

    def _openai(self, blocks, streamed):
        calls = [{"id": b["id"], "type": "function",
                  "function": {"name": b["name"],
                               "arguments": json.dumps(b["input"], ensure_ascii=False)}}
                 for b in blocks if b["type"] == "tool_use"]
        text = "".join(b["text"] for b in blocks if b["type"] == "text")
        if not streamed:
            data = {"choices": [{"message": {"content": text or None,
                                             **({"tool_calls": calls} if calls else {})}}],
                    "usage": {"prompt_tokens": 150, "completion_tokens": 30}}
            raw = json.dumps(data).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.end_headers()

        def chunk(delta, usage=None):
            o = {"choices": [{"delta": delta}]}
            if usage:
                o["usage"] = usage
            self.wfile.write(f"data: {json.dumps(o, ensure_ascii=False)}\n\n".encode())
            self.wfile.flush()

        if text:
            for k in range(0, len(text), 9):
                chunk({"content": text[k:k + 9]})
        for i, c in enumerate(calls):
            frag = c["function"]["arguments"]
            chunk({"tool_calls": [{"index": i, "id": c["id"],
                                   "function": {"name": c["function"]["name"],
                                                "arguments": frag[:5]}}]})
            for k in range(5, len(frag), 6):
                chunk({"tool_calls": [{"index": i,
                                       "function": {"arguments": frag[k:k + 6]}}]})
        chunk({}, {"prompt_tokens": 150, "completion_tokens": 30})
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def do_POST(self):
        n = int(self.headers.get("content-length", 0))
        req = json.loads(self.rfile.read(n) or b"{}")
        SEEN.append({"path": self.path, "req": req})
        blocks = self._payload(req)
        streamed = bool(req.get("stream"))
        if self.path.endswith("/v1/messages"):
            self._anthropic(blocks, streamed)
        else:
            self._openai(blocks, streamed)


def _serve():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Stub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


class TestDichThamSo(unittest.TestCase):
    def test_tool_schema_dung_cho_ca_hai(self):
        t = native.neutral_tools()
        self.assertIn("read_file", [x["name"] for x in t])
        a = native.to_anthropic_tools(t)[0]
        self.assertIn("input_schema", a)
        o = native.to_openai_tools(t)[0]
        self.assertEqual(o["type"], "function")
        self.assertIn("parameters", o["function"])

    def test_tool_result_sang_hai_dinh_dang(self):
        msgs = [{"role": "user", "content": [{"type": "text", "text": "hỏi"}]},
                {"role": "assistant", "content": [
                    {"type": "tool_use", "id": "x1", "name": "read_file", "input": {"path": "a"}}]},
                {"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": "x1", "content": "nội dung"}]}]
        a = native.to_anthropic_messages(msgs)
        self.assertEqual(a[1]["content"][0]["type"], "tool_use")
        self.assertEqual(a[2]["content"][0]["tool_use_id"], "x1")
        o = native.to_openai_messages(msgs)
        self.assertEqual(o[1]["tool_calls"][0]["id"], "x1")
        self.assertEqual(o[2]["role"], "tool")
        self.assertEqual(o[2]["tool_call_id"], "x1")

    def test_lich_su_dang_chu_van_gui_duoc(self):
        o = native.to_openai_messages([
            {"role": "user", "content": "câu trước"},
            {"role": "assistant", "content": "đã nghe"},
            {"role": "user", "content": "## 1. Vai trò"},
        ])
        self.assertEqual(o[0]["content"], "câu trước")
        self.assertEqual(o[1]["content"], "đã nghe")
        self.assertEqual(o[2]["content"], "## 1. Vai trò")

    def test_doc_so_token_con_lai(self):
        from mira.providers import afford_tokens
        detail = 'HTTP 402 — {"error":{"message":"can only afford 900"}}'
        self.assertEqual(afford_tokens(detail), 900)
        self.assertIsNone(afford_tokens("HTTP 401"))


class TestNativeVongLap(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv, cls.base = _serve()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def _session(self):
        d = tempfile.TemporaryDirectory()
        root = Path(d.name)
        (root / "a.txt").write_text("A", encoding="utf-8")
        (root / "b.txt").write_text("B", encoding="utf-8")
        return d, Session(root=root, mode="default", approve=lambda t, a: True)

    def _run(self, provider_name, model, stream_it):
        d, s = self._session()
        SEEN.clear()
        got: list[str] = []
        res = agent.run_turn(task="đọc hai tệp", session=s, model=model,
                             provider_name=provider_name, base_url=self.base,
                             api_key="k", protocol="native", no_stream=not stream_it,
                             price_in=(1.0, 1.0),
                             on_text=got.append, on_tool=lambda n, a: None)
        return d, res, got

    def test_anthropic_stream_goi_song_song_hai_cong_cu(self):
        d, res, got = self._run("anthropic", "claude-x", True)
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["protocol"], "native")
        self.assertEqual(sorted(res["toolSummary"]["tools"]), ["read_file"])
        self.assertEqual(res["toolSummary"]["calls"], 2, "phải gọi 2 công cụ song song")
        self.assertEqual(res["turns"], 2)
        self.assertEqual(res["final"], "đã đọc hai tệp")
        self.assertTrue(got, "phải có văn bản streaming")
        self.assertIn("A", json.dumps(SEEN[-1]["req"], ensure_ascii=False))
        d.cleanup()

    def test_anthropic_khong_stream_cung_chay(self):
        d, res, _ = self._run("anthropic", "claude-x", False)
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["toolSummary"]["calls"], 2)
        d.cleanup()

    def test_openai_stream_goi_song_song(self):
        d, res, _ = self._run("openai", "gpt-x", True)
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["toolSummary"]["calls"], 2)
        self.assertEqual(res["final"], "đã đọc hai tệp")
        d.cleanup()

    def test_openai_khong_stream_cung_chay(self):
        d, res, _ = self._run("openai", "gpt-x", False)
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["toolSummary"]["calls"], 2)
        d.cleanup()

    def test_khong_con_giao_thuc_van_ban(self):
        """Native: đầu ra model KHÔNG được chứa thẻ <tool> nào."""
        d, res, got = self._run("anthropic", "claude-x", True)
        self.assertNotIn("<tool>", "".join(got))
        d.cleanup()

    def test_thieu_key_thi_chan_ngay(self):
        d, s = self._session()
        res = agent.run_turn(task="x", session=s, model="claude-x", provider_name="anthropic",
                             base_url=self.base, api_key="", protocol="native", price_in=(1.0, 1.0),
                             on_text=lambda _s: None)
        self.assertEqual(res["status"], "blocked")
        self.assertEqual(res["protocol"], "native")
        d.cleanup()

    def test_envelope_co_truong_protocol(self):
        d, res, _ = self._run("anthropic", "sonnet-5.5", True)
        env = agent.envelope("x", res, Session(root=Path(d.name)), "s")
        self.assertEqual(env["protocol"], "native")
        self.assertEqual(env["usage"]["total"], 360)
        self.assertEqual(env["assistantTurns"], 2)
        d.cleanup()


if __name__ == "__main__":
    unittest.main(verbosity=2)
