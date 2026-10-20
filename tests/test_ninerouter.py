"""9router qua server giả. Không cần 9router thật, không ra mạng.

Bài sống chỉ chạy khi FROG_LIVE_9ROUTER=1 trên máy có 9router. CI bỏ qua và in lý do.
"""
from __future__ import annotations

import io
import json
import os
import socket
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from frog import cli, keys, team  # noqa: E402
from frog import config as C  # noqa: E402
from frog.providers import (REGISTRY, SUBSCRIPTION_NOTE, NineRouterProvider,  # noqa: E402
                            OpenAICompatProvider, ProviderError, agent_binding, billing_of,
                            flag_warning, missing_key_text, model_flags, probe_models,
                            provider_for)

KEY = "test-9r"
MODELS = ["cu/gpt-5.6-sol-high", "cu/claude-opus-5-thinking-high", "cu/claude-fable-5-high"]


class _Fake(BaseHTTPRequestHandler):
    mode = "json"
    seen: list = []

    def log_message(self, *a):
        pass

    def _send(self, code: int, body, kind: str = "application/json") -> None:
        raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("content-type", kind)
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == "/v1/models":
            self._send(200, {"object": "list", "data": [{"id": m} for m in MODELS]})
        else:
            self._send(404, {"error": {"message": "not found"}})

    def do_POST(self):
        n = int(self.headers.get("content-length", 0))
        req = json.loads(self.rfile.read(n) or b"{}")
        type(self).seen.append({"path": self.path, "req": req,
                                "auth": self.headers.get("authorization")})
        if self.headers.get("authorization") != f"Bearer {KEY}":
            self._send(401, {"error": {"message": "Invalid API key"}})
            return
        if req.get("model") not in MODELS:
            self._send(404, {"error": {"message": "No active credentials for provider: x",
                                       "code": "model_not_found"}})
            return
        mode = type(self).mode
        if mode == "sse_error":
            body = ('data: {"error":{"message":"Cursor AgentService returned an empty turn",'
                    '"type":"api_error"}}\n\ndata: [DONE]\n\n')
            self._send(200, body.encode(), "text/event-stream")
        elif mode == "sse":
            body = ('data: {"choices":[{"delta":{"content":"xin "}}]}\n\n'
                    'data: {"choices":[{"delta":{"content":"chào"}}]}\n\ndata: [DONE]\n\n')
            self._send(200, body.encode(), "text/event-stream")
        else:
            blob = json.dumps(req, ensure_ascii=False)
            text = ('{"verdict":"PASS","reasons":["khop"],"evidence":["x"],"confidence":0.9}'
                    if "VERIFIER" in blob else "KẾT QUẢ: trang giới thiệu đã soạn.")
            self._send(200, {"choices": [{"message": {"content": text}}],
                             "usage": {"prompt_tokens": 50, "completion_tokens": 9}})


def _closed_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _plan_three_roles():
    plan = team.build_plan("soạn báo cáo nội bộ", surface="read_only",
                           labels=["internal"], records=10, dollars=0)
    plan.lane = 2
    plan.roles = ["planner", "worker", "verifier"]
    return plan


class NineRouterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), _Fake)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def setUp(self):
        _Fake.mode = "json"
        _Fake.seen.clear()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        home = patch.object(keys, "KEYS_PATH", Path(tmp.name) / "keys.json")
        home.start()
        self.addCleanup(home.stop)
        env = {k: v for k, v in os.environ.items()
               if k not in ("NINE_ROUTER_API_KEY", "NINE_ROUTER_BASE_URL", "OPENROUTER_API_KEY")}
        env["NINE_ROUTER_API_KEY"] = KEY
        clean = patch.dict(os.environ, env, clear=True)
        clean.start()
        self.addCleanup(clean.stop)

    def test_dang_ky_va_khoa(self):
        cls = REGISTRY["9router"]
        self.assertIs(cls, NineRouterProvider)
        self.assertTrue(issubclass(cls, OpenAICompatProvider))
        self.assertEqual(cls.default_base, "http://localhost:20120")
        self.assertEqual(cls.env_key, "NINE_ROUTER_API_KEY")
        self.assertEqual(keys.ENV["9router"], "NINE_ROUTER_API_KEY")
        rows = {row[0]: row for row in keys.status_rows()}
        self.assertEqual(rows["9router"][2], "có")
        self.assertEqual(keys.resolve("9router"), (KEY, "env"))

    def test_cu_tu_di_9router_khong_sang_openrouter(self):
        self.assertEqual(provider_for("cu/gpt-5.6-sol-high", api_key="k").name, "9router")
        os.environ["OPENROUTER_API_KEY"] = "or-key"
        self.assertEqual(agent_binding("cu/gpt-5.6-sol-high", None),
                         ("cu/gpt-5.6-sol-high", "9router"))
        self.assertEqual(billing_of("cu/x"), "subscription")
        self.assertEqual(billing_of("x", "9router"), "subscription")
        self.assertEqual(billing_of("gpt-5.6-sol"), "metered")

    def test_goi_nguyen_id_va_bearer(self):
        prov = NineRouterProvider("cu/claude-opus-5-thinking-high", base_url=self.base)
        text, usage = prov.call("SYS", "USER")
        self.assertIn("KẾT QUẢ", text)
        self.assertEqual(usage, {"in": 50, "out": 9})
        last = _Fake.seen[-1]
        self.assertEqual(last["path"], "/v1/chat/completions")
        self.assertEqual(last["req"]["model"], "cu/claude-opus-5-thinking-high")
        self.assertEqual(last["auth"], f"Bearer {KEY}")
        self.assertIn("max_tokens", last["req"])

    def test_base_url_tu_bien_moi_truong(self):
        os.environ["NINE_ROUTER_BASE_URL"] = self.base
        self.assertEqual(NineRouterProvider("cu/x").base_url, self.base)

    def test_thieu_khoa_bao_ro_ten_bien(self):
        del os.environ["NINE_ROUTER_API_KEY"]
        prov = NineRouterProvider("cu/gpt-5.6-sol-high", base_url=self.base)
        self.assertFalse(prov.available())
        self.assertIn("NINE_ROUTER_API_KEY", missing_key_text(prov))
        plan = team.build_plan("tóm tắt tài liệu công khai", surface="read_only",
                               labels=["public"], records=10, dollars=0)
        res = team.execute_plan(plan, provider_name="9router",
                                model_override="cu/gpt-5.6-sol-high", base_url=self.base,
                                on_step=lambda m: None)
        self.assertEqual(res["status"], "blocked")
        self.assertIn("NINE_ROUTER_API_KEY", res["fail_reason"])
        self.assertEqual(_Fake.seen, [])
        from frog.handoff import _key_hint
        self.assertIn("NINE_ROUTER_API_KEY", _key_hint("cu/gpt-5.6-sol-high", "9router"))

    def test_sai_base_url_bao_cach_sua(self):
        prov = NineRouterProvider("cu/gpt-5.6-sol-high",
                                  base_url=f"http://127.0.0.1:{_closed_port()}")
        with self.assertRaises(ProviderError) as caught:
            prov.call("SYS", "USER")
        msg = str(caught.exception)
        self.assertIn("không kết nối được", msg)
        self.assertIn("NINE_ROUTER_BASE_URL", msg)
        self.assertIn("--base-url", msg)

    def test_khoa_sai_bao_ten_bien(self):
        os.environ["NINE_ROUTER_API_KEY"] = "sai"
        prov = NineRouterProvider("cu/gpt-5.6-sol-high", base_url=self.base)
        with self.assertRaises(ProviderError) as caught:
            prov.call("SYS", "USER")
        self.assertIn("HTTP 401", str(caught.exception))
        self.assertIn("NINE_ROUTER_API_KEY", str(caught.exception))

    def test_model_khong_co_thi_liet_ke_model_kha_dung(self):
        prov = NineRouterProvider("cu/khong-co-model", base_url=self.base)
        with self.assertRaises(ProviderError) as caught:
            prov.call("SYS", "USER")
        msg = str(caught.exception)
        self.assertIn("không có model cu/khong-co-model", msg)
        for model in MODELS:
            self.assertIn(model, msg)

    def test_luot_rong_sse_thanh_loi(self):
        _Fake.mode = "sse_error"
        prov = NineRouterProvider("cu/gpt-5.6-sol-high", base_url=self.base)
        with self.assertRaises(ProviderError) as caught:
            prov.call("SYS", "USER")
        self.assertIn("empty turn", str(caught.exception))
        from frog.stream import stream
        with self.assertRaises(ProviderError) as streamed:
            stream(prov, "SYS", "USER")
        self.assertIn("empty turn", str(streamed.exception))

    def test_so_ghi_uncertain_khong_bao_gio_0(self):
        logs: list[str] = []
        res = team.execute_plan(_plan_three_roles(), provider_name="9router",
                                model_override="cu/gpt-5.6-sol-high", base_url=self.base,
                                on_step=logs.append)
        led = res["ledger"]
        self.assertEqual(led["total_usd"], 0.0)
        self.assertEqual(led["by_role"], {})
        self.assertEqual(len(led["uncertain"]), 3)
        for item in led["uncertain"]:
            self.assertIsNone(item["usd"])
            self.assertEqual(item["reason"], SUBSCRIPTION_NOTE)
            self.assertEqual(item["billing"], "subscription")
        for req in led["requests"]:
            self.assertIsNone(req["usd"])
            self.assertEqual(req["state"], "uncertain")
        called = [s for s in res["steps"] if s.get("text")]
        self.assertTrue(called)
        self.assertTrue(all(s.get("usd") is None for s in called))
        line = team.cost_text(led)
        self.assertIn(SUBSCRIPTION_NOTE, line)
        self.assertNotIn("$", line)
        self.assertTrue(any(SUBSCRIPTION_NOTE in row for row in logs))
        self.assertFalse(any("$0" in row for row in logs))

    def test_tran_luot_goi_goi_thue_bao(self):
        with patch.object(C, "SUBSCRIPTION_CALL_CAP", 1):
            res = team.execute_plan(_plan_three_roles(), provider_name="9router",
                                    model_override="cu/gpt-5.6-sol-high", base_url=self.base,
                                    on_step=lambda m: None)
        self.assertEqual(res["status"], "stopped_budget")
        self.assertIn("gói thuê bao", res["fail_reason"])
        self.assertEqual(len(_Fake.seen), 1)

    def test_sse_khong_usage_khong_thanh_0_dong(self):
        _Fake.mode = "sse"
        led = team.Ledger()
        prov = OpenAICompatProvider("cu/gpt-5.6-sol-high", api_key=KEY, base_url=self.base)
        text, usage, usd, _rid = led.tracked_call(
            "worker", "cu/gpt-5.6-sol-high", prov, "S", "U", {"in": 1.0, "out": 1.0},
            source="cli", max_out=16)
        self.assertEqual(text, "xin chào")
        self.assertTrue(usage["unknown"])
        self.assertIsNone(usd)
        self.assertEqual(led.rows, [])
        self.assertEqual(led.uncertain[-1]["reason"], team.UNKNOWN_USAGE_NOTE)
        self.assertGreater(led.uncertain_usd, 0)

    def test_agent_khong_in_0_dong(self):
        from frog.agent import run_turn
        from frog.tools import Session
        with tempfile.TemporaryDirectory() as root:
            session = Session(root=Path(root), mode="plan", approve=lambda t, a: False)
            res = run_turn(task="chào", session=session, model="cu/gpt-5.6-sol-high",
                           provider_name="9router", base_url=self.base, protocol="text",
                           no_stream=True, max_turns=2)
        self.assertIsNone(res["costUsd"])
        self.assertEqual(res["billing"], "subscription")

    def test_nhan_no_zdr(self):
        self.assertEqual(model_flags("cu/claude-fable-5-high"), ["no_zdr"])
        self.assertEqual(model_flags("cu/gpt-5.6-sol-high"), [])
        self.assertIn("no_zdr", flag_warning("cu/claude-fable-5-1-max"))
        self.assertEqual(flag_warning("cu/gpt-5.6-sol-high"), "")

    def test_doctor_liet_ke_model(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            got = cli._doctor_9router(self.base)
        out = buf.getvalue()
        self.assertIsNone(got)
        self.assertIn("9router: 3 model", out)
        self.assertIn("no_zdr", out)
        self.assertEqual(_Fake.seen, [])

    def test_doctor_khong_co_9router_khong_hong(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            got = cli._doctor_9router(f"http://127.0.0.1:{_closed_port()}")
        out = buf.getvalue()
        self.assertIsNone(got)
        self.assertIn("không kết nối được", out)
        self.assertIn("NINE_ROUTER_BASE_URL", out)

    def test_smoke_mot_luot_va_canh_bao_no_zdr(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            got = cli._doctor_9router(self.base, smoke="cu/claude-fable-5-high")
        out = buf.getvalue()
        self.assertTrue(got)
        self.assertIn("no_zdr", out)
        self.assertIn(SUBSCRIPTION_NOTE, out)
        self.assertEqual(len(_Fake.seen), 1)

    def test_smoke_model_khong_co_khong_goi(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            got = cli._doctor_9router(self.base, smoke="cu/khong-co")
        self.assertFalse(got)
        self.assertIn("không có model cu/khong-co", buf.getvalue())
        self.assertEqual(_Fake.seen, [])


@unittest.skipUnless(os.environ.get("FROG_LIVE_9ROUTER") == "1",
                     "9router chỉ có trên máy chủ repo; đặt FROG_LIVE_9ROUTER=1 để kiểm "
                     "bằng cách liệt kê model (không tốn quota)")
class LiveNineRouterTest(unittest.TestCase):
    def test_liet_ke_model_that(self):
        base = os.environ.get("NINE_ROUTER_BASE_URL") or NineRouterProvider.default_base
        ids, why = probe_models(base, os.environ.get("NINE_ROUTER_API_KEY"))
        self.assertTrue(ids, why)


if __name__ == "__main__":
    unittest.main(verbosity=2)
