"""Cổng 0.90: recall hoặc precision của bất kỳ nhóm nào dưới ngưỡng thì fail."""
import unittest

from mira.bench import AXES, QUALITY_FLOOR, adversarial_path, gate_failures, load_cases, score_cases


def _nhom(slug: str, precision, recall) -> dict:
    return {"slug": slug, "name": slug, "precision": precision, "recall": recall}


class QualityGateTest(unittest.TestCase):
    def test_recall_duoi_0_90_thi_tra_1(self):
        self.assertEqual(QUALITY_FLOOR, 0.90)
        loi = gate_failures([_nhom("lenh_an", 1.0, 0.86)])
        self.assertTrue(loi)
        self.assertTrue(any("lenh_an" in dong and "recall" in dong for dong in loi))

    def test_precision_duoi_0_90_thi_tra_1(self):
        loi = gate_failures([_nhom("lenh_an", 0.86, 1.0)])
        self.assertTrue(loi)
        self.assertTrue(any("lenh_an" in dong and "precision" in dong for dong in loi))

    def test_ca_sau_nhom_bang_0_90_thi_rong(self):
        groups = [_nhom(slug, 0.90, 0.90) for slug, _name in AXES]
        groups.append(_nhom("ngoai_thuoc", 0.10, 0.10))
        self.assertEqual(gate_failures(groups), [])

    def test_eval_that_hom_nay_chua_qua_cong(self):
        """Suite đóng băng đang dưới sàn. Xóa test này khi DETECT-1 làm bảng xanh."""
        self.assertTrue(gate_failures(score_cases(load_cases(adversarial_path()))))


if __name__ == "__main__":
    unittest.main(verbosity=2)
