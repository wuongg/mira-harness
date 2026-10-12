"""Chế độ gán nhãn NGƯỜI.

Vì sao phải tách riêng:
  * Phiếu gán nhãn KHÔNG được chứa `truth` — nếu người gán nhìn thấy nhãn tổng
    hợp thì nhãn người trở thành bản sao của nó và không đo được gì.
  * `task_id` phải KHÔNG tương quan với tầng, nếu không người gán suy ra tầng
    từ số thứ tự. `tasks.build_tasks()` đã xáo trộn trước khi đánh id.
  * Người gán chỉ thấy thứ hệ thống THẬT SỰ thấy: yêu cầu + nhãn nguồn + quy mô.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

FIELDS = ["task_id", "request", "tool_surface", "data_labels", "untrusted_marker",
          "content_kind", "content", "output_type", "records", "dollars",
          "human_injection", "human_confidence", "human_note"]


def export_labels(tasks: list[Any], path: str | Path) -> Path:
    """Xuất phiếu gán nhãn. KHÔNG chứa truth. Cột cần điền để trống.

    PHẢI xếp theo `task_id`, không theo thứ tự tầng. `load_tasks()` trả về theo
    nhóm tầng, nên nếu xuất nguyên thứ tự đó thì người gán đọc 70 dòng cùng tầng
    liền nhau và suy ra tầng — id có xáo cũng vô ích.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(FIELDS)
        for t in sorted(tasks, key=lambda x: x.id):
            o = t.observable
            w.writerow([t.id, t.request, o["tool_surface"],
                        "|".join(o["data_labels"]),
                        "yes" if o["untrusted_content"] else "no",
                        o.get("content_kind", ""), o.get("content", ""),
                        o["output_type"], o["records"], o["dollars"], "", "", ""])
    return path


def load_labels(path: str | Path) -> dict[str, bool]:
    """Đọc phiếu đã điền. Ô trống -> bỏ qua (không đoán hộ)."""
    out: dict[str, bool] = {}
    with Path(path).open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            v = (row.get("human_injection") or "").strip().lower()
            if v in ("1", "true", "yes", "y", "có", "co", "x"):
                out[row["task_id"]] = True
            elif v in ("0", "false", "no", "n", "không", "khong", ""):
                if v:
                    out[row["task_id"]] = False
    return out


def label_stats(tasks: list[Any], labels: dict[str, bool]) -> dict[str, Any]:
    """So nhãn NGƯỜI với nhãn NGUỒN và với nhãn tổng hợp (chỉ để chẩn đoán)."""
    by_id = {t.id: t for t in tasks}
    n = len(labels)
    if not n:
        return {"n": 0, "note": "phiếu trống — chưa có nhãn người"}
    human_true = sum(1 for v in labels.values() if v)
    source_flag = sum(1 for k in labels if by_id[k].observable["untrusted_content"])
    agree_source = sum(1 for k, v in labels.items()
                       if bool(by_id[k].observable["untrusted_content"]) == v)
    agree_synth = sum(1 for k, v in labels.items() if by_id[k].truth["injection_present"] == v)
    return {
        "n": n,
        "human_positive": human_true,
        "human_positive_rate": round(human_true / n, 4),
        "source_flag_positive": source_flag,
        "agree_with_source_flag": round(agree_source / n, 4),
        "agree_with_synthetic_truth": round(agree_synth / n, 4),
        "human_catches_more_than_source": human_true - sum(
            1 for k, v in labels.items()
            if v and not by_id[k].observable["untrusted_content"]),
        "note": "agree_with_synthetic_truth chỉ để chẩn đoán — KHÔNG phải thước đo chất lượng nhãn người",
    }


def sheet_labelability(tasks: list[Any]) -> dict[str, Any]:
    """Mục tiêu cần gán có SUY RA ĐƯỢC từ cột hiển thị trên phiếu không?

    Nếu trong mỗi nhóm (untrusted_marker, tool_surface) mà nhãn nhận cả hai giá trị
    thì không ai — người hay máy — suy ra được nhãn từ phiếu. Đây là điều kiện tiên
    quyết để một bộ nhãn có nghĩa; thiếu nó thì gán bao nhiêu cũng vô ích.
    """
    import collections
    groups: dict[tuple, list] = collections.defaultdict(list)
    for t in tasks:
        groups[(t.observable["untrusted_content"], t.observable["tool_surface"])].append(
            bool(t.truth["injection_present"]))
    non_det = {k: (len(v), sum(v)) for k, v in groups.items() if len(set(v)) > 1}
    with_content = sum(1 for t in tasks if t.observable.get("content"))
    full = with_content == len(tasks)
    if full and non_det:
        verdict = ("nội dung thật ĐÃ có trên phiếu ⇒ nhãn nay TRẢ LỜI ĐƯỢC bằng cách đọc; "
                   "nhưng vẫn KHÔNG suy ra được từ cột metadata — nên phải đọc, không đoán theo nhãn nguồn")
    elif not non_det:
        verdict = "suy ra được từ metadata"
    else:
        verdict = "thiếu nội dung thật — nhãn vẫn chỉ là phỏng đoán"
    return {
        "n_tasks": len(tasks),
        "n_groups": len(groups),
        "n_groups_non_determinable": len(non_det),
        "determinable": len(non_det) == 0,
        "content_on_sheet": full,
        "n_with_content": with_content,
        "groups": {f"marker={k[0]},surface={k[1]}": {"n": v[0], "inj": v[1]}
                   for k, v in sorted(non_det.items(), key=lambda kv: str(kv[0]))},
        "verdict": verdict,
    }


def triage(tasks: list[Any], trace: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Xếp hạng tác vụ theo MỨC ĐÁNG GÁN NHÃN, chỉ dùng cột hiển thị (không dùng truth).

    Lý do từng hạng:
      recall   — marker=no & bề mặt rủi ro cao: nơi 'bỏ sót' nguy hiểm có thể nấp
      precision— marker=yes: cần mẫu để đo báo động thừa
      low      — còn lại: gần như chắc chắn không đổi kết luận
    """
    rows: list[dict[str, Any]] = []
    by_id = {r["id"]: r for r in (trace or [])}
    for t in tasks:
        o = t.observable
        high_risk = o["tool_surface"] in ("write_external", "egress_new")
        if not o["untrusted_content"] and high_risk:
            rank, why = 1, "recall — marker=no & bề mặt rủi ro cao"
        elif not o["untrusted_content"]:
            rank, why = 3, "recall phụ — marker=no, bề mặt thấp"
        else:
            rank, why = 2, "precision — marker=yes, đo báo động thừa"
        r = by_id.get(t.id, {})
        rows.append({"task_id": t.id, "rank": rank, "why": why,
                     "tool_surface": o["tool_surface"],
                     "untrusted_marker": "yes" if o["untrusted_content"] else "no",
                     "lane_final": r.get("lane_final"),
                     "t1b_conf": (r.get("classifier") or {}).get("confidence")})
    rows.sort(key=lambda x: (x["rank"], x["task_id"]))
    return rows


def write_triage(rows: list[dict[str, Any]], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["task_id", "rank", "why", "tool_surface", "untrusted_marker",
              "lane_final", "t1b_conf"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})
    return path


def apply_labels(trace: list[dict[str, Any]], labels: dict[str, bool]) -> int:
    """Ghi đè `truth.injection_present` bằng nhãn NGƯỜI cho mọi chỉ số chấm điểm."""
    n = 0
    for r in trace:
        if r["id"] in labels:
            r["truth"]["synthetic_injection_present"] = r["truth"]["injection_present"]
            r["truth"]["injection_present"] = labels[r["id"]]
            r["truth"]["label_source"] = "human"
            n += 1
    return n
