"""Kiểm hội đồng phản biện và danh sách ngắn gán nhãn.

Trọng tâm: hội đồng phải TÍNH RA được rằng mục tiêu cần gán không nằm trong cột
hiển thị — và tuyệt đối KHÔNG được tự nhận là sinh được nhãn thay người.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mira import panel                        # noqa: E402
from mira.labels import sheet_labelability, triage  # noqa: E402
from mira.tasks import build_tasks            # noqa: E402

TASKS = build_tasks()


class TestKhaNhan(unittest.TestCase):
    def test_muc_tieu_khong_suy_ra_duoc_tu_phieu(self):
        r = sheet_labelability(TASKS)
        self.assertFalse(r["determinable"], "phiếu hiện tại phải bị đánh dấu KHÔNG suy ra được")
        self.assertEqual(r["n_groups_non_determinable"], r["n_groups"])
        self.assertIn("TRẢ LỜI ĐƯỢC", r["verdict"])

    def test_moi_nhom_deu_co_hai_nhan(self):
        r = sheet_labelability(TASKS)
        for k, v in r["groups"].items():
            self.assertGreater(v["inj"], 0, f"{k} không có injection nào")
            self.assertLess(v["inj"], v["n"], f"{k} toàn injection — lại suy ra được")


class TestTriage(unittest.TestCase):
    def test_xep_hang_chi_dung_cot_hien_thi(self):
        rows = triage(TASKS)
        self.assertEqual(len(rows), len(TASKS))
        r1 = [r for r in rows if r["rank"] == 1]
        for r in r1:
            self.assertEqual(r["untrusted_marker"], "no")
            self.assertIn(r["tool_surface"], ("write_external", "egress_new"))

    def test_bo_sot_that_nam_trong_hang_1_hoac_3(self):
        """Mọi tác vụ bị bỏ sót thật phải có marker=no ⇒ chỉ ở hạng 1 hoặc 3."""
        by_id = {t.id: t for t in TASKS}
        for r in triage(TASKS):
            if by_id[r["task_id"]].truth["label_missed_injection"]:
                self.assertEqual(r["untrusted_marker"], "no")

    def test_tap_toi_thieu_nho_hon_nhieu_so_voi_toan_bo(self):
        rows = triage(TASKS)
        r1 = [r for r in rows if r["rank"] == 1]
        self.assertLess(len(r1), len(rows) // 3, "hạng 1 phải là thiểu số")


class TestHoiDong(unittest.TestCase):
    def test_offline_khong_goi_model(self):
        res = panel.debate("câu hỏi", tasks=TASKS, rounds=1)
        self.assertEqual(res["mode"], "offline")
        self.assertIn("findings", res)

    def test_phat_hien_critical_ve_vong_tron(self):
        res = panel.debate("x", tasks=TASKS, rounds=2)
        ids = {f["id"] for f in res["findings"]}
        self.assertIn("F1", ids)
        self.assertIn("F6", ids)
        f6 = next(f for f in res["findings"] if f["id"] == "F6")
        self.assertEqual(f6["severity"], "critical")

    def test_vong_2_sua_lai_f4(self):
        res = panel.debate("x", tasks=TASKS, rounds=2)
        f4 = next(f for f in res["findings"] if f["id"] == "F4")
        self.assertEqual(f4["status"], "revised", "phản biện phải sửa lại F4")
        self.assertIn("báo động thừa", f4["note"])

    def test_bao_cao_noi_ro_khong_sinh_nhan(self):
        md = panel.render_verdict(panel.debate("x", tasks=TASKS, rounds=2))
        self.assertIn("không", md.lower())
        self.assertIn("nội dung thật", md)

    def test_khong_co_key_thi_roi_ve_offline(self):
        res = panel.debate("x", tasks=TASKS, provider_name="anthropic", api_key="", rounds=1)
        self.assertEqual(res["mode"], "offline")


if __name__ == "__main__":
    unittest.main(verbosity=2)
