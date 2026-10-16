"""TUI toàn màn hình — dùng `curses` trong THƯ VIỆN CHUẨN, không thêm phụ thuộc.

Vì sao không kéo textual/rich: `curses` đã cho màn hình thay thế, cuộn, phím điều
hướng, chuột và vẽ lại khi đổi kích thước — đủ cho một app full-screen thật. Giữ
được tính "cài xong chạy ngay, không cần pip gì thêm".

Lớp dữ liệu và lớp vẽ tách rời:
  * hàm thuần (`load_run`, `sparkline`, `overview_text`, …) — kiểm được không cần TTY
  * lớp curses — mỏng, chỉ lo vẽ và bắt phím/chuột
  * `--dump` in một khung ra văn bản — dùng cho test và cho máy không có TTY
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from . import config as C

VIEWS = ["tổng quan", "tác vụ", "làn", "nhãn", "trợ giúp"]

BLOCKS = " ▁▂▃▄▅▆▇█"


# =============================================================== lớp dữ liệu
@dataclass
class RunData:
    metrics: dict
    trace: list[dict]
    path: Path

    @property
    def name(self) -> str:
        return self.path.name


def load_run(run: str) -> RunData:
    d = Path(run)
    mf = d / "metrics.json"
    if not mf.exists():
        raise FileNotFoundError(f"không thấy {mf} — chạy `r0-shadow run --out {run}` trước")
    metrics = json.loads(mf.read_text(encoding="utf-8"))
    trace: list[dict] = []
    tf = d / "trace.jsonl"
    if tf.exists():
        for line in tf.read_text(encoding="utf-8").splitlines():
            if line.strip():
                trace.append(json.loads(line))
    return RunData(metrics=metrics, trace=trace, path=d)


# ================================================================ hàm thuần
def sparkline(values: list[float], width: int = 40) -> str:
    """Biểu đồ mini. Rỗng/cùng giá trị -> không vỡ."""
    if not values:
        return ""
    v = list(values)
    if len(v) > width:
        step = len(v) / width
        v = [v[min(len(v) - 1, int(i * step))] for i in range(width)]
    lo, hi = min(v), max(v)
    if hi <= lo:
        return "▄" * len(v)
    return "".join(BLOCKS[max(0, min(8, int(round((x - lo) / (hi - lo) * 8))))] for x in v)


def hbar(value: float, vmax: float, width: int = 24, full: str = "█", rest: str = "·") -> str:
    if vmax <= 0 or width <= 0:
        return ""
    k = max(0, min(width, int(round(width * value / vmax))))
    return full * k + rest * (width - k)


def _lane_counts(m: dict) -> tuple[int, int, int]:
    d = m.get("lane_distribution", {})
    return int(d.get("0", 0)), int(d.get("1", 0)), int(d.get("2", 0))


def overview_text(rd: RunData, width: int = 96) -> list[str]:
    m, t = rd.metrics, rd.trace
    n = m.get("n", len(t))
    l0, l1, l2 = _lane_counts(m)
    led = m.get("ledger") or {}
    total = led.get("total_usd", 0.0)
    lat = m.get("latency_overall", {})
    out: list[str] = []
    out.append("")
    out.append(f"  {n} tác vụ   ·   ${total:,.2f}   ·   audit {m.get('audit_hours_per_week', 0):.1f}h/tuần")
    out.append("")
    vmax = max(l0, l1, l2, 1)
    for i, (lab, cnt) in enumerate((("làn 0", l0), ("làn 1", l1), ("làn 2", l2))):
        pct = 100 * cnt / n if n else 0
        out.append(f"  {lab}  {hbar(cnt, vmax, 28)} {cnt:>4}  {pct:5.1f}%")
    out.append("")
    out.append(f"  VC escalate {100 * m.get('VC_escalate_rate', 0):5.1f}%"
               f"   2 người duyệt {100 * m.get('dual_approval_rate', 0):5.1f}%"
               f"   cổng t3 {100 * m.get('VC_gate3_rate', 0):5.1f}%")
    out.append(f"  độ trễ p50 {lat.get('p50', 0):>6.1f}s   p95 {lat.get('p95', 0):>7.1f}s")
    out.append("")
    # chi phí mỗi làn
    cb = m.get("cost_by_lane", {})
    if cb:
        out.append("  chi phí mỗi tác vụ (p50 / p95)")
        mx = max((v.get("p95", 0) for v in cb.values()), default=1) or 1
        for lane in sorted(cb, key=int):
            v = cb[lane]
            out.append(f"  làn {lane}  {hbar(v.get('p95', 0), mx, 24)} "
                       f"${v.get('p50', 0):.4f} / ${v.get('p95', 0):.4f}")
    # T1b
    out.append("")
    rec = m.get("t1b_recall_on_missed")
    out.append(f"  T1b  recall {rec if rec is not None else '—'}   "
               f"precision {m.get('t1b_precision', 0):.3f}   "
               f"nâng {100 * m.get('t1b_raise_rate', 0):.1f}%")
    cal = m.get("t1b_calibration", {})
    if cal:
        out.append("  hiệu chuẩn: " + "   ".join(
            f"{k}→{100 * v['risk_rate']:.0f}%" for k, v in sorted(cal.items())))
    return out


TASK_COLS = [("id", 6), ("tầng", 5), ("làn", 4), ("độ tin", 7), ("bc", 3),
             ("$", 9), ("giây", 7), ("bề mặt", 14)]


def task_rows(rd: RunData) -> list[dict]:
    rows = []
    for r in rd.trace:
        c = r.get("classifier") or {}
        rows.append({
            "id": r.get("id", ""), "stratum": r.get("stratum", ""),
            "lane": r.get("lane_final", 0), "conf": c.get("confidence", 0.0),
            "ev": c.get("n_evidence", 0), "cost": r.get("cost_usd", 0.0),
            "lat": r.get("latency_s", 0.0), "surface": r.get("tool_surface", ""),
            "raised": bool(c.get("raised")), "raw": r,
        })
    return rows


def task_line(row: dict) -> str:
    return (f"{row['id']:<6} {row['stratum']:<5} {row['lane']:>4} "
            f"{row['conf']:>7.2f} {row['ev']:>3} ${row['cost']:>8.4f} "
            f"{row['lat']:>7.1f} {row['surface']:<14}")


def lane_rows(rd: RunData) -> list[dict]:
    m = rd.metrics
    cb, lb = m.get("cost_by_lane", {}), m.get("latency_by_lane", {})
    out = []
    for lane in sorted(cb, key=int):
        c = cb[lane]
        out.append({"lane": lane, "n": c.get("n", 0), "p50": c.get("p50", 0.0),
                    "p95": c.get("p95", 0.0), "cap": c.get("cap"),
                    "lat50": (lb.get(lane) or {}).get("p50", 0.0),
                    "lat95": (lb.get(lane) or {}).get("p95", 0.0),
                    "share": (m.get("lane2_cost_share") or {}) if lane == "2" else None})
    return out


def label_rows(rd: RunData) -> list[dict]:
    """Trạng thái phiếu nhãn trong thư mục lần chạy (nếu có)."""
    out = []
    for name, kind in (("labels.csv", "phiếu"), ("labels-triage.csv", "danh sách ngắn")):
        p = rd.path / name
        if not p.exists():
            continue
        import csv
        rows = list(csv.DictReader(p.open(encoding="utf-8")))
        filled = sum(1 for r in rows if (r.get("human_injection") or "").strip())
        out.append({"file": name, "kind": kind, "n": len(rows), "filled": filled})
    return out


def help_text() -> list[str]:
    return [
        "",
        "  phím",
        "    ↑ ↓  /  k j      cuộn danh sách",
        "    ← →  /  tab       đổi mục",
        "    1 … 5             nhảy thẳng tới mục",
        "    enter             mở chi tiết tác vụ",
        "    r                 nạp lại số từ đĩa",
        "    m                 bật/tắt chuột",
        "    ?                 mục trợ giúp này",
        "    q                 thoát",
        "",
        "  chuột",
        "    bấm vào tab để đổi mục · bấm dòng để chọn",
        "    lăn chuột để cuộn",
        "",
        "  ghi chú",
        "    TUI chỉ ĐỌC số đã đo. Muốn đo lại: rồi chạy",
        "    `r0-shadow run --out <thư mục>` từ terminal khác.",
        "    Máy không có TTY: dùng `r0-shadow tui --dump`.",
    ]


def render_dump(rd: RunData, view: str = "tổng quan", width: int = 96) -> str:
    """In một khung ra văn bản — cho test và cho máy không có TTY."""
    L: list[str] = []
    L.append(f"r0-shadow · {rd.name} · mục: {view}")
    L.append("─" * min(width, 96))
    if view == "tổng quan":
        L += overview_text(rd, width)
    elif view == "tác vụ":
        L.append("  " + " ".join(f"{h:<{w}}" for h, w in TASK_COLS))
        for row in task_rows(rd):
            L.append("  " + task_line(row))
    elif view == "làn":
        for r in lane_rows(rd):
            cap = f"${r['cap']:.2f}" if r["cap"] else "—"
            L.append(f"  làn {r['lane']}  n={r['n']:<4} p50 ${r['p50']:.4f} "
                     f"p95 ${r['p95']:.4f}  trần {cap}  độ trễ p50 {r['lat50']:.1f}s")
    elif view == "nhãn":
        rows = label_rows(rd)
        if not rows:
            L.append("  (thư mục này không có phiếu nhãn)")
        for r in rows:
            L.append(f"  {r['file']:<20} {r['kind']:<14} {r['filled']}/{r['n']} đã điền")
    else:
        L += help_text()
    return "\n".join(L)


# ================================================================== lớp curses
PAIRS = {"accent": 1, "dim": 2, "ok": 3, "warn": 4, "bad": 5, "title": 6}


def _init_colors() -> None:
    import curses
    try:
        curses.start_color()
        curses.use_default_colors()          # tôn trọng nền terminal
    except Exception:
        return
    spec = {"accent": curses.COLOR_CYAN, "dim": curses.COLOR_WHITE,
            "ok": curses.COLOR_GREEN, "warn": curses.COLOR_YELLOW,
            "bad": curses.COLOR_RED, "title": curses.COLOR_CYAN}
    for name, fg in spec.items():
        try:
            curses.init_pair(PAIRS[name], fg, -1)
        except Exception:
            pass


class App:
    def __init__(self, stdscr, rd: RunData, run: str):
        import curses
        self.curses = curses
        self.s = stdscr
        self.rd = rd
        self.run = run
        self.view = 0
        self.sel = 0
        self.top = 0
        self.mouse = True
        self.status = ""
        self.rows_cache = task_rows(rd)

    # ---------------------------------------------------------- tiện ích vẽ
    def _add(self, y, x, text, attr=0, maxw=None):
        h, w = self.s.getmaxyx()
        if y < 0 or y >= h or x >= w:
            return
        if maxw is not None:
            text = text[:max(0, maxw)]
        try:
            self.s.addstr(y, x, text[:max(0, w - x - 1)], attr)
        except self.curses.error:
            pass

    def _tabs(self, w):
        x = 1
        for i, name in enumerate(VIEWS):
            lab = f" {i + 1} {name} "
            attr = self.curses.color_pair(PAIRS["accent"]) | self.curses.A_BOLD if i == self.view else \
                self.curses.color_pair(PAIRS["dim"])
            self._add(1, x, lab, attr)
            x += len(lab) + 1

    def _frame(self):
        h, w = self.s.getmaxyx()
        self.s.erase()
        title = f" r0-shadow · {self.rd.name} "
        self._add(0, 1, title, self.curses.color_pair(PAIRS["title"]) | self.curses.A_BOLD)
        self._add(0, max(1, w - len(self.run) - 2), f"{self.run} ",
                  self.curses.color_pair(PAIRS["dim"]))
        self._add(1, 0, "─" * w, self.curses.color_pair(PAIRS["dim"]))
        self._tabs(w)
        self._add(2, 0, "─" * w, self.curses.color_pair(PAIRS["dim"]))
        m, t = self.rd.metrics, self.rd.trace
        l0, l1, l2 = _lane_counts(m)
        foot = (f" n={m.get('n', len(t))} · làn {l0}/{l1}/{l2} · "
                f"${(m.get('ledger') or {}).get('total_usd', 0):.2f} · "
                f"↑↓ cuộn · tab đổi mục · q thoát · ? trợ giúp ")
        if self.status:
            foot = " " + self.status + " · " + foot.strip()
        self._add(h - 1, 0, foot[:w - 1], self.curses.color_pair(PAIRS["dim"]))
        return h, w

    # ------------------------------------------------------------- từng mục
    def _draw_overview(self, y0, y1, w):
        lines = overview_text(self.rd, w)
        for i, ln in enumerate(lines):
            y = y0 + i - self.top
            if y0 <= y < y1:
                self._add(y, 0, ln, self.curses.color_pair(PAIRS["dim"]))

    def _draw_tasks(self, y0, y1, w):
        head = "  " + " ".join(f"{h:<{cw}}" for h, cw in TASK_COLS)
        self._add(y0, 0, head, self.curses.color_pair(PAIRS["accent"]) | self.curses.A_BOLD)
        avail = max(1, y1 - y0 - 1)
        self.sel = max(0, min(self.sel, len(self.rows_cache) - 1))
        if self.sel < self.top:
            self.top = self.sel
        if self.sel >= self.top + avail:
            self.top = self.sel - avail + 1
        for i in range(avail):
            k = self.top + i
            if k >= len(self.rows_cache):
                break
            row = self.rows_cache[k]
            attr = self.curses.A_REVERSE if k == self.sel else 0
            if not attr:
                attr = self.curses.color_pair(
                    PAIRS["warn"] if row["raised"] else PAIRS["dim"])
            self._add(y0 + 1 + i, 0, "  " + task_line(row), attr)

    def _draw_lanes(self, y0, y1, w):
        rows = lane_rows(self.rd)
        mx = max((r["p95"] for r in rows), default=1) or 1
        for i, r in enumerate(rows):
            y = y0 + i * 2
            if not (y0 <= y < y1):
                continue
            cap = f"trần ${r['cap']:.2f}" if r["cap"] else "không trần"
            self._add(y, 1, f"làn {r['lane']}   n={r['n']}   {cap}",
                      self.curses.color_pair(PAIRS["accent"]) | self.curses.A_BOLD)
            self._add(y + 1, 1, f"  {hbar(r['p95'], mx, 30)} "
                                f"p50 ${r['p50']:.4f}  p95 ${r['p95']:.4f}  "
                                f"độ trễ {r['lat50']:.0f}s/{r['lat95']:.0f}s",
                      self.curses.color_pair(PAIRS["dim"]))
        # biểu đồ chi phí theo tác vụ
        vals = [r.get("cost_usd", 0) for r in self.rd.trace]
        if vals and y0 + len(rows) * 2 + 2 < y1:
            yy = y0 + len(rows) * 2 + 2
            self._add(yy, 1, "chi phí theo tác vụ", self.curses.color_pair(PAIRS["dim"]))
            self._add(yy + 1, 1, sparkline(vals, max(10, w - 6)),
                      self.curses.color_pair(PAIRS["accent"]))
            self._add(yy + 2, 1, "độ trễ theo tác vụ", self.curses.color_pair(PAIRS["dim"]))
            self._add(yy + 3, 1, sparkline([r.get("latency_s", 0) for r in self.rd.trace],
                                           max(10, w - 6)),
                      self.curses.color_pair(PAIRS["accent"]))

    def _draw_labels(self, y0, y1, w):
        rows = label_rows(self.rd)
        if not rows:
            self._add(y0, 2, "thư mục này không có phiếu nhãn — chạy "
                             "`r0-shadow labels export`", self.curses.color_pair(PAIRS["warn"]))
            return
        for i, r in enumerate(rows):
            y = y0 + i * 2
            if not (y0 <= y < y1):
                continue
            done = r["filled"] >= r["n"]
            attr = self.curses.color_pair(PAIRS["ok"] if done else PAIRS["warn"])
            self._add(y, 2, f"{r['file']}  ({r['kind']})", attr)
            self._add(y + 1, 4, f"{hbar(r['filled'], r['n'], 30)} "
                                f"{r['filled']}/{r['n']} đã điền",
                      self.curses.color_pair(PAIRS["dim"]))

    def _draw_help(self, y0, y1, w):
        for i, ln in enumerate(help_text()):
            y = y0 + i - self.top
            if y0 <= y < y1:
                self._add(y, 0, ln, self.curses.color_pair(PAIRS["dim"]))

    def _draw(self):
        h, w = self._frame()
        y0, y1 = 3, h - 1
        if self.view == 0:
            self._draw_overview(y0, y1, w)
        elif self.view == 1:
            self._draw_tasks(y0, y1, w)
        elif self.view == 2:
            self._draw_lanes(y0, y1, w)
        elif self.view == 3:
            self._draw_labels(y0, y1, w)
        else:
            self._draw_help(y0, y1, w)
        self.s.refresh()

    def _scroll(self, dy):
        h, _ = self.s.getmaxyx()
        avail = max(1, h - 4)
        if self.view == 1:
            self.sel = max(0, min(len(self.rows_cache) - 1, self.sel + dy))
        else:
            self.top = max(0, self.top + dy)
        if self.view == 1 and dy == 0:
            self.top = max(0, self.top - avail)

    def _detail(self):
        if not self.rows_cache:
            return
        r = self.rows_cache[self.sel]["raw"]
        c = r.get("classifier") or {}
        h, w = self.s.getmaxyx()
        self.s.erase()
        self._add(0, 1, f" tác vụ {r['id']} ", self.curses.color_pair(PAIRS["title"]) | self.curses.A_BOLD)
        self._add(1, 0, "─" * w, self.curses.color_pair(PAIRS["dim"]))
        lines = [
            f"yêu cầu      {r.get('request', '')[:w - 20]}",
            f"tầng         {r.get('stratum')}   bề mặt {r.get('tool_surface')}",
            f"làn          cơ sở {r.get('lane_base')} → cuối {r.get('lane_final')}"
            f"   sàn {r.get('floor')} ({r.get('floor_reason', '')[:40]})",
            f"cổng         tầng {r.get('gate_tier')} · {r.get('gate_minutes', 0):.0f} phút"
            f"{' · 2 người duyệt' if r.get('dual_approval') else ''}",
            f"classifier   {c.get('choice')} · tin {c.get('confidence')} · "
            f"bằng chứng {c.get('evidence')}",
            f"chi phí      ${r.get('cost_usd', 0):.6f}   độ trễ {r.get('latency_s')}s",
            f"mốc D4       {r.get('milestones', {}).get('milestones')}/"
            f"{r.get('milestones', {}).get('criteria_total')}",
            f"nhãn         injection={r.get('truth', {}).get('injection_present')} "
            f"· bỏ sót={r.get('truth', {}).get('label_missed_injection')}",
        ]
        for i, ln in enumerate(lines):
            self._add(2 + i, 2, ln, self.curses.color_pair(PAIRS["dim"]))
        self._add(h - 1, 0, " bất kỳ phím để quay lại "
                            "· ↑↓ chuyển tác vụ ", self.curses.color_pair(PAIRS["dim"]))
        self.s.refresh()
        while True:
            k = self.s.getch()
            if k in (self.curses.KEY_UP, ord("k")):
                self.sel = max(0, self.sel - 1)
                self._detail()
            elif k in (self.curses.KEY_DOWN, ord("j")):
                self.sel = min(len(self.rows_cache) - 1, self.sel + 1)
                self._detail()
            else:
                return

    # ---------------------------------------------------------------- vòng lặp
    def run_loop(self):
        curses = self.curses
        curses.curs_set(0)
        try:
            curses.mousemask(curses.ALL_MOUSE_EVENTS | curses.REPORT_MOUSE_POSITION)
        except Exception:
            self.mouse = False
        self.s.keypad(True)
        self.s.nodelay(False)
        while True:
            self._draw()
            k = self.s.getch()
            if k in (ord("q"), 27):
                return 0
            if k == curses.KEY_RESIZE:
                continue
            if k in (curses.KEY_UP, ord("k")):
                self._scroll(-1)
            elif k in (curses.KEY_DOWN, ord("j")):
                self._scroll(1)
            elif k in (curses.KEY_LEFT,):
                self.view = (self.view - 1) % len(VIEWS)
                self.top = 0
            elif k in (curses.KEY_RIGHT, 9):
                self.view = (self.view + 1) % len(VIEWS)
                self.top = 0
            elif ord("1") <= k <= ord("5"):
                self.view = k - ord("1")
                self.top = 0
            elif k in (curses.KEY_NPAGE,):
                self._scroll(10)
            elif k in (curses.KEY_PPAGE,):
                self._scroll(-10)
            elif k in (10, 13, curses.KEY_ENTER):
                if self.view == 1:
                    self._detail()
            elif k == ord("r"):
                try:
                    self.rd = load_run(self.run)
                    self.rows_cache = task_rows(self.rd)
                    self.status = "đã nạp lại"
                except Exception as e:                       # noqa: BLE001
                    self.status = f"lỗi nạp: {e}"
            elif k == ord("m"):
                self.mouse = not self.mouse
                self.status = "chuột: bật" if self.mouse else "chuột: tắt"
            elif k == ord("?"):
                self.view = VIEWS.index("trợ giúp")
                self.top = 0
            elif k == curses.KEY_MOUSE and self.mouse:
                self._mouse()

    def _mouse(self):
        curses = self.curses
        try:
            _id, mx, my, _z, bstate = curses.getmouse()
        except Exception:
            return
        if bstate & curses.BUTTON4_PRESSED:
            self._scroll(-3)
            return
        if bstate & curses.BUTTON5_PRESSED:
            self._scroll(3)
            return
        if my == 1:                                   # bấm vào thanh tab
            x = 1
            for i, name in enumerate(VIEWS):
                lab = f" {i + 1} {name} "
                if x <= mx < x + len(lab):
                    self.view = i
                    self.top = 0
                    return
                x += len(lab) + 1
        if self.view == 1 and my >= 4:                # bấm vào danh sách tác vụ
            k = self.top + (my - 4)
            if 0 <= k < len(self.rows_cache):
                self.sel = k


def _curses_main(stdscr, rd: RunData, run: str) -> int:
    _init_colors()
    return App(stdscr, rd, run).run_loop()


def cmd_tui(args) -> int:
    from . import ui
    try:
        rd = load_run(args.run)
    except FileNotFoundError as e:
        ui.note(str(e), "bad")
        return 2

    if args.dump:
        print(render_dump(rd, args.dump, ui.term_width()))
        return 0

    try:
        import curses
    except ImportError:
        ui.note("máy này không có `curses` (Windows?) — dùng `r0-shadow tui --dump` "
                "hoặc `r0-shadow stats`", "warn")
        print()
        print(render_dump(rd, "tổng quan", ui.term_width()))
        return 0

    if not __import__("sys").stdout.isatty():
        ui.note("đầu ra không phải TTY — in bản tĩnh thay vì mở TUI", "warn")
        print()
        print(render_dump(rd, "tổng quan", ui.term_width()))
        return 0

    try:
        curses.wrapper(_curses_main, rd, args.run)
    except KeyboardInterrupt:
        pass
    except Exception as e:                                   # noqa: BLE001
        ui.note(f"TUI lỗi: {type(e).__name__}: {e} — dùng `--dump`", "bad")
        return 1
    return 0
