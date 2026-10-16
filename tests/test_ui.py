"""Kiểm lớp trình bày mới và màn thống kê."""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from frog import stats, ui                        # noqa: E402
from frog.cli import cmd_run                      # noqa: E402

RUN = Path()


def setUpModule():
    global RUN
    RUN = Path(tempfile.mkdtemp(prefix="frog-stats-"))
    cmd_run(Namespace(out=str(RUN), cache_hit=0.0, seed=1, n=0, labels=None,
                      quiet=True, json=False, classifier="keyword", provider=None,
                      model=None, api_key=None, base_url=None, no_cache=True))


def tearDownModule():
    shutil.rmtree(RUN, ignore_errors=True)


class TestLinhVat(unittest.TestCase):
    def setUp(self):
        ui.set_color(False)

    def tearDown(self):
        ui.set_color(None)

    def test_note_khong_dung_icon(self):
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            for kind in ("info", "ok", "warn", "bad"):
                ui.note("xin chao", kind)
        out = buf.getvalue()
        for ch in ("✓", "✗", "•", "⏱", "⚠", "⚙", "▸"):
            self.assertNotIn(ch, out)
        self.assertIn("xong", out)
        self.assertIn("xin chao", out)

    def test_masthead_co_mat_va_chu(self):
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ui.masthead(["frog"])
        out = buf.getvalue()
        self.assertIn("▐▛███▜▌", out)
        self.assertIn("▗▄ ▄▖", out)
        self.assertIn("frog", out)
        self.assertGreaterEqual(len(ui.MASCOT), 4)


class TestChuKhoi(unittest.TestCase):
    def setUp(self):
        ui.set_color(False)

    def tearDown(self):
        ui.set_color(None)

    def test_big_du_nam_dong(self):
        rows = ui.big("146.3M")
        self.assertEqual(len(rows), 5)
        self.assertTrue(all(isinstance(r, str) for r in rows))

    def test_big_moi_dong_dai_bang_nhau(self):
        rows = ui.big("320")
        self.assertEqual(len({len(r) for r in rows}), 1, "các dòng phải thẳng cột")

    def test_big_ky_tu_la_khong_vo(self):
        self.assertEqual(len(ui.big("Z?")), 5)

    def test_big_khong_mau_khi_tat_mau(self):
        self.assertNotIn("\x1b", "".join(ui.big("12")))


class TestLuoiCham(unittest.TestCase):
    def setUp(self):
        ui.set_color(False)

    def tearDown(self):
        ui.set_color(None)

    def test_heat_so_dong_bang_so_hang(self):
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ui.heat([[0, 1, 2], [1, 0, 2]], row_labels=["S1", "S2"])
        lines = [l for l in buf.getvalue().splitlines() if l.strip()]
        self.assertEqual(len(lines), 2)

    def test_heat_nhan_dong(self):
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ui.heat([[0, 1]], row_labels=["S7"])
        self.assertIn("S7", buf.getvalue())

    def test_heat_chiu_cuong_do_ngoai_khoang(self):
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ui.heat([[9, -3]])       # không được vỡ
        self.assertTrue(buf.getvalue().strip())


class TestThongKe(unittest.TestCase):
    def test_doc_duoc_metrics(self):
        m, t, d = stats._load(str(RUN))
        self.assertEqual(m["n"], 320)
        self.assertTrue(t)

    def test_thieu_thu_muc_thi_bao_ro(self):
        with self.assertRaises(FileNotFoundError):
            stats._load("/tmp/khong-co-thu-muc-nay-r0")

    def test_moi_chi_so_lon_dung_duoc(self):
        m, t, _ = stats._load(str(RUN))
        for key, (label, fn) in stats.HEADLINES.items():
            v = fn(m, t)
            self.assertTrue(str(v).strip(), f"chỉ số {key} rỗng")

    def test_luoi_lan_phu_moi_tang(self):
        m, t, _ = stats._load(str(RUN))
        cells, strata, _ = stats._lane_cells(t)
        self.assertEqual(len(cells), len(strata))
        self.assertGreater(len(strata), 1)

    def test_render_chay_khong_vo(self):
        import io
        import contextlib
        ui.set_color(False)
        try:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                stats.render(str(RUN), "cost")
            out = buf.getvalue()
        finally:
            ui.set_color(None)
        self.assertIn("r0-shadow", out)
        self.assertIn("stats", out)

    def test_render_moi_chi_so(self):
        import io
        import contextlib
        ui.set_color(False)
        try:
            for k in stats.HEADLINES:
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    stats.render(str(RUN), k)
                self.assertTrue(buf.getvalue().strip())
        finally:
            ui.set_color(None)


if __name__ == "__main__":
    unittest.main(verbosity=2)
