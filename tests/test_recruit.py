"""Phân tích đơn → đề cử → phỏng vấn → settle."""
from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from frog.recruit import interview_roster  # noqa: E402
from frog.roles import (CANDIDATE_MAX, infer_domain, settle, validate_settled)  # noqa: E402

ORDER = "trang web giới thiệu frog cần SEO và bản dịch Anh"
ORDER_LEGAL = "soạn hộ hợp đồng NDA tiếng Việt cho đối tác"


class InterviewTest(unittest.TestCase):
    def test_chi_pass_moi_vao_de_xuat(self):
        proposal = {
            "size": "nho", "web": True, "analysis": "cần SEO và dịch",
            "backend": {"needed": False, "reason": "tĩnh", "roles": []},
            "hired": [
                {"role": "product_manager", "task": "phạm vi", "reason": "pm"},
                {"role": "seo_copywriter", "kind": "make", "title": "SEO",
                 "task": "meta SEO", "reason": "cần SEO"},
                {"role": "translator", "kind": "make", "title": "Biên dịch",
                 "task": "dịch Anh", "reason": "cần bản Anh"},
                {"role": "frontend_engineer", "task": "html", "reason": "fe"},
                {"role": "qa_reviewer", "task": "kiểm", "reason": "qa"},
            ],
            "considered": [],
        }

        def ask(_system, user):
            if "seo_copywriter" in user:
                return json.dumps({"verdict": "FAIL", "reasons": ["thừa"], "confidence": 0.8})
            return json.dumps({"verdict": "PASS", "reasons": ["khớp"], "confidence": 0.9})

        filtered, rejected, _notes = interview_roster(ORDER, proposal, ask=ask)
        names = [r["role"] for r in filtered["hired"]]
        self.assertNotIn("seo_copywriter", names)
        self.assertIn("translator", names)
        self.assertTrue(any(r["role"] == "seo_copywriter" for r in rejected))
        st = settle(ORDER, filtered)
        self.assertNotIn("seo_copywriter", [r["role"] for r in st["hired"]])
        self.assertIn("translator", [r["role"] for r in st["hired"]])
        self.assertTrue(any(r.get("origin") == "phỏng vấn" for r in st["considered"]))
        self.assertEqual(validate_settled(st), [])

    def test_tran_chong_bung_no_khong_phai_bon_nghe(self):
        extras = [{"role": f"craft_{i}", "kind": "make", "title": f"C{i}",
                   "task": f"việc {i}", "reason": "cần"} for i in range(CANDIDATE_MAX + 5)]
        proposal = {"hired": extras, "considered": []}
        filtered, _rej, notes = interview_roster(
            ORDER, proposal, ask=lambda s, u: json.dumps(
                {"verdict": "PASS", "reasons": ["ok"], "confidence": 1}),
            skip=False)
        self.assertEqual(len(filtered["hired"]), CANDIDATE_MAX)
        self.assertTrue(any("chống bùng nổ" in n for n in notes))

    def test_bo_phong_van_khi_env(self):
        proposal = {"hired": [
            {"role": "seo_copywriter", "kind": "make", "title": "SEO",
             "task": "meta", "reason": "x"}], "considered": []}
        with patch.dict(os.environ, {"FROG_NO_INTERVIEW": "1"}):
            filtered, rejected, _ = interview_roster(
                ORDER, proposal, ask=lambda s, u: (_ for _ in ()).throw(RuntimeError("không gọi")))
        self.assertEqual(len(filtered["hired"]), 1)
        self.assertEqual(rejected, [])


class MultiDomainTest(unittest.TestCase):
    def test_suy_nganh_khong_mac_dinh_web(self):
        self.assertEqual(infer_domain(ORDER_LEGAL)[0], "legal")
        self.assertEqual(infer_domain("phân tích khảo sát khách hàng")[0], "research")
        self.assertEqual(infer_domain(ORDER)[0], "web")

    def test_don_phap_ly_khong_bat_frontend(self):
        proposal = {
            "domain": "legal", "size": "nho", "web": False,
            "hired": [
                {"role": "contract_lawyer", "kind": "make", "title": "luật sư hợp đồng",
                 "task": "soạn NDA", "reason": "đơn pháp lý"},
                {"role": "legal_reviewer", "kind": "review", "title": "kiểm pháp lý",
                 "task": "đối chiếu điều khoản", "reason": "cần kiểm"},
            ],
            "considered": [],
            "backend": {"needed": False, "reason": "không phải web", "roles": []},
        }
        st = settle(ORDER_LEGAL, proposal)
        names = [r["role"] for r in st["hired"]]
        self.assertEqual(st["domain"], "legal")
        self.assertFalse(st["web"])
        self.assertNotIn("frontend_engineer", names)
        self.assertIn("contract_lawyer", names)
        self.assertTrue(any(r.get("kind") == "review" for r in st["hired"]))
        self.assertEqual(validate_settled(st), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
