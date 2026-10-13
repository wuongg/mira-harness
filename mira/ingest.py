"""Nạp trace team vào 16 chỉ số. Không gọi model. Không bịa số 0 khi thiếu trường."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SIXTEEN = (
    "D1_compress_rate",
    "D2_compress_rate",
    "D3_stop_rate",
    "D4_violation_rate",
    "lane_distribution",
    "t1b_recall_on_missed",
    "t1b_precision",
    "t1b_false_alarm_rate",
    "VC_escalate_rate",
    "audit_hours_per_week",
    "oracle_verifier",
    "latency_overall",
    "labeled_taskset",
    "capability_policy",
    "shadow",
    "ledger",
)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict]:
    rows = []
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _is_shadow_row(row: dict) -> bool:
    return isinstance(row, dict) and "guards" in row and "truth" in row


def _is_team_result(obj: Any) -> bool:
    return isinstance(obj, dict) and "steps" in obj and "ledger" in obj


def _is_team_chain(rows: list[dict]) -> bool:
    if not rows:
        return False
    head = rows[0]
    return isinstance(head, dict) and head.get("kind") == "header" and "plan_hash" in head


def metrics_from_team(result: dict, *, wrote_disk: bool) -> dict[str, Any]:
    """Mười sáu khóa. Thiếu trường thì null, không điền 0."""
    plan = result.get("plan") or {}
    lane = plan.get("lane")
    steps = result.get("steps") or []
    ledger = result.get("ledger") or {}
    seconds = [s["seconds"] for s in steps if isinstance(s.get("seconds"), (int, float))]
    acted = result.get("status") == "ok" and (wrote_disk or bool(result.get("promoted")))
    latency = None
    if seconds:
        total = round(sum(seconds), 4)
        latency = {"p50": total, "p95": total}
    out: dict[str, Any] = {key: None for key in SIXTEEN}
    out["data_source"] = "real"
    out["n"] = 1
    if lane is not None:
        out["lane_distribution"] = {str(lane): 1}
        out["VC_escalate_rate"] = 1.0 if lane == 2 else 0.0
    out["oracle_verifier"] = {
        "verifier_verdict": result.get("verifier_verdict"),
        "oracle_score": result.get("oracle_score"),
    }
    out["latency_overall"] = latency
    out["labeled_taskset"] = {
        "n": 1,
        "label_source": "real",
        "status": "không có nhãn người và không có nhãn synthetic",
    }
    if plan.get("capability") is not None:
        out["capability_policy"] = plan.get("capability")
    out["shadow"] = {"action_taken": 1 if acted else 0,
                     "note": "trace team, không phải shadow"}
    total = ledger.get("total_usd")
    out["ledger"] = {"total_usd": total} if total is not None else None
    return out


def _result_from_chain(rows: list[dict]) -> dict:
    steps = [row for row in rows if row.get("role")]
    return {"steps": steps, "ledger": {}, "plan": {}, "status": None}


def ingest_dir(directory: Path) -> int:
    directory = Path(directory)
    metrics_path = directory / "metrics.json"
    chain_path = directory / "trace.jsonl"
    team_path = directory / "trace.json"
    chain = _jsonl(chain_path) if chain_path.is_file() else []
    shadow = bool(chain) and all(_is_shadow_row(row) for row in chain)
    team_obj = _read_json(team_path) if team_path.is_file() else None
    team = _is_team_result(team_obj) or _is_team_chain(chain)
    if shadow and team:
        print("trace shadow và trace team cùng thư mục, không ghi")
        return 2
    if shadow:
        print("đây là trace shadow, không ghi đè nhãn synthetic")
        return 2
    if metrics_path.is_file() and not team:
        try:
            existing = _read_json(metrics_path)
        except (OSError, json.JSONDecodeError):
            existing = {}
        label = str((existing.get("labeled_taskset") or {}).get("label_source") or "")
        if "synthetic" in label.lower() or existing.get("data_source") == "synthetic":
            print("đây là trace shadow, không ghi đè nhãn synthetic")
            return 2
    if not team:
        print("không thấy trace team")
        return 2
    if not isinstance(team_obj, dict):
        team_obj = _result_from_chain(chain)
    wrote = (directory / "result.md").is_file()
    metrics = metrics_from_team(team_obj, wrote_disk=wrote)
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
    print("nguồn dữ liệu: real")
    return 0
