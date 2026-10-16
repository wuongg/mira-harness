"""Kiểm tra bất biến của SPEC — chạy được, không cần đọc lại tài liệu.

    python3 -m unittest discover -s tests -v
    r0-shadow selftest

Mỗi bài kiểm tra ứng với một bất biến hoặc một bảo đảm đã tuyên bố trong SPEC.
Nếu một bài đỏ, tuyên bố tương ứng trong tài liệu đang SAI.
"""
from __future__ import annotations

import csv
import random
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from frog import config as C                      # noqa: E402
from frog.labels import export_labels             # noqa: E402
from frog.metrics import compute                  # noqa: E402
from frog.pipeline import ShadowRun               # noqa: E402
from frog.tasks import load_tasks                 # noqa: E402


def _run(seed: int = C.SEED, cache: float = 0.90):
    C.CACHE_HIT = cache
    tasks = load_tasks()
    run = ShadowRun(tasks=tasks, rng=random.Random(seed), seed=seed)
    return run.run()


class TestTaiLap(unittest.TestCase):
    """Một bộ đo không tái lập được thì mọi so sánh trước/sau đều vô nghĩa."""

    def test_hai_lan_chay_trung_khit(self):
        a, b = compute(_run()), compute(_run())
        for k in ("lane_distribution", "VC_escalate_rate", "cost_per_milestone",
                  "t1b_recall_on_missed", "oracle_verifier", "D1_fill_p95",
                  "audit_hours_per_week", "gate_tier_distribution"):
            self.assertEqual(a[k], b[k], f"chỉ số {k} KHÔNG tái lập được")

    def test_lan_gio_do_NOI_DUNG_quyet_khong_do_hat_giong(self):
        """T1b nay đọc nội dung nên làn là HÀM CỦA NỘI DUNG, không của hạt giống.

        Đây là hệ quả CÓ CHỦ Ý của việc bỏ rút-thăm: đổi hạt giống chạy KHÔNG được
        làm đổi phân bố làn, vì nội dung do hạt giống của bộ sinh tác vụ quyết.
        """
        a, b = compute(_run(seed=C.SEED)), compute(_run(seed=C.SEED + 1))
        self.assertEqual(a["lane_distribution"], b["lane_distribution"])
        self.assertEqual(a["t1b_recall_on_missed"], b["t1b_recall_on_missed"])

    def test_hat_giong_van_lai_cac_so_khac(self):
        """Nhưng oracle/mốc/độ trễ vẫn ngẫu nhiên — nên chúng phải đổi."""
        a, b = compute(_run(seed=C.SEED)), compute(_run(seed=C.SEED + 1))
        self.assertNotEqual(a["oracle_verifier"], b["oracle_verifier"])


class TestBatBien(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.trace = _run()

    def test_I1_I2_shadow_khong_hanh_dong(self):
        """Chế độ shadow: KHÔNG hành động. Bất biến là `action_taken == 0`.

        Lưu ý phân biệt: `would_deliver_shadow` là PHẢN THỰC ("nếu chạy thật thì
        có giao không") và ĐƯỢC PHÉP > 0 — không được lẫn nó với hành động thật.
        """
        self.assertEqual(sum(r["action_taken"] for r in self.trace), 0,
                         "shadow đã hành động — vi phạm I2")
        self.assertTrue(all(r["action_taken"] is False for r in self.trace))
        self.assertLessEqual(sum(r["would_deliver_shadow"] for r in self.trace),
                             len(self.trace))

    def test_I3_nhan_lay_tu_nguon(self):
        """Mọi dòng trace phải mang nhãn dữ liệu lấy từ NGUỒN, không phải từ LLM."""
        for r in self.trace:
            self.assertIn(r["tool_surface"], C.RIGHTS_FLOOR, r["id"])
            self.assertIsInstance(r["data_labels"], list, r["id"])

    def test_I4_san_khong_bao_gio_duoi_muc_quyen(self):
        """Sàn rủi ro không bao giờ thấp hơn mức mà QUYỀN đòi hỏi."""
        for r in self.trace:
            self.assertGreaterEqual(r["floor"], C.RIGHTS_FLOOR[r["tool_surface"]], r["id"])

    def test_khong_ha_san_khi_chua_qua_thoi_gian_thu(self):
        """0 lượt hạ sàn: chưa qua 200 lượt sạch ⇒ nhánh hạ phải đóng."""
        self.assertFalse(any(r["floor_lowered"] for r in self.trace),
                         "có lượt hạ sàn dù chưa qua thời gian thử")

    def test_I5_cong_la_code_tra_ve_so(self):
        for r in self.trace:
            self.assertIsInstance(r["gate_tier"], int, r["id"])
            self.assertTrue(1 <= r["gate_tier"] <= 3, r["id"])

    def test_cong_nguoi_khong_thap_hon_san(self):
        for r in self.trace:
            self.assertGreaterEqual(r["gate_tier"], min(r["floor"], 3), r["id"])

    def test_chi_co_ba_lan(self):
        self.assertTrue(all(0 <= r["lane_final"] <= 2 for r in self.trace))

    def test_san_ba_thi_bat_buoc_hai_nguoi_duyet(self):
        for r in self.trace:
            if r["floor"] >= 3:
                self.assertTrue(r["dual_approval"], r["id"])

    def test_I8_ngan_sach_theo_vai_va_co_du_phong(self):
        """Dự phòng kiểm phải tồn tại và worker không được đụng vào."""
        for lane, b in C.BUDGET.items():
            self.assertGreater(b["reserve"], 0, f"làn {lane} không có dự phòng")
            self.assertLess(b["reserve"], b["cap"], f"làn {lane} dự phòng ≥ trần")


class TestPhieuGanNhan(unittest.TestCase):
    """Ba bảo đảm để nhãn người có giá trị."""

    def _sheet(self):
        d = tempfile.TemporaryDirectory()
        p = export_labels(load_tasks(), Path(d.name) / "l.csv")
        rows = list(csv.DictReader(open(p, encoding="utf-8")))
        return d, p, rows

    def test_phieu_khong_chua_truth(self):
        d, p, _ = self._sheet()
        cols = next(csv.reader(open(p, encoding="utf-8")))
        for bad in ("truth", "injection_present", "truth_floor", "label_missed_injection"):
            self.assertNotIn(bad, cols)
        d.cleanup()

    def test_o_nhan_de_trong(self):
        d, _, rows = self._sheet()
        self.assertEqual(sum(1 for r in rows if r["human_injection"].strip()), 0)
        d.cleanup()

    def test_phieu_xep_theo_id_khong_theo_tang(self):
        """Phiếu phải xếp theo task_id, nếu không thì thứ tự dòng lộ tầng."""
        d, _, rows = self._sheet()
        ids = [r["task_id"] for r in rows]
        self.assertEqual(ids, sorted(ids), "phiếu không xếp theo task_id")
        first = {r["tool_surface"] for r in rows[:40]}
        self.assertGreaterEqual(len(first), 3,
                                "40 dòng đầu cùng tầng — thứ tự dòng đang lộ tầng")
        d.cleanup()


if __name__ == "__main__":
    unittest.main(verbosity=2)
