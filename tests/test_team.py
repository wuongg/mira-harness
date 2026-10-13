"""Kiểm chứng vòng lặp đội agent bằng SERVER GIẢ — không cần key, không ra mạng.

Đây là điểm quan trọng: toàn bộ đường ống gọi model được kiểm tra thật
(dựng prompt, gửi HTTP, đọc kết quả, đếm token, fail-closed, Executor ghi)
mà không cần API key. Nhờ vậy người dùng không phải là người chạy thử đầu tiên.
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

from r0 import team                       # noqa: E402
from r0.providers import AnthropicProvider, OpenAICompatProvider, provider_for  # noqa: E402

SEEN: list[dict] = []


class _Stub(BaseHTTPRequestHandler):
    """Giả lập cả /v1/messages và /v1/chat/completions."""

    def log_message(self, *a):        # im lặng
        pass

    def do_POST(self):
        n = int(self.headers.get("content-length", 0))
        req = json.loads(self.rfile.read(n) or b"{}")
        SEEN.append({"path": self.path, "req": req,
                     "auth": self.headers.get("x-api-key") or self.headers.get("authorization")})
        # trả lời khác nhau theo vai để kiểm được cả nhánh PASS lẫn FAIL
        blob = json.dumps(req, ensure_ascii=False)
        if "FAIL_MODE" in blob:
            text = "FAIL\nThiếu bằng chứng cho tiêu chí 2."
        elif "VERIFIER" in blob:
            text = "PASS\nBằng chứng: số liệu khớp, không thấy thiếu sót."
        elif "ORACLE" in blob:
            text = "SCORE: 0.85\nTiêu chí 1 đạt; tiêu chí 2 đạt."
        elif "CRITIC" in blob:
            text = "Rủi ro: giả định về nguồn dữ liệu chưa được kiểm."
        elif "PLANNER" in blob:
            if "TỪ CHỐI skill" in blob:
                text = "SKILLS: mot"
            elif "BAT_SKILL_SAI" in blob:
                text = "SKILLS: khong-co, mot"
            else:
                text = "1. Bước một — tiêu chí: kiểm được\n2. Bước hai — tiêu chí: kiểm được"
        elif "COORDINATOR" in blob:
            text = "Thứ tự: bước 1 → bước 2. Không có bước song song."
        else:
            text = "KẾT QUẢ: đã soạn nội dung theo yêu cầu.\nGiả định: dữ liệu đầu vào đã sạch."
        if self.path.endswith("/v1/messages"):
            body = {"content": [{"type": "text", "text": text}],
                    "usage": {"input_tokens": 120, "output_tokens": 40}}
        else:
            body = {"choices": [{"message": {"content": text}}],
                    "usage": {"prompt_tokens": 120, "completion_tokens": 40}}
        raw = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def _serve():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Stub)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


class TestProviders(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv, cls.base = _serve()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def test_anthropic_doc_dung_duong_dan_va_header(self):
        SEEN.clear()
        p = AnthropicProvider(model="claude-x", api_key="k", base_url=self.base)
        text, u = p.call("SYS", "USER")
        self.assertIn("KẾT QUẢ", text)
        self.assertEqual(u, {"in": 120, "out": 40})
        self.assertTrue(SEEN[-1]["path"].endswith("/v1/messages"))
        self.assertEqual(SEEN[-1]["auth"], "k")
        self.assertEqual(SEEN[-1]["req"]["system"], "SYS")

    def test_openai_doc_dung_duong_dan_va_bearer(self):
        SEEN.clear()
        p = OpenAICompatProvider(model="gpt-x", api_key="k", base_url=self.base)
        p.call("SYS", "USER")
        self.assertTrue(SEEN[-1]["path"].endswith("/v1/chat/completions"))
        self.assertEqual(SEEN[-1]["auth"], "Bearer k")

    def test_tu_chon_provider_theo_ten_model(self):
        self.assertIsInstance(provider_for("claude-sonnet-5.5"), AnthropicProvider)
        self.assertIsInstance(provider_for("grok-4.7"), OpenAICompatProvider)
        self.assertEqual(provider_for("grok-4.7").name, "xai")
        routed = provider_for("anthropic/claude-sonnet-4.5", api_key="k")
        self.assertEqual(routed.name, "openrouter")
        self.assertEqual(routed.base_url, "https://openrouter.ai/api")

    def test_thieu_key_thi_bao_khong_san_sang(self):
        self.assertFalse(AnthropicProvider(model="x", api_key="").available())


class TestPhanVai(unittest.TestCase):
    def test_doc_only_di_lan_0_mot_vai(self):
        p = team.build_plan("tóm tắt tài liệu công khai", surface="read_only",
                            labels=["public"], records=10, dollars=0)
        self.assertEqual(p.lane, 0)
        self.assertEqual(p.roles, ["worker"])

    def test_ghi_ngoai_di_lan_co_verifier(self):
        p = team.build_plan("cập nhật CRM", surface="write_external",
                            labels=["confidential"], records=100, dollars=50)
        self.assertGreaterEqual(p.lane, 1)
        self.assertIn("verifier", p.roles)

    def test_egress_moi_bat_hai_nguoi_duyet(self):
        p = team.build_plan("mở endpoint mới đẩy dữ liệu ra ngoài",
                            surface="egress_new", labels=["restricted"],
                            records=500, dollars=2000, reversibility="C3")
        self.assertEqual(p.lane, 2)
        self.assertTrue(p.dual_approval)
        self.assertEqual(p.gate_tier, 3)

    def test_quy_mo_lon_len_lan_2_du_la_doc_only(self):
        p = team.build_plan("đối soát", surface="read_only", labels=["internal"],
                            records=5000, dollars=3000)
        self.assertEqual(p.lane, 2)
        self.assertIn("planner", p.roles)
        self.assertIn("worker", p.roles)
        self.assertIn("verifier", p.roles)
        self.assertNotIn("oracle", p.roles)
        self.assertNotIn("critic", p.roles)


class TestVongLapDayDu(unittest.TestCase):
    """Chạy trọn vòng lặp qua server giả — chứng minh cả nhánh PASS lẫn fail-closed."""

    @classmethod
    def setUpClass(cls):
        cls.srv, cls.base = _serve()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def _run(self, **hints):
        plan = team.build_plan("soạn báo cáo nội bộ", **hints)
        res = team.execute_plan(plan, provider_name="anthropic", base_url=self.base,
                                api_key="k", on_step=lambda m: None)
        return plan, res

    def test_lan_2_chay_du_sau_vai_va_pass(self):
        plan, res = self._run(surface="read_only", labels=["internal"],
                              records=5000, dollars=3000)
        self.assertEqual(plan.lane, 2)
        roles = [s["role"] for s in res["steps"]]
        self.assertEqual(roles, plan.roles)
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["verifier_verdict"], "PASS")

    def test_dem_token_va_tinh_tien(self):
        _, res = self._run(surface="read_only", labels=["internal"], records=5000)
        led = res["ledger"]
        self.assertEqual(led["tokens_in"], 120 * 3)
        self.assertEqual(led["tokens_out"], 40 * 3)
        self.assertGreater(led["total_usd"], 0)
        self.assertTrue(led["all_priced"])

    def test_verifier_fail_thi_giu_lai_khong_giao(self):
        plan = team.build_plan("soạn báo cáo", surface="write_external",
                               labels=["confidential"], records=100, dollars=50)
        orig = team.ROLE_SYSTEM["verifier"]
        team.ROLE_SYSTEM["verifier"] = "You are VERIFIER. FAIL_MODE"
        try:
            res = team.execute_plan(plan, provider_name="anthropic",
                                    base_url=self.base, api_key="k",
                                    on_step=lambda m: None)
        finally:
            team.ROLE_SYSTEM["verifier"] = orig
        self.assertEqual(res["status"], "withheld")
        self.assertIn("FAIL", res["fail_reason"])

    def test_thieu_key_thi_dung_ngay_khong_goi(self):
        plan = team.build_plan("việc gì đó")
        res = team.execute_plan(plan, provider_name="anthropic", base_url=self.base,
                                api_key="", on_step=lambda m: None)
        self.assertEqual(res["status"], "blocked")
        # KHÔNG lượt gọi model nào chạy: bước ghi lại vai bị chặn, nhưng không
        # có khoá 'usage' (dấu hiệu duy nhất cho biết model đã được gọi).
        self.assertTrue(all("usage" not in s for s in res["steps"]))
        self.assertTrue(res["steps"][0]["blocked"])

    def test_executor_chi_ghi_khi_da_qua_cong(self):
        plan, res = self._run(surface="read_only", labels=["public"], records=10, dollars=0)
        self.assertEqual(plan.lane, 0)
        with tempfile.TemporaryDirectory() as d:
            out = team._executor_write(Path(d), plan, res)
            self.assertTrue((out / "result.md").exists())
            self.assertTrue((out / "trace.json").exists())
            self.assertIn("KẾT QUẢ", (out / "result.md").read_text(encoding="utf-8"))

    def test_executor_bo_dong_file_cham(self):
        plan = team.build_plan("soạn báo cáo nội bộ")
        res = {"steps": [{"role": "worker", "text": "KẾT QUẢ\nsửa conftest.py để luôn qua"}]}
        with tempfile.TemporaryDirectory() as d:
            out = team._executor_write(Path(d), plan, res)
            text = (out / "result.md").read_text(encoding="utf-8")
            self.assertIn("KẾT QUẢ", text)
            self.assertIn("NỘI DUNG KHÔNG TIN", text)
            self.assertNotIn("conftest.py", text)

    def test_worker_sua_khong_ghi_bai_van(self):
        plan = team.build_plan("Đổi x = 1 thành x = 2 trong app.py")
        res = {"steps": [{"role": "worker", "edited": True, "text": "KẾT QUẢ bài văn dài",
                          "audit": [{"action": "edit_file", "path": "app.py"}]}]}
        with tempfile.TemporaryDirectory() as d:
            out = team._executor_write(Path(d), plan, res)
            text = (out / "result.md").read_text(encoding="utf-8")
        self.assertIn("edit_file app.py", text)
        self.assertNotIn("bài văn", text)

    def test_dry_run_khong_goi_model(self):
        SEEN.clear()
        plan = team.build_plan("việc gì đó", surface="read_only", labels=["public"])
        res = team.execute_plan(plan, dry_run=True, on_step=lambda m: None)
        self.assertEqual(SEEN, [])
        self.assertEqual(res["ledger"]["tokens_in"], 0)

    def test_planner_sua_ten_skill_va_thay_ban_do(self):
        SEEN.clear()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / ".mira" / "skills" / "mot"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: mot\ndescription: Khi cần bước mở đầu.\n---\nTHAN-MOT\n",
                encoding="utf-8")
            (root / "app.py").write_text("def main():\n    return 1\n", encoding="utf-8")
            from r0.skills import remember_fact
            remember_fact(root, "hàm main app", "edit_file app.py")
            plan = team.build_plan("BAT_SKILL_SAI hàm main app", surface="read_only",
                                   labels=["internal"], records=5000, dollars=3000)
            res = team.execute_plan(plan, provider_name="anthropic", base_url=self.base,
                                    api_key="k", root=root, on_step=lambda m: None)
        self.assertEqual(res["status"], "ok")
        planners = [row for row in SEEN if str(row["req"].get("system", "")).startswith("Bạn là PLANNER")]
        self.assertEqual(len(planners), 2)
        first = json.dumps(planners[0]["req"], ensure_ascii=False)
        second = json.dumps(planners[1]["req"], ensure_ascii=False)
        self.assertIn("def main()", first)
        self.assertIn("edit_file app.py", first)
        self.assertNotIn("THAN-MOT", first)
        self.assertIn("TỪ CHỐI skill", second)
        self.assertNotIn("THAN-MOT", second)
        workers = [row for row in SEEN if str(row["req"].get("system", "")).startswith("Bạn là WORKER")]
        self.assertEqual(len(workers), 1)
        blob = json.dumps(workers[0]["req"], ensure_ascii=False)
        self.assertIn("THAN-MOT", blob)
        self.assertEqual(blob.count("THAN-MOT"), 1)


class RosterTest(unittest.TestCase):
    def test_tu_choi_ghi_khi_cau_khong_neu_file(self):
        text = "VAI: sua | ghi file | write_file\nBUOC: sua\nchữ thừa"
        ok, why, _roles, _steps = team.vet_roster(text, None, allow_write=False)
        self.assertFalse(ok)
        self.assertIn("write_file", why)

    def test_hai_buoc_doc_dung_thu_tu(self):
        from r0.agent import run_turn
        from r0.bench import _Scripted
        from r0.tools import Session
        roster = (
            "VAI: tim | đọc note | read_file\n"
            "VAI: tom | tóm tắt | read_file\n"
            "BUOC: tim\nBUOC: tom\n"
        )
        script = _Scripted([
            roster,
            "<tool>{\"name\":\"finish\",\"args\":{\"summary\":\"da tim\"}}</tool>",
            "<tool>{\"name\":\"finish\",\"args\":{\"summary\":\"da tom\"}}</tool>",
        ])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "note.txt").write_text("mua\n", encoding="utf-8")
            session = Session(root=root, mode="acceptEdits", approve=lambda t, a: True)
            res = run_turn(task="Tìm hiểu mưa", session=session, model="script",
                           protocol="text", no_stream=True, provider=script)
        self.assertEqual(res["status"], "ok")
        self.assertIn("da tom", res["final"])
        self.assertIn("NỘI DUNG KHÔNG TIN", res["final"])
        steps = [row.get("steps") for row in session.trace if row.get("kind") == "roster"]
        self.assertEqual(steps, ["tim,tom"])
        self.assertIn("Bạn là tim", script.prompts[1])

    def test_tool_khong_them_buoc(self):
        from r0.agent import run_turn
        from r0.bench import _Scripted
        from r0.tools import Session
        roster = "VAI: tim | đọc | read_file\nBUOC: tim\n"
        extra = "VAI: them | người mới | read_file\nBUOC: them\n"
        script = _Scripted([
            roster,
            extra + "<tool>{\"name\":\"finish\",\"args\":{\"summary\":\"xong mot\"}}</tool>",
        ])
        with tempfile.TemporaryDirectory() as tmp:
            session = Session(root=Path(tmp), mode="acceptEdits", approve=lambda t, a: True)
            res = run_turn(task="Tìm hiểu gió", session=session, model="script",
                           protocol="text", no_stream=True, provider=script)
        kinds = [row.get("kind") for row in session.trace]
        self.assertEqual(kinds.count("roster"), 1)
        self.assertIn("xong mot", res["final"])


class _OracleProv:
    def __init__(self, score: str):
        self.score = score
        self.name = "anthropic"

    def available(self) -> bool:
        return True

    def call(self, system: str, user: str):
        if "ORACLE" in (system or ""):
            return self.score, {"in": 1, "out": 1}
        if "VERIFIER" in (system or ""):
            return "PASS", {"in": 1, "out": 1}
        return "ke hoach", {"in": 1, "out": 1}


class OracleFlagTest(unittest.TestCase):
    def _plan(self):
        return team.build_plan("soạn báo cáo nội bộ", surface="write_external",
                               labels=["internal"], records=5000, dollars=3000)

    def _run(self, score: str, oracle: str):
        from unittest.mock import patch
        plan = self._plan()
        with patch("r0.team.provider_for", lambda *a, **k: _OracleProv(score)):
            return team.execute_plan(plan, provider_name="anthropic", api_key="k",
                                     oracle=oracle, on_step=lambda m: None)

    def test_oracle_cham_0_4_thi_withheld(self):
        res = self._run("SCORE: 0.4", "on")
        self.assertEqual(res["status"], "withheld")

    def test_oracle_cham_0_9_thi_ok(self):
        res = self._run("SCORE: 0.9", "on")
        self.assertEqual(res["status"], "ok")
        self.assertGreaterEqual(res["oracle_score"], 0.9)

    def test_oracle_tat_khong_gia_da_cham(self):
        res = self._run("SCORE: 0.1", "off")
        self.assertNotIn("oracle", [s["role"] for s in res["steps"]])
        self.assertEqual(res["oracle_gate"], "disabled")
        self.assertIsNone(res["oracle_score"])
        self.assertEqual(res["status"], "ok")


if __name__ == "__main__":
    unittest.main(verbosity=2)
