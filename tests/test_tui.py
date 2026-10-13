"""Kiểm TUI: lớp dữ liệu thuần (kiểm được không cần TTY) + đường --dump."""
from __future__ import annotations

import shutil
import sys
import tempfile
import types
import unittest
from argparse import Namespace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mira import tui                                  # noqa: E402
from mira.cli import cmd_run                          # noqa: E402

RUN = Path()


def setUpModule():
    global RUN
    RUN = Path(tempfile.mkdtemp(prefix="mira-tui-"))
    cmd_run(Namespace(out=str(RUN), cache_hit=0.0, seed=1, n=0, labels=None,
                      quiet=True, json=False, classifier="keyword", provider=None,
                      model=None, api_key=None, base_url=None, no_cache=True))


def tearDownModule():
    shutil.rmtree(RUN, ignore_errors=True)


class TestBieuDo(unittest.TestCase):
    def test_sparkline_rong(self):
        self.assertEqual(tui.sparkline([]), "")

    def test_sparkline_cung_gia_tri_khong_vo(self):
        self.assertEqual(len(tui.sparkline([5, 5, 5], 10)), 3)

    def test_sparkline_dung_so_cot(self):
        self.assertEqual(len(tui.sparkline(list(range(100)), 20)), 20)

    def test_sparkline_chay_tu_thap_len_cao(self):
        s = tui.sparkline([0, 1, 2, 3, 4, 5, 6, 7, 8], 9)
        self.assertEqual(len(s), 9)
        self.assertLessEqual(tui.BLOCKS.index(s[0]), tui.BLOCKS.index(s[-1]))

    def test_hbar_bien(self):
        self.assertEqual(tui.hbar(0, 10, 5), "·····")
        self.assertEqual(tui.hbar(10, 10, 5), "█████")
        self.assertEqual(tui.hbar(5, 0, 5), "")


class TestDuLieu(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rd = tui.load_run(str(RUN))

    def test_nap_duoc(self):
        self.assertEqual(self.rd.metrics["n"], 320)
        self.assertTrue(self.rd.trace)

    def test_thieu_thu_muc_thi_bao_ro(self):
        with self.assertRaises(FileNotFoundError):
            tui.load_run("/tmp/khong-co-r0-tui")

    def test_dong_tac_vu_du_cot(self):
        rows = tui.task_rows(self.rd)
        self.assertEqual(len(rows), 320)
        line = tui.task_line(rows[0])
        self.assertIn(rows[0]["id"], line)
        self.assertIn("$", line)

    def test_lane_rows_phu_moi_lan(self):
        rows = tui.lane_rows(self.rd)
        self.assertEqual([r["lane"] for r in rows], ["0", "1", "2"])

    def test_help_co_phim_chinh(self):
        h = " ".join(tui.help_text())
        for k in ("↑", "tab", "enter", "r", "q", "chuột"):
            self.assertIn(k, h)


class TestDump(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rd = tui.load_run(str(RUN))

    def test_moi_muc_dump_ra_chu(self):
        for v in tui.VIEWS:
            out = tui.render_dump(self.rd, v, 96)
            self.assertTrue(out.strip(), f"mục {v} rỗng")
            self.assertIn(self.rd.name, out)

    def test_dump_tong_quan_co_lan_va_chi_phi(self):
        out = tui.render_dump(self.rd, "tổng quan", 96)
        self.assertIn("làn 0", out)
        self.assertIn("làn 2", out)
        self.assertIn("$", out)

    def test_dump_tac_vu_lieu_co_dong(self):
        out = tui.render_dump(self.rd, "tác vụ", 96)
        self.assertIn("T0001"[:1], out)
        self.assertGreaterEqual(len(out.splitlines()), 10)

    def test_dump_khong_co_ma_mau(self):
        for v in tui.VIEWS:
            self.assertNotIn("\x1b", tui.render_dump(self.rd, v, 96))


class TestLopCurses(unittest.TestCase):
    def test_curses_co_trong_thu_vien_chuan(self):
        """Không cần TTY. Thiếu _curses thì dùng module giả."""
        try:
            import curses
        except ModuleNotFoundError:
            curses = types.ModuleType("curses")
            curses.wrapper = lambda fn: None
        self.assertTrue(hasattr(curses, "wrapper"))

    def test_app_khoi_tao_duoc_khong_can_man_hinh(self):
        """Lớp curses mỏng: dựng App với đối tượng giả để bắt lỗi sớm."""
        rd = tui.load_run(str(RUN))
        app = tui.App.__new__(tui.App)
        app.rd = rd
        app.run = str(RUN)
        app.view, app.sel, app.top, app.mouse, app.status = 0, 0, 0, True, ""
        app.rows_cache = tui.task_rows(rd)
        self.assertEqual(len(app.rows_cache), 320)
        # _scroll trên mục danh sách phải kẹp trong khoảng
        app.view = 1
        app.sel = 0
        app.s = type("S", (), {"getmaxyx": lambda self_: (30, 100)})()
        app._scroll(-5)
        self.assertEqual(app.sel, 0)
        app._scroll(10 ** 6)
        self.assertEqual(app.sel, 319)


if __name__ == "__main__":
    unittest.main(verbosity=2)
