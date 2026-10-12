"""Màn thống kê — dựng bảng điều khiển từ số đo R0 shadow.

Đọc `metrics.json` + `trace.jsonl` của một lần chạy và bày ra theo phong cách tối giản:
con số lớn, lưới chấm, mấy cột tóm tắt. Chỉ ĐỌC số đã đo — không tính lại gì mới,
để bảng này không bao giờ lệch khỏi báo cáo.
"""
from __future__ import annotations

import json
import time
from collections import defaultdict
from pathlib import Path

from . import ui


def _load(run: str) -> tuple[dict, list[dict], Path]:
    d = Path(run)
    mf, tf = d / "metrics.json", d / "trace.jsonl"
    if not mf.exists():
        raise FileNotFoundError(
            f"không thấy {mf} — chạy `r0-shadow run --out {run}` trước")
    metrics = json.loads(mf.read_text(encoding="utf-8"))
    trace: list[dict] = []
    if tf.exists():
        for line in tf.read_text(encoding="utf-8").splitlines():
            if line.strip():
                trace.append(json.loads(line))
    return metrics, trace, d


HEADLINES = {
    "cost": ("tổng chi phí", lambda m, t: f"${m.get('ledger', {}).get('total_usd', 0):.2f}"),
    "tasks": ("tác vụ", lambda m, t: str(m.get("n", len(t)))),
    "audit": ("giờ audit / tuần", lambda m, t: f"{m.get('audit_hours_per_week', 0):.1f}h"),
    "vc": ("tỉ lệ escalate V-C", lambda m, t: f"{100 * m.get('VC_escalate_rate', 0):.1f}%"),
    "latency": ("độ trễ p95", lambda m, t: f"{m.get('latency_overall', {}).get('p95', 0):.0f}s"),
}


def _lane_cells(trace: list[dict]) -> tuple[list[list[int]], list[str], list[str]]:
    """Lưới 8 tầng × N cột; mỗi ô là làn của tác vụ (0..2) -> cường độ."""
    if not trace:
        return [], [], []
    by: dict[str, list[int]] = defaultdict(list)
    for r in trace:
        by[r.get("stratum", "?")].append(int(r.get("lane_final", 0)))
    strata = sorted(by)
    width = max(len(v) for v in by.values())
    cells = []
    for s in strata:
        row = [int(by[s][i]) if i < len(by[s]) else 0 for i in range(width)]
        cells.append(row)
    return cells, strata, []


def _cols(n: int, step: int = 10) -> list[str]:
    return [str(i + 1) if (i % step == 0) else "" for i in range(n)]


def render(run: str, metric: str = "cost") -> None:
    metrics, trace, d = _load(run)
    label, fn = HEADLINES.get(metric, HEADLINES["cost"])
    w = min(ui.term_width(), 96)

    # ---- đầu trang ----
    print()
    print("  " + ui.c("r0-shadow", "bright", "bold") + ui.c(" / ", "faint")
          + ui.c("stats", "dim")
          + ui.c(f"    {d.name}", "faint").rjust(max(0, w - 24)))
    print(ui.c("  " + "─" * (w - 4), "faint"))

    # ---- con số lớn ----
    print()
    ui.print_big(fn(metrics, trace), "bright", indent=4)
    print(" " * 4 + ui.c(label, "dim"))
    print()

    # ---- lưới chấm: làn theo tầng ----
    cells, strata, _ = _lane_cells(trace)
    if cells:
        print("  " + ui.c("làn theo tầng tác vụ", "dim")
              + ui.c(f"   {len(strata)} tầng × {len(cells[0])} tác vụ", "faint"))
        print()
        ui.heat(cells, row_labels=strata, indent=2)
        print()
        ui.legend_heat(("làn 0", "làn 1", "làn 2"), indent=2)
        print()

    # ---- ba cột tóm tắt ----
    lanes = metrics.get("lane_distribution", {})
    l0, l1, l2 = lanes.get("0", 0), lanes.get("1", 0), lanes.get("2", 0)
    sh = metrics.get("shadow", {})
    cols = [
        (str(l0), "làn 0"),
        (str(l1), "làn 1"),
        (str(l2), "làn 2"),
        (f"{metrics.get('audit_hours_per_week', 0):.1f}h", "audit / tuần"),
        (str(sh.get("action_taken", 0)), "hành động thật"),
    ]
    print(ui.c("  " + "─" * (w - 4), "faint"))
    print()
    seg = (w - 6) // len(cols)
    line1 = line2 = "  "
    for v, k in cols:
        line1 += ui.c(str(v).center(seg), "bright", "bold")
        line2 += ui.c(k.center(seg), "faint")
    print(line1)
    print(line2)

    # ---- chân trang ----
    print()
    print(ui.c("  " + "─" * (w - 4), "faint"))
    vc = metrics.get("VC_escalate_rate", 0)
    dual = metrics.get("dual_approval_rate", 0)
    print("  " + ui.c(f"VC escalate {ui.pct(vc)}  ·  2 người duyệt {ui.pct(dual)}  ·  "
                      f"fail-closed {sh.get('note', '')[:0] or '100%'}", "faint"))
    ui.footer(f"r0-shadow · {time.strftime('%Y-%m-%d %H:%M')} · nguồn {d}", indent=2)


def cmd_stats(args) -> int:
    try:
        render(args.run, args.metric)
    except FileNotFoundError as e:
        ui.note(str(e), "bad")
        return 2
    except Exception as e:                       # noqa: BLE001 — báo gọn, không traceback
        ui.note(f"không dựng được thống kê: {type(e).__name__}: {e}", "bad")
        return 1
    return 0
