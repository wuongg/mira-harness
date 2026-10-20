"""Sơ đồ nhân sự theo đơn web. Provider giả, không ra mạng.

Mỗi luật có một bài phản chứng: vai mới thử ghi, vượt trần, bỏ cổng, dưới 4 vai.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import fake_9router  # noqa: E402
from frog import keys, team  # noqa: E402
from frog.intake import brief_hash, validate_brief  # noqa: E402
from frog.roles import (POOL, READ_ONLY, REQUIRED, infer_size, is_web_order,  # noqa: E402
                        run_order, settle, validate_settled)

ORDER_A = "Tôi cần một trang web giới thiệu frog để gửi cho bạn bè xem."
ORDER_B = "làm cho tôi 1 trang web của frog"
ORDER_C = "tôi muốn frog có trang chủ"
ORDER_BIG = "trang giới thiệu kèm form đăng ký nhận tin, lưu danh sách email"
LAZY = {"size": "nho", "web": True,
        "backend": {"needed": False, "reason": "trang tĩnh", "roles": []},
        "hired": [{"role": "product_manager", "task": "chốt phạm vi", "reason": "giữ phạm vi"},
                  {"role": "frontend_engineer", "task": "dựng trang", "reason": "cần người làm"},
                  {"role": "qa_reviewer", "task": "kiểm trang", "reason": "cần người kiểm"}],
        "considered": [{"role": "devops_engineer", "reason": "trang tĩnh, chưa cần hạ tầng"}]}
BRIEF = {"goal": "trang giới thiệu frog", "deliverables": [],
         "acceptance_criteria": [{"text": "Trang có tiêu đề frog", "outcome": "nhan_dinh"}],
         "constraints": [], "assumptions": [], "questions": [],
         "per_role_hints": {"planner": "", "worker": "", "verifier": ""}}


class RolePoolTest(unittest.TestCase):
    def test_du_19_vai_va_prompt_theo_nghe(self):
        self.assertEqual(len(POOL), 19)
        prompts = [spec.system_prompt for spec in POOL.values()]
        self.assertEqual(len(set(prompts)), 19)
        for spec in POOL.values():
            self.assertTrue(spec.system_prompt.startswith(f"Mã vai: {spec.name}\n"))
            self.assertNotIn("Bạn là WORKER", spec.system_prompt)
            self.assertEqual(spec.allowed_tools, READ_ONLY)
            self.assertGreater(spec.cap_usd, 0)
        self.assertIn("tiêu chí nghiệm thu", POOL["product_manager"].system_prompt)
        self.assertIn("checklist", POOL["qa_reviewer"].system_prompt.lower())
        security = POOL["security_reviewer"].system_prompt
        self.assertIn("form", security)
        self.assertIn("dữ liệu", security)
        for name in ("qa_reviewer", "security_reviewer", "a11y_reviewer", "content_reviewer"):
            self.assertIn("verdict", POOL[name].system_prompt)

    def test_ba_cach_dien_dat_cung_co_nho(self):
        for order in (ORDER_A, ORDER_B, ORDER_C):
            self.assertTrue(is_web_order(order), order)
            self.assertEqual(infer_size(order)[0], "nho", order)
        self.assertEqual(infer_size(ORDER_BIG)[0], "vua")
        self.assertEqual(infer_size("web bán hàng có đăng nhập")[0], "lon")
        self.assertFalse(is_web_order("tóm tắt tài liệu công khai"))

    def test_intake_tuyen_thieu_thi_code_bu_va_ghi_nguon(self):
        st = settle(ORDER_A, LAZY)
        names = [r["role"] for r in st["hired"]]
        for name in REQUIRED["nho"]:
            self.assertIn(name, names)
        origin = {r["role"]: r["origin"] for r in st["hired"]}
        self.assertEqual(origin["product_manager"], "intake")
        self.assertEqual(origin["ux_designer"], "luật cỡ đơn")
        skipped = {r["role"]: r for r in st["considered"]}
        self.assertEqual(skipped["devops_engineer"]["origin"], "intake")
        self.assertIn("security_reviewer", skipped)
        self.assertTrue(all(r["reason"] for r in st["considered"]))
        self.assertEqual(len(names) + len(skipped), len(POOL))
        self.assertFalse(st["backend"]["needed"])
        self.assertEqual(st["errors"], [])

    def test_don_lon_bat_buoc_backend_va_bao_mat(self):
        st = settle(ORDER_BIG, LAZY)
        self.assertEqual(st["size"]["intake"], "nho")
        self.assertEqual(st["size"]["final"], "vua")
        names = [r["role"] for r in st["hired"]]
        self.assertIn("backend_api_engineer", names)
        self.assertIn("security_reviewer", names)
        self.assertTrue(st["backend"]["needed"])
        self.assertIn("backend_api_engineer", st["backend"]["roles"])
        self.assertTrue(any("nâng cỡ đơn" in note for note in st["notes"]))
        refused = settle(ORDER_BIG, LAZY, drop=["security_reviewer"])
        self.assertTrue(any("không bỏ được security_reviewer" in e for e in refused["errors"]))
        auth = settle("web bán hàng có đăng nhập", LAZY)
        self.assertIn("auth_engineer", [r["role"] for r in auth["hired"]])

    def test_fallback_ghi_ro_va_don_web_bi_chan(self):
        st = settle(ORDER_A, None)
        self.assertTrue(st["fallback"])
        self.assertEqual([r["role"] for r in st["hired"]], ["planner", "worker", "verifier"])
        self.assertTrue(any("fallback" in note for note in st["notes"]))
        self.assertTrue(any("ít nhất 4 vai" in e for e in st["errors"]))
        broken = settle(ORDER_A, {"size": "nho", "hired": "frontend_engineer"})
        self.assertTrue(broken["fallback"])
        hired = settle(ORDER_A, None, hire=["content_writer"])
        self.assertFalse(hired["fallback"])
        self.assertEqual(hired["errors"], [])
        plain = settle("tóm tắt tài liệu công khai", None)
        self.assertTrue(plain["fallback"])
        self.assertEqual(plain["errors"], [])

    def test_duoi_4_vai_va_thieu_vai_kiem_bi_chan(self):
        st = settle(ORDER_A, LAZY)
        st["hired"] = st["hired"][:3]
        self.assertTrue(any("ít nhất 4 vai" in e for e in validate_settled(st)))
        no_review = settle(ORDER_A, LAZY)
        no_review["hired"] = [r for r in no_review["hired"] if r["kind"] != "review"]
        self.assertTrue(any("vai kiểm" in e for e in validate_settled(no_review)))

    def test_intake_khong_cap_duoc_quyen_ghi(self):
        evil = json.loads(json.dumps(LAZY))
        evil["hired"][2]["allowed_tools"] = ["write_file"]
        st = settle(ORDER_A, evil)
        row = next(r for r in st["hired"] if r["role"] == "qa_reviewer")
        self.assertEqual(row["tools"], list(READ_ONLY))
        self.assertTrue(any("bỏ quyền write_file" in note for note in st["notes"]))
        st["hired"][0]["tools"] = ["write_file"]
        self.assertTrue(any("quyền ghi" in e for e in validate_settled(st)))

    def test_vai_ngoai_danh_muc(self):
        proposal = json.loads(json.dumps(LAZY))
        proposal["hired"].append({"role": "photographer", "kind": "make",
                                  "task": "chụp ảnh sản phẩm", "reason": "trang cần ảnh thật"})
        proposal["hired"].append({"role": "Bad Name!", "kind": "make", "task": "x"})
        st = settle(ORDER_A, proposal)
        self.assertIn("photographer", [r["role"] for r in st["hired"]])
        self.assertIn("Bad Name!", [r["role"] for r in st["considered"]])
        self.assertEqual(validate_settled(st), [])
        self.assertIn("photographer", run_order(st))

    def test_brief_khoa_so_do_vao_hash(self):
        brief = json.loads(json.dumps(BRIEF))
        brief["acceptance_criteria"] = ["Trang có tiêu đề frog"]
        self.assertEqual(validate_brief(brief), (True, ""))
        brief["staffing"] = settle(ORDER_A, LAZY)
        self.assertEqual(validate_brief(brief), (True, ""))
        changed = dict(brief, staffing=settle(ORDER_A, LAZY, hire=["content_writer"]))
        self.assertNotEqual(brief_hash(brief), brief_hash(changed))
        skip_gate = dict(brief, staffing=dict(brief["staffing"], skip_gate=True))
        ok, why = validate_brief(skip_gate)
        self.assertFalse(ok)
        self.assertIn("khóa lạ", why)
        self.assertFalse(validate_brief(dict(brief, roles=["worker"]))[0])


class StaffedRunTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = fake_9router.serve(0)
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def setUp(self):
        fake_9router.CALLS.clear()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        home = patch.object(keys, "KEYS_PATH", Path(tmp.name) / "keys.json")
        home.start()
        self.addCleanup(home.stop)
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("FAKE_", "NINE_ROUTER_"))}
        env["NINE_ROUTER_API_KEY"] = "fake"
        clean = patch.dict(os.environ, env, clear=True)
        clean.start()
        self.addCleanup(clean.stop)

    def _plan(self, order=ORDER_A, proposal=LAZY):
        plan = team.build_plan(order, surface="read_only", labels=["internal"],
                               records=10, dollars=0)
        st = settle(order, proposal)
        plan.staffing = st
        plan.roles = run_order(st)
        plan.brief = json.loads(json.dumps(BRIEF))
        return plan, st

    def _run(self, plan, **kw):
        kw.setdefault("provider_name", "9router")
        kw.setdefault("role_models", team.slot_models("9router"))
        return team.execute_plan(plan, base_url=self.base, on_step=lambda m: None, **kw)

    def test_moi_vai_mot_luot_dung_thu_tu_va_khac_ho_model(self):
        plan, st = self._plan()
        res = self._run(plan)
        self.assertEqual([s["role"] for s in res["steps"]], run_order(st))
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["verifier_verdict"], "PASS")
        models = {s["role"]: s["model"] for s in res["steps"]}
        self.assertEqual(models["qa_reviewer"], "cu/claude-opus-5-thinking-high")
        self.assertEqual(models["frontend_engineer"], "cu/gpt-5.6-sol-high")
        called = [c["role"] for c in fake_9router.CALLS]
        self.assertEqual(sorted(called), sorted(run_order(st)))

    def test_vai_kiem_fail_thi_khong_ban_giao(self):
        plan, _st = self._plan()
        os.environ["FAKE_FAIL"] = "qa_reviewer"
        res = self._run(plan)
        self.assertEqual(res["status"], "withheld")
        self.assertNotIn("handoff_editor", [s["role"] for s in res["steps"]])

    def test_vai_kiem_doi_ghi_file_khong_ghi_duoc(self):
        plan, _st = self._plan()
        os.environ["FAKE_EVIL"] = "qa_reviewer"
        with tempfile.TemporaryDirectory() as tmp:
            res = self._run(plan, root=Path(tmp))
            self.assertFalse((Path(tmp) / "pwned.txt").exists())
            self.assertFalse(any(p.name == "pwned.txt" for p in Path(tmp).rglob("*")))
        self.assertEqual(res["status"], "withheld")

    def test_vuot_tran_vai_bi_chan_truoc_khi_goi(self):
        plan, _st = self._plan()
        plan.declared_price = (1000.0, 1000.0)
        res = self._run(plan, provider_name="openai", model_override="cu/gpt-5.6-sol-high",
                        api_key="k", max_tokens=64, role_models=None)
        self.assertEqual(res["status"], "stopped_budget")
        self.assertIn("trần vai", res["fail_reason"])
        self.assertEqual(fake_9router.CALLS, [])

    def test_dry_run_liet_ke_dung_vai(self):
        plan, st = self._plan()
        res = team.execute_plan(plan, dry_run=True, role_models=team.slot_models("9router"),
                                on_step=lambda m: None)
        self.assertEqual([s["role"] for s in res["steps"]], run_order(st))
        self.assertEqual(fake_9router.CALLS, [])


class TeamCliTest(unittest.TestCase):
    """Đi qua frog team thật bằng tiến trình con. Khóa giả, 9router giả."""

    @classmethod
    def setUpClass(cls):
        cls.srv = fake_9router.serve(0)
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def _team(self, root: Path, answers: str, *extra: str, staff: str = "lazy",
              provider: bool = True):
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("FAKE_", "NINE_ROUTER_"))
               and k not in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY")}
        env.update(PYTHONPATH=str(ROOT), PYTHONIOENCODING="utf-8", HOME=str(root),
                   USERPROFILE=str(root), NINE_ROUTER_API_KEY="fake",
                   NINE_ROUTER_BASE_URL=self.base)
        os.environ["FAKE_STAFF"] = staff
        flags = ["--provider", "9router"] if provider else []
        try:
            return subprocess.run(
                [sys.executable, "-m", "frog", "team", *flags, *extra, ORDER_A],
                cwd=root, env=env, input=answers.encode("utf-8"), stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, timeout=120)
        finally:
            os.environ.pop("FAKE_STAFF", None)

    def test_duyet_brief_la_duyet_so_do_roi_ban_giao(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proc = self._team(root, "y\ny\n", "--out", "out")
            text = proc.stdout.decode("utf-8", "replace")
            self.assertEqual(proc.returncode, 0, text + proc.stderr.decode("utf-8", "replace"))
            self.assertIn("SƠ ĐỒ NHÂN SỰ", text)
            self.assertIn("Đã cân nhắc, không tuyển", text)
            self.assertIn("Duyệt brief và sơ đồ nhân sự này?", text)
            result = next((root / "out").rglob("result.md"))
            body = result.read_text(encoding="utf-8")
            for role in ("product_manager", "frontend_engineer", "qa_reviewer", "handoff_editor"):
                self.assertIn(role, body)

    def test_chi_co_khoa_9router_thi_khong_doi_khoa_hang(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = self._team(Path(tmp), "y\nn\n", provider=False)
            text = proc.stdout.decode("utf-8", "replace")
            self.assertNotIn("ANTHROPIC_API_KEY", text)
            self.assertIn("đội đi 9router", text)
            self.assertIn("SƠ ĐỒ NHÂN SỰ", text)
            self.assertEqual(proc.returncode, 4, text)

    def test_so_do_doi_bo_cong_van_phai_qua_cong(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proc = self._team(root, "y\nn\n", "--out", "out", staff="gate")
            text = proc.stdout.decode("utf-8", "replace")
            self.assertEqual(proc.returncode, 4, text)
            self.assertIn("bỏ quyền write_file", text)
            self.assertFalse((root / "out").exists() and any((root / "out").rglob("result.md")))

    def test_intake_khong_tra_so_do_thi_fallback_va_chan(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = self._team(Path(tmp), "y\ny\n", staff="none")
            text = proc.stdout.decode("utf-8", "replace")
            self.assertEqual(proc.returncode, 8, text)
            self.assertIn("fallback", text)
            self.assertIn("ít nhất 4 vai", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
