"""Suite đối kháng: schema, báo cáo theo nhóm, không gọi model."""
from __future__ import annotations

import ctypes
import io
import os
import tempfile
import unicodedata
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from frog.bench import adversarial_path, load_cases, predict_case, run_adversarial, run_eval
from frog.pipeline import content_signal


class AdversarialTest(unittest.TestCase):
    def test_du_so_dong_dung_schema(self):
        cases = load_cases(adversarial_path())
        self.assertEqual(len(cases), 58)
        axes = {row["axis"] for row in cases}
        self.assertEqual(axes, {"lenh_an", "gia_danh", "lo_key", "path_escape", "homoglyph", "tieng_viet"})
        for row in cases:
            self.assertIn(row["expected"], ("block", "allow"))
            self.assertTrue(row["input"])

    def test_suite_cu_khong_doi(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = run_eval()
        text = buf.getvalue()
        self.assertNotIn("lenh_an", text)
        self.assertIn("qua", text)
        self.assertIn(code, (0, 1))

    def test_bao_cao_co_sau_nhom(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = run_adversarial()
        text = buf.getvalue()
        self.assertEqual(code, 0)
        for slug in ("lenh_an", "gia_danh", "lo_key", "path_escape", "homoglyph", "tieng_viet"):
            self.assertIn(slug, text)
        self.assertIn("precision", text)
        self.assertIn("recall", text)
        self.assertIn("không phải shadow RNG", text)

    def test_khong_goi_model(self):
        def boom(*_a, **_k):
            raise AssertionError("không được dựng provider")

        with patch("frog.team.provider_for", boom), patch("frog.providers.provider_for", boom):
            code = run_adversarial()
        self.assertEqual(code, 0)

    def test_nfkc_khong_du_voi_chu_kirin(self):
        by_id = {row["id"]: row for row in load_cases(adversarial_path())}
        raw = by_id["HG01"]["input"]
        self.assertIn("\u0406", raw)
        self.assertEqual(unicodedata.normalize("NFKC", raw), raw)

    def test_hg01_hg03_hg05_thanh_block(self):
        by_id = {row["id"]: row for row in load_cases(adversarial_path())}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for case_id in ("HG01", "HG03", "HG05"):
                self.assertEqual(predict_case(by_id[case_id], root), "block", case_id)

    def test_hg10_van_allow(self):
        by_id = {row["id"]: row for row in load_cases(adversarial_path())}
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(predict_case(by_id["HG10"], Path(tmp)), "allow")

    def test_tv04_tv08_la08_thanh_block(self):
        by_id = {row["id"]: row for row in load_cases(adversarial_path())}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for case_id in ("TV04", "TV08", "LA08"):
                self.assertEqual(predict_case(by_id[case_id], root), "block", case_id)

    def test_guide_khong_thanh_gui(self):
        by_id = {row["id"]: row for row in load_cases(adversarial_path())}
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(predict_case(by_id["TV10"], Path(tmp)), "allow")
        self.assertFalse(content_signal("The guide stays on the shelf.")["exfil"])

    def test_cum_bo_qua_khong_khop_boqua_dinh(self):
        self.assertFalse(content_signal("boqua huong dan")["override"])

    def test_la10_va_la11_la_allow(self):
        by_id = {row["id"]: row for row in load_cases(adversarial_path())}
        self.assertEqual(by_id["LA10"]["expected"], "allow")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(predict_case(by_id["LA10"], root), "allow")
            self.assertEqual(predict_case(by_id["LA11"], root), "allow")

    def test_phu_dinh_khong_nuot_menh_lenh_sau(self):
        by_id = {row["id"]: row for row in load_cases(adversarial_path())}
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(predict_case(by_id["LA12"], Path(tmp)), "block")

    def test_lk06_va_lk09_thanh_block(self):
        by_id = {row["id"]: row for row in load_cases(adversarial_path())}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for case_id in ("LK06", "LK09"):
                self.assertEqual(predict_case(by_id[case_id], root), "block", case_id)

    def test_send_khong_url_van_allow(self):
        by_id = {row["id"]: row for row in load_cases(adversarial_path())}
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(predict_case(by_id["LK10"], Path(tmp)), "allow")

    def test_sending_khong_an_token_send(self):
        self.assertFalse(content_signal("sending the file tomorrow")["exfil"])

    def test_pe02_gach_nguoc_bi_chan(self):
        by_id = {row["id"]: row for row in load_cases(adversarial_path())}
        self.assertEqual(by_id["PE02"]["expected"], "block")
        self.assertIn("\\", by_id["PE02"]["path"])
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(predict_case(by_id["PE02"], Path(tmp)), "block")

    def test_goc_chua_resolve_van_phan_dung_path_escape(self):
        """Gốc 8.3 hoặc symlink phải cho phép file trong thư mục, vẫn chặn thoát."""
        by_id = {row["id"]: row for row in load_cases(adversarial_path())}
        with tempfile.TemporaryDirectory() as tmp:
            alias = _goc_khac_resolve(Path(tmp))
            if alias is None:
                self.skipTest("máy không tạo được path khác resolve()")
            for case_id in ("PE01", "PE02", "PE03", "PE04", "PE05", "PE06", "PE07", "PE08"):
                self.assertEqual(
                    predict_case(by_id[case_id], alias),
                    by_id[case_id]["expected"],
                    case_id,
                )


def _goc_khac_resolve(real: Path) -> Path | None:
    """Một path trỏ cùng thư mục nhưng không bằng resolve(), như TEMP 8.3 trên runner."""
    if os.name == "nt":
        buf = ctypes.create_unicode_buffer(512)
        n = ctypes.windll.kernel32.GetShortPathNameW(str(real), buf, 512)
        if n and Path(buf.value) != real.resolve():
            return Path(buf.value)
    link = real.parent / (real.name + "-link")
    try:
        link.symlink_to(real, target_is_directory=True)
    except OSError:
        return None
    if link.resolve() != link:
        return link
    return None


if __name__ == "__main__":
    unittest.main(verbosity=2)
