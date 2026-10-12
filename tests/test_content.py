"""Kiểm NỘI DUNG THẬT: phiếu gán nhãn phải cho người gán thấy bằng chứng để đọc.

Điểm cốt lõi: nội dung có dấu hiệu payload ⟺ tác vụ thật sự có injection. Có vậy thì
`human_injection` mới là câu hỏi TRẢ LỜI ĐƯỢC, thay vì đoán một đồng xu ẩn.
"""
from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from r0.labels import FIELDS, export_labels, sheet_labelability   # noqa: E402
from r0.tasks import PAYLOAD_SIGNATURES, build_tasks              # noqa: E402

TASKS = build_tasks()


def _has_signature(text: str) -> bool:
    return any(s in text for s in PAYLOAD_SIGNATURES)


class TestNoiDungThat(unittest.TestCase):
    def test_moi_tac_vu_co_noi_dung(self):
        self.assertTrue(all(t.observable.get("content") for t in TASKS))

    def test_noi_dung_mang_dung_bang_chung(self):
        """Dấu hiệu payload có ⟺ injection_present. Đây là điều kiện để nhãn đọc được."""
        bad = [t.id for t in TASKS
               if _has_signature(t.observable["content"]) != bool(t.truth["injection_present"])]
        self.assertEqual(bad, [], f"nội dung lệch nhãn ở {len(bad)} tác vụ")

    def test_noi_dung_sach_khong_co_dau_hieu_payload(self):
        for t in TASKS:
            if not t.truth["injection_present"]:
                self.assertFalse(_has_signature(t.observable["content"]),
                                 f"{t.id} sạch mà vẫn có dấu hiệu payload")

    def test_co_duoi_lanh_tinh_de_phan_biet(self):
        """Nội dung sạch phải nhắc tới việc gửi dữ liệu — nếu không thì quá dễ."""
        clean = [t for t in TASKS if not t.truth["injection_present"]]
        mention = [t for t in clean if "gửi" in t.observable["content"] or "ngoài" in t.observable["content"]]
        self.assertGreater(len(mention), 0, "nội dung sạch phải có chỉ dẫn hợp lệ để phân biệt")

    def test_vi_tri_payload_chi_co_khi_co_injection(self):
        for t in TASKS:
            if t.truth["injection_present"]:
                self.assertIsNotNone(t.truth["payload_location"])
            else:
                self.assertIsNone(t.truth["payload_location"])

    def test_tai_lap_duoc(self):
        again = build_tasks()
        self.assertEqual([t.observable["content"] for t in TASKS],
                         [t.observable["content"] for t in again])

    def test_khong_doi_nhan_cu(self):
        """Thêm nội dung KHÔNG được đổi luồng chính — nhãn phải y như trước."""
        again = build_tasks()
        self.assertEqual([t.truth["injection_present"] for t in TASKS],
                         [t.truth["injection_present"] for t in again])
        self.assertEqual([t.truth["label_missed_injection"] for t in TASKS],
                         [t.truth["label_missed_injection"] for t in again])


class TestPhieuCoNoiDung(unittest.TestCase):
    def test_phieu_co_cot_noi_dung(self):
        self.assertIn("content", FIELDS)
        self.assertIn("content_kind", FIELDS)

    def test_phieu_xuat_ra_co_noi_dung_that(self):
        with tempfile.TemporaryDirectory() as d:
            p = export_labels(TASKS, Path(d) / "labels.csv")
            rows = list(csv.DictReader(p.open(encoding="utf-8")))
        self.assertEqual(len(rows), len(TASKS))
        self.assertTrue(all(r["content"].strip() for r in rows))
        # người gán đọc được nội dung ⇒ nhãn trả lời được
        n_sig = sum(1 for r in rows if _has_signature(r["content"]))
        self.assertEqual(n_sig, sum(1 for t in TASKS if t.truth["injection_present"]))

    def test_phieu_khong_lo_dap_an(self):
        with tempfile.TemporaryDirectory() as d:
            p = export_labels(TASKS, Path(d) / "labels.csv")
            head = p.read_text(encoding="utf-8").splitlines()[0]
        self.assertNotIn("truth", head)
        self.assertNotIn("injection_present", head)

    def test_kha_nhan_bao_da_co_noi_dung(self):
        r = sheet_labelability(TASKS)
        self.assertTrue(r["content_on_sheet"])
        self.assertEqual(r["n_with_content"], len(TASKS))
        self.assertFalse(r["determinable"], "metadata vẫn không suy ra được — phải đọc")
        self.assertIn("TRẢ LỜI ĐƯỢC", r["verdict"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
