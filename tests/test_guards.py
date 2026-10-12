"""Kiểm hai van an toàn (trần lượt / trần ngân sách) và worker làn 2 chạy song song.

Van ngân sách phải đếm bằng CODE từ token đã tiêu — không hỏi model (I8).
Song song chỉ đổi thời gian; mọi cổng và fail-closed vẫn nguyên (I1/I2/I5).
"""
from __future__ import annotations

import json
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from r0 import agent, team                       # noqa: E402
from r0.team import ROLES_BY_LANE, TeamPlan, execute_plan, expand_roles, make_task  # noqa: E402
from r0.tools import Session                      # noqa: E402


# ------------------------------------------------------------ server giả
class _Stub(BaseHTTPRequestHandler):
    """Luôn trả một tool_use -> vòng lặp KHÔNG tự kết thúc, để đo van."""

    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("content-length", 0))
        self.rfile.read(n)
        data = {"content": [{"type": "tool_use", "id": "c1", "name": "list_dir", "input": {}}],
                "usage": {"input_tokens": 150, "output_tokens": 30}}
        raw = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def _serve():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Stub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


class TestVanLuotVaNganSach(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv, cls.base = _serve()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def _session(self):
        d = Path(__file__).resolve().parents[1] / "out"
        d.mkdir(parents=True, exist_ok=True)
        return Session(root=d, mode="default", approve=lambda t, a: True)

    def _run(self, **kw):
        return agent.run_turn(task="x", session=self._session(), model="sonnet-5.5",
                              provider_name="anthropic", base_url=self.base, api_key="k",
                              protocol="native", no_stream=True,
                              on_text=lambda _t: None, **kw)

    def test_tran_luot_dung_so(self):
        res = self._run(max_turns=2)
        self.assertEqual(res["turns"], 2)
        self.assertEqual(res["status"], "stopped_turns")
        self.assertIn("2 vòng", res["stopReason"])
        self.assertEqual(res["toolSummary"]["calls"], 2)

    def test_tran_luot_1(self):
        res = self._run(max_turns=1)
        self.assertEqual(res["turns"], 1)
        self.assertEqual(res["status"], "stopped_turns")

    def test_tran_ngan_sach_dung_som(self):
        # mỗi lượt: 150*2 + 30*10 = 600e-6 USD -> lượt 2 vượt 0,001
        res = self._run(max_budget_usd=0.001)
        self.assertEqual(res["status"], "stopped_budget")
        self.assertEqual(res["turns"], 2)
        self.assertGreaterEqual(res["costUsd"], 0.001)
        self.assertIn("trần", res["stopReason"])

    def test_ngan_sach_rong_thi_khong_dung(self):
        res = self._run(max_budget_usd=999.0, max_turns=3)
        self.assertEqual(res["status"], "stopped_turns", "không vượt tiền -> chỉ chạm trần lượt")
        self.assertEqual(res["turns"], 3)

    def test_envelope_co_stop_reason(self):
        res = self._run(max_turns=2)
        env = agent.envelope("x", res, self._session(), "s")
        self.assertEqual(env["status"], "stopped_turns")
        self.assertFalse(env["ok"])
        self.assertIn("stopReason", env)
        self.assertIsNotNone(env["stopReason"])

    def test_van_khong_lam_ho_hong_luong_binh_thuong(self):
        res = self._run(max_turns=25, max_budget_usd=None)
        self.assertEqual(res["status"], "stopped_turns")   # stub không bao giờ finish
        self.assertEqual(res["turns"], 25)


# ------------------------------------------------- đội làn 2 chạy song song
class FakeProvider:
    """Nhà cung cấp giả: đếm số lần gọi ĐỒNG THỜI để chứng minh song song."""

    name = "fake"
    lock = threading.Lock()
    active = 0
    peak = 0
    delay = 0.0
    fail_verifier = False
    fail_first_verifier = False      # chỉ verifier ĐẦU TIÊN fail (để thử lan truyền)
    verifier_calls = 0

    def __init__(self, model, **_kw):
        self.model = model

    def available(self):
        return True

    def call(self, system, user):
        cls = type(self)
        with cls.lock:
            cls.active += 1
            cls.peak = max(cls.peak, cls.active)
        try:
            if cls.delay:
                time.sleep(cls.delay)
            if "PLANNER" in system:
                return "1. bước A\n2. bước B", {"in": 10, "out": 5}
            if "COORDINATOR" in system:
                return "bảng phân công", {"in": 10, "out": 5}
            if "WORKER" in system:
                return "kết quả công việc", {"in": 10, "out": 5}
            if "VERIFIER" in system:
                with cls.lock:
                    cls.verifier_calls += 1
                    first = cls.verifier_calls == 1
                fail = cls.fail_verifier or (cls.fail_first_verifier and first)
                return ("FAIL\nthiếu bằng chứng" if fail else "PASS\nổn"), {"in": 10, "out": 5}
            if "ORACLE" in system:
                return "SCORE: 0.9\nđạt", {"in": 10, "out": 5}
            if "CRITIC" in system:
                return "rủi ro: giả định chưa kiểm", {"in": 10, "out": 5}
            return "x", {"in": 1, "out": 1}
        finally:
            with cls.lock:
                cls.active -= 1


def _plan(lane=2, cap=0.0):
    return TeamPlan(task_text="làm việc X", lane=lane, floor=2, floor_reason="thử",
                    capability="write_external", gate_tier=3, gate_minutes=25.0,
                    dual_approval=True, roles=ROLES_BY_LANE[lane], roles_reason="thử",
                    task=make_task("làm việc X", surface="write_external"), cap_usd=cap)


class TestSongSongLan2(unittest.TestCase):
    def setUp(self):
        FakeProvider.active = FakeProvider.peak = 0
        FakeProvider.delay = 0.0
        FakeProvider.fail_verifier = False
        self._p = patch.object(team, "provider_for",
                               lambda model, name=None, **kw: FakeProvider(model))
        self._p.start()

    def tearDown(self):
        self._p.stop()

    def _run(self, plan, workers):
        return execute_plan(plan, workers=workers, on_step=lambda _m: None)

    def test_workers_3_chay_dong_thoi(self):
        FakeProvider.delay = 0.06
        res = self._run(_plan(), 3)
        self.assertEqual(res["status"], "ok")
        self.assertGreaterEqual(FakeProvider.peak, 3,
                                "3 worker phải chạy đồng thời, không tuần tự")

    def test_workers_1_khong_song_song(self):
        FakeProvider.delay = 0.02
        res = self._run(_plan(), 1)
        self.assertEqual(res["status"], "ok")
        self.assertEqual(FakeProvider.peak, 1, "workers=1 thì không có gì chạy song song")

    def test_so_buoc_bang_so_worker(self):
        res = self._run(_plan(), 4)
        roles = [s["role"] for s in res["steps"]]
        self.assertEqual(roles.count("worker"), 4)
        self.assertEqual(roles.count("verifier"), 4)

    def test_thu_tu_buoc_tat_dinh(self):
        res = self._run(_plan(), 3)
        roles = [s["role"] for s in res["steps"]]
        self.assertEqual(roles, ["planner", "coordinator",
                                 "worker", "worker", "worker",
                                 "verifier", "verifier", "verifier",
                                 "oracle", "critic"])

    def test_fail_closed_khi_mot_verifier_fail(self):
        FakeProvider.fail_verifier = True
        res = self._run(_plan(), 3)
        self.assertEqual(res["status"], "withheld")
        self.assertEqual(res["verifier_verdict"], "FAIL")

    def test_tat_ca_pass_thi_ok(self):
        res = self._run(_plan(), 3)
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["verifier_verdict"], "PASS")
        self.assertAlmostEqual(res["oracle_score"], 0.9, places=3)

    def test_tran_ngan_sach_cua_lan(self):
        res = self._run(_plan(cap=1e-9), 3)
        self.assertEqual(res["status"], "stopped_budget")

    def test_lan_0_van_chay_khi_khong_song_song(self):
        res = self._run(_plan(lane=0), 3)
        self.assertEqual(res["status"], "ok")
        self.assertEqual([s["role"] for s in res["steps"]], ["worker"])

    def test_expand_roles_chi_no_lan_2(self):
        self.assertEqual(expand_roles(ROLES_BY_LANE[1], 1, 3), ["worker", "verifier"])
        self.assertEqual(len(expand_roles(ROLES_BY_LANE[2], 2, 3)), 10)

    def test_dry_run_phong_to_vai(self):
        plan = _plan()
        res = execute_plan(plan, workers=3, dry_run=True, on_step=lambda _m: None)
        roles = [s["role"] for s in res["steps"]]
        self.assertEqual(roles.count("worker"), 3)
        self.assertEqual(roles.count("verifier"), 3)

    def test_dry_run_khong_goi_model(self):
        FakeProvider.peak = 0
        plan = _plan()
        res = execute_plan(plan, workers=3, dry_run=True, on_step=lambda _m: None)
        self.assertEqual(FakeProvider.peak, 0, "dry-run KHÔNG được gọi model")
        self.assertEqual([s["role"] for s in res["steps"]].count("worker"), 3)


class TestDoiCon(unittest.TestCase):
    """Subagent lồng nhau: chia trần cha, sổ cái chung, fail-closed lan truyền."""

    def setUp(self):
        FakeProvider.active = FakeProvider.peak = 0
        FakeProvider.delay = 0.0
        FakeProvider.fail_verifier = False
        FakeProvider.fail_first_verifier = False
        FakeProvider.verifier_calls = 0
        self._p = patch.object(team, "provider_for",
                               lambda model, name=None, **kw: FakeProvider(model))
        self._p.start()

    def tearDown(self):
        self._p.stop()

    def _logs(self, plan, **kw):
        msgs = []
        res = execute_plan(plan, on_step=msgs.append, **kw)
        return res, "\n".join(msgs)

    def test_depth_0_khong_mo_doi_con(self):
        res, _ = self._logs(_plan(cap=100.0), workers=1, depth=0)
        self.assertFalse(res["nested"])
        self.assertEqual(res["ledger"]["subagent_runs"], 0)

    def test_depth_1_mo_mot_doi_con_lan_1(self):
        res, _ = self._logs(_plan(cap=100.0), workers=1, depth=1)
        self.assertTrue(res["nested"])
        self.assertEqual(res["ledger"]["subagent_runs"], 1)
        worker = next(s for s in res["steps"] if s["role"] == "worker")
        self.assertEqual(worker["sub"]["lane"], 1)

    def test_doi_con_chia_nua_tran_con_lai(self):
        _res, logs = self._logs(_plan(cap=1.0), workers=1, depth=1)
        self.assertIn("trần $0.49", logs, "đội con phải nhận ~50% trần còn lại")

    def test_depth_2_long_hai_cap(self):
        res, _ = self._logs(_plan(cap=100.0), workers=1, depth=2)
        self.assertEqual(res["ledger"]["subagent_runs"], 2)

    def test_lan_1_khong_mo_doi_con(self):
        res, _ = self._logs(_plan(lane=1, cap=100.0), workers=1, depth=2)
        self.assertEqual(res["ledger"]["subagent_runs"], 0)
        self.assertFalse(res["nested"])

    def test_doi_con_fail_thi_ca_luot_bi_giu_lai(self):
        """Verifier CHA vẫn PASS, nhưng verifier CON fail -> cả lượt bị giữ lại."""
        FakeProvider.fail_first_verifier = True     # verifier con chạy trước
        res, _ = self._logs(_plan(cap=100.0), workers=1, depth=1)
        self.assertTrue(any(s.get("degraded") for s in res["steps"]))
        self.assertEqual(res["status"], "withheld")
        self.assertIn("đội con", res["fail_reason"])

    def test_so_cai_dung_chung_va_bi_chan_tran(self):
        res, _ = self._logs(_plan(cap=100.0), workers=2, depth=2)
        self.assertGreaterEqual(res["ledger"]["subagent_runs"], 1)
        self.assertLessEqual(res["ledger"]["subagent_runs"], team.SUBAGENT_MAX_RUNS)

    def test_cham_tran_doi_con_thi_khong_mo(self):
        with patch.object(team, "SUBAGENT_MAX_RUNS", 0):
            res, _ = self._logs(_plan(cap=100.0), workers=1, depth=1)
        self.assertEqual(res["status"], "blocked")
        self.assertIn("đội con", res["fail_reason"])

    def test_het_tien_thi_khong_mo_doi_con(self):
        # trần 0,0001 USD: pha đầu (planner) đã vượt trước khi tới worker
        res, _ = self._logs(_plan(cap=0.0001), workers=1, depth=1)
        self.assertEqual(res["status"], "stopped_budget")
        self.assertEqual(res["ledger"]["subagent_runs"], 0, "hết tiền thì không mở đội con")

    def test_chi_phi_cay_khong_vuot_xa_tran(self):
        res, _ = self._logs(_plan(cap=0.05), workers=2, depth=2)
        self.assertLessEqual(res["ledger"]["total_usd"], 0.05 + 0.01)


if __name__ == "__main__":
    unittest.main(verbosity=2)
