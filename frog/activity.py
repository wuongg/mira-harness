"""Đọc nhật ký agent — các phiên lưu ở ~/.mira/sessions/*.jsonl.

Mỗi tệp phiên là JSONL: dòng `meta` (đầu), các dòng `message`, các dòng `event`
(công cụ đã gọi, cổng đã hỏi, tệp đã ghi). Module này chỉ ĐỌC — không sửa gì.

Dùng cho:
  r0-shadow logs            — liệt kê phiên
  r0-shadow logs <id>       — chi tiết một phiên
  r0-shadow dash            — bảng điều khiển tổng (kiểu opencode)
"""
from __future__ import annotations

import json
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from . import ui

SESS_DIR = Path.home() / ".mira" / "sessions"


def _fmt_time(ts: float) -> str:
    return time.strftime("%d/%m %H:%M", time.localtime(ts)) if ts else "—"


def _fmt_tok(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


def load_session_file(p: Path) -> dict:
    meta: dict = {}
    messages: list[dict] = []
    events: list[dict] = []
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except ValueError:
                continue
            t = o.get("type")
            if t == "meta":
                meta = o
            elif t == "message":
                messages.append(o)
            elif t == "event":
                events.append(o)
    except OSError:
        pass
    tok = meta.get("tokens") or {}
    tools: Counter = Counter()
    for e in events:
        name = e.get("tool") or e.get("name") or e.get("action")
        if name:
            tools[str(name)] += 1
    try:
        mtime = p.stat().st_mtime
    except OSError:
        mtime = 0.0
    return {
        "id": p.stem, "path": p, "mtime": mtime,
        "meta": meta, "messages": messages, "events": events,
        "model": meta.get("model") or "", "mode": meta.get("mode") or "",
        "turns": int(meta.get("turns") or 0),
        "cost": float(meta.get("cost_usd") or 0.0),
        "tok_in": int(tok.get("in") or 0), "tok_out": int(tok.get("out") or 0),
        "first_task": meta.get("first_task") or "", "tools": tools,
    }


def list_sessions(limit: int = 0) -> list[dict]:
    if not SESS_DIR.exists():
        return []
    try:
        files = sorted(SESS_DIR.glob("*.jsonl"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return []
    if limit:
        files = files[:limit]
    return [load_session_file(p) for p in files]


def totals(sessions: list[dict]) -> dict:
    tools: Counter = Counter()
    for s in sessions:
        tools.update(s["tools"])
    return {"n": len(sessions),
            "turns": sum(s["turns"] for s in sessions),
            "tok_in": sum(s["tok_in"] for s in sessions),
            "tok_out": sum(s["tok_out"] for s in sessions),
            "cost": sum(s["cost"] for s in sessions),
            "tools": tools}


# ------------------------------------------------------------------ hiển thị
def _session_row(s: dict) -> list[str]:
    tot = s["tok_in"] + s["tok_out"]
    return [s["id"], _fmt_time(s["mtime"]), s["model"] or "—",
            str(s["turns"] or ""), _fmt_tok(tot) if tot else "—",
            f"${s['cost']:.4f}" if s["cost"] else "—",
            (s["first_task"][:40] or "—")]


def render_list(sessions: list[dict]) -> None:
    if not sessions:
        ui.note("Chưa có phiên nào. Gõ frog để bắt đầu.", "info")
        return
    ui.table(["id", "lúc", "model", "lượt", "token", "$", "việc"],
             [_session_row(s) for s in sessions],
             ["l", "l", "l", "r", "r", "r", "l"])


def render_detail(s: dict) -> None:
    ui.section(f"phiên {s['id']}")
    ui.kv("lúc", _fmt_time(s["mtime"]))
    ui.kv("model", s["model"] or "—")
    ui.kv("chế độ", s["mode"] or "—")
    ui.kv("lượt model", s["turns"])
    ui.kv("token", f"{s['tok_in']} vào + {s['tok_out']} ra")
    ui.kv("chi phí", f"${s['cost']:.6f}" if s["cost"] else "—")
    ui.kv("việc đầu", s["first_task"] or "—")
    if s["tools"]:
        ui.section("công cụ đã gọi")
        for name, n in s["tools"].most_common():
            print(f"    {ui.c(name, 'accent')}  ×{n}")
    if s["events"]:
        ui.section("sự kiện")
        for e in s["events"]:
            desc = e.get("path") or e.get("cmd") or e.get("detail") or ""
            label = e.get("tool") or e.get("action") or e.get("type") or "?"
            ui.note(f"{label}  {str(desc)[:80]}", "ok" if e.get("ok", True) else "warn")
    if s["messages"]:
        ui.section("lượt gần đây")
        for m in s["messages"][-6:]:
            role = m.get("role", "?")
            text = m.get("content") or ""
            if isinstance(text, list):
                text = " ".join(str(b.get("text", "")) if isinstance(b, dict) else str(b)
                                for b in text)
            print(f"    {ui.c(role, 'accent', 'bold')}: {str(text)[:100]}")


def render_dashboard(limit: int = 8, run: str | None = "out") -> None:
    sess = list_sessions(limit)
    t = totals(list_sessions())
    ui.title("frog · bảng số")
    ui.hr()
    ui.kv("phiên", t["n"])
    ui.kv("lượt model", t["turns"])
    ui.kv("token", f"{_fmt_tok(t['tok_in'])} vào + {_fmt_tok(t['tok_out'])} ra")
    ui.kv("chi phí", f"${t['cost']:.4f}")
    ui.hr()
    ui.section("phiên gần đây")
    render_list(sess)
    if t["tools"]:
        ui.hr()
        ui.section("công cụ dùng nhiều")
        mx = max(t["tools"].values())
        for name, n in t["tools"].most_common(8):
            print(f"    {ui.c(f'{name:<10}', 'accent')} {ui.bar(n, mx, 18)} {n}")
    ui.hr()
    render_lab(run)


# --------------------------------------------------- số đo lường (lab) + nghĩa
# Ảnh chụp khi chưa có thư mục lần chạy nào (bản cài mới). Có run dir thì lấy số sống.
LAB_SNAPSHOT = [
    ("tác vụ đo", "320", "số tác vụ đem chạy thử trong lab"),
    ("phân bố làn", "106 / 164 / 50", "tác vụ rơi vào làn 0 / 1 / 2 (đội hình xử lý)"),
    ("giờ người mỗi tuần", "60,2 h", "công người phải duyệt, ở nhịp 250 tác vụ/tuần"),
    ("leo thang (VC)", "0,157", "tỉ lệ tác vụ bị đẩy lên làn đắt hơn"),
    ("bắt mã độc", "0,815", "bộ lọc nội dung bắt được bao nhiêu % ca có mã độc"),
    ("báo nhầm", "0,200", "tỉ lệ báo động trên ca lành (càng thấp càng tốt)"),
    ("độ trễ p50 / p95", "71,8s / 425,7s", "thời gian xử lý một tác vụ (trung vị / đuôi)"),
    ("chi phí mỗi làn (p50)", "$0,044 / $0,083 / $0,599", "USD mỗi tác vụ theo làn 0 / 1 / 2"),
    ("sổ cái", "$48,31", "tổng tiền model đã tiêu cho cả mẻ đo"),
    ("dò rẻ vs dò đắt", "$1,10 / 1.000 tác vụ", "dò từ khoá (miễn phí) vs model đọc — giá thật để chọn"),
]


def lab_rows(run: str | None = None) -> list[tuple[str, str, str]]:
    """Đọc số đo từ <run>/metrics.json; không có thì dùng ảnh chụp."""
    if not run:
        return LAB_SNAPSHOT
    p = Path(run) / "metrics.json"
    if not p.exists():
        return LAB_SNAPSHOT
    try:
        m = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return LAB_SNAPSHOT
    g = m.get
    ld = g("lane_distribution") or {}
    lat = g("latency_overall") or {}
    cb = g("cost_by_lane") or {}
    led = g("ledger") or {}
    ci = g("t1b_recall_on_missed_ci95") or []
    ci_s = f" [{ci[0]:.2f}–{ci[1]:.2f}]" if len(ci) == 2 else ""
    rows = [
        ("tác vụ đo", str(g("n", "—")), "số tác vụ đem chạy thử trong lab"),
        ("phân bố làn",
         f"{ld.get('0', '—')} / {ld.get('1', '—')} / {ld.get('2', '—')}",
         "tác vụ rơi vào làn 0 / 1 / 2 (đội hình xử lý)"),
        ("giờ người mỗi tuần", f"{g('audit_hours_per_week', 0):.1f} h",
         "công người phải duyệt, ở nhịp 250 tác vụ/tuần"),
        ("leo thang (VC)", f"{g('VC_escalate_rate', 0):.3f}",
         "tỉ lệ tác vụ bị đẩy lên làn đắt hơn"),
        ("bắt mã độc", f"{g('t1b_recall_on_missed', 0):.3f}{ci_s}",
         "bộ lọc nội dung bắt được bao nhiêu % ca có mã độc"),
        ("báo nhầm", f"{g('t1b_false_alarm_rate', 0):.3f}",
         "tỉ lệ báo động trên ca lành (càng thấp càng tốt)"),
        ("độ trễ p50 / p95",
         f"{lat.get('p50', 0):.1f}s / {lat.get('p95', 0):.1f}s",
         "thời gian xử lý một tác vụ (trung vị / đuôi)"),
        ("chi phí mỗi làn (p50)",
         " / ".join(f"${(cb.get(k) or {}).get('p50', 0):.3f}" for k in ("0", "1", "2")),
         "USD mỗi tác vụ theo làn 0 / 1 / 2"),
        ("sổ cái", f"${led.get('total_usd', 0):.2f}",
         "tổng tiền model đã tiêu cho cả mẻ đo"),
        ("dò rẻ vs dò đắt", "$1,10 / 1.000 tác vụ",
         "dò từ khoá (miễn phí) vs model đọc — giá thật để chọn"),
    ]
    return rows


def render_lab(run: str | None = None) -> None:
    rows = lab_rows(run)
    ui.section("số đo lường (lab) — con số của phần kiểm định thiết kế")
    ui.table(["chỉ số", "số", "nghĩa"],
             [[a, b, c] for a, b, c in rows], ["l", "r", "l"])
    ui.footer("lab = phần ĐO của dự án, không cần cho việc hằng ngày · "
              "xuất chi tiết: `r0-shadow export` · đo lại: `r0-shadow run`")


def cmd_logs(args) -> int:
    sid = getattr(args, "session", None)
    if sid:
        p = SESS_DIR / f"{sid}.jsonl"
        if not p.exists():
            ui.note(f"không có phiên {sid}", "bad")
            return 2
        render_detail(load_session_file(p))
        return 0
    ui.title("frog · nhật ký")
    render_list(list_sessions(getattr(args, "limit", 0)))
    return 0


def cmd_dash(args) -> int:
    render_dashboard()
    return 0


# --------------------------------------------------------- xuất dữ liệu chi tiết
def _md_report(what: str, run: str | None) -> str:
    sess = list_sessions()
    t = totals(sess)
    L: list[str] = ["# r0-shadow — dữ liệu chi tiết", "",
                    f"_xuất lúc {datetime.now():%Y-%m-%d %H:%M}_", ""]
    if what in ("all", "sessions"):
        L += [f"## Phiên agent ({t['n']})", "",
              "| id | lúc | model | lượt | token | $ | việc |",
              "|---|---|---|---|---|---|---|"]
        for s in sess:
            tot = s["tok_in"] + s["tok_out"]
            L.append(f"| {s['id']} | {_fmt_time(s['mtime'])} | {s['model'] or '—'} | "
                     f"{s['turns']} | {tot} | {s['cost']:.4f} | {s['first_task'][:60]} |")
        L += ["", f"**Tổng:** {t['n']} phiên · {t['turns']} lượt · "
                  f"{t['tok_in']}+{t['tok_out']} token · ${t['cost']:.4f}", "",
              "### Chi tiết từng phiên"]
        for s in sess:
            L += ["", f"#### {s['id']}",
                  f"- model: {s['model'] or '—'} · chế độ: {s['mode'] or '—'}",
                  f"- lượt: {s['turns']} · token: {s['tok_in']} vào, {s['tok_out']} ra · "
                  f"$ {s['cost']:.6f}",
                  f"- việc đầu: {s['first_task'] or '—'}"]
            if s["tools"]:
                L.append("- công cụ: " + ", ".join(f"{k} ×{v}" for k, v in s["tools"].most_common()))
            for e in s["events"][:40]:
                label = e.get("tool") or e.get("action") or e.get("type") or "?"
                desc = e.get("path") or e.get("cmd") or e.get("detail") or ""
                L.append(f"  - {label} {str(desc)[:80]}")
    if what in ("all", "lab"):
        L += ["", "## Số đo lường (lab)", "",
              "| chỉ số | số | nghĩa |", "|---|---|---|"]
        for a, b, cc in lab_rows(run):
            L.append(f"| {a} | {b} | {cc} |")
    return "\n".join(L) + "\n"


def _json_report(what: str, run: str | None) -> dict:
    sess = list_sessions()
    t = totals(sess)
    return {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "totals": {"sessions": t["n"], "turns": t["turns"],
                   "tok_in": t["tok_in"], "tok_out": t["tok_out"],
                   "cost_usd": round(t["cost"], 6)},
        "sessions": [{
            "id": s["id"], "mtime": _fmt_time(s["mtime"]), "model": s["model"],
            "mode": s["mode"], "turns": s["turns"],
            "tok_in": s["tok_in"], "tok_out": s["tok_out"],
            "cost_usd": round(s["cost"], 6), "first_task": s["first_task"],
            "tools": dict(s["tools"]), "events": s["events"],
        } for s in sess],
        "lab": [{"chi_so": a, "so": b, "nghia": c} for a, b, c in lab_rows(run)],
    }


def _csv_report() -> str:
    import csv
    import io
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "luc", "model", "che_do", "luot", "token_vao",
                "token_ra", "chi_phi_usd", "viec"])
    for s in list_sessions():
        w.writerow([s["id"], _fmt_time(s["mtime"]), s["model"], s["mode"],
                    s["turns"], s["tok_in"], s["tok_out"],
                    f"{s['cost']:.6f}", s["first_task"]])
    return buf.getvalue()


def export_report(what: str = "all", fmt: str = "md",
                  run: str | None = None, out: str | None = None) -> Path:
    stamp = datetime.now().strftime("%Y%m%d")
    if fmt == "md":
        content, default = _md_report(what, run), f"r0-shadow-export-{stamp}.md"
    elif fmt == "json":
        content, default = (json.dumps(_json_report(what, run), ensure_ascii=False, indent=2),
                            f"r0-shadow-export-{stamp}.json")
    elif fmt == "csv":
        content, default = _csv_report(), f"r0-shadow-sessions-{stamp}.csv"
    else:
        raise ValueError(f"định dạng lạ: {fmt}")
    p = Path(out or default)
    p.write_text(content, encoding="utf-8")
    return p


def cmd_export(args) -> int:
    p = export_report(what=getattr(args, "what", None) or "all",
                      fmt=getattr(args, "format", None) or "md",
                      run=getattr(args, "run", None),
                      out=getattr(args, "out", None))
    ui.note(f"đã ghi dữ liệu chi tiết: {p}", "ok")
    return 0
