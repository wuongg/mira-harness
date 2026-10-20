"""Tuyển người theo đơn: phân tích → đề cử → phỏng vấn → chỉ PASS mới vào đội.

Không giới hạn nghề theo danh mục cố định. Trần CANDIDATE_MAX chỉ chống bùng nổ
quota (một intake lỗi đề cử hàng trăm vai), không phải luật nghiệp vụ "chỉ 4 vai lạ".
"""
from __future__ import annotations

import json
import os
import re
from typing import Callable

from .roles import CANDIDATE_MAX, KINDS, POOL, _NAME

INTERVIEW_SYSTEM = (
    "Bạn là người PHỎNG VẤN tuyển vào đội làm đúng một đơn của khách. "
    "Chỉ trả một object JSON, không chữ nào khác, khóa: verdict, reasons, confidence. "
    "verdict chỉ PASS hoặc FAIL. "
    "PASS khi: việc khớp nhu cầu đơn, kind (manage|make|review|handoff) đúng, "
    "task cụ thể, không trùng vai đã có cùng một việc. "
    "FAIL khi: mơ hồ, thừa so với đơn, sai kind, tên không phải nghề thật, "
    "hoặc không giúp hoàn thành đơn. reasons là danh sách ngắn tiếng Việt."
)

_JSON = re.compile(r"\{.*\}", re.S)


def _parse_verdict(text: str) -> dict:
    raw = (text or "").strip()
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        found = _JSON.search(raw)
        if not found:
            return {"verdict": "FAIL", "reasons": ["phỏng vấn không trả JSON"], "confidence": 0.0}
        try:
            obj = json.loads(found.group(0))
        except json.JSONDecodeError:
            return {"verdict": "FAIL", "reasons": ["phỏng vấn JSON hỏng"], "confidence": 0.0}
    verdict = str(obj.get("verdict") or "").strip().upper()
    if verdict not in ("PASS", "FAIL"):
        verdict = "FAIL"
    reasons = obj.get("reasons") if isinstance(obj.get("reasons"), list) else []
    reasons = [str(r).strip() for r in reasons if str(r).strip()] or ["không nêu lý do"]
    try:
        conf = float(obj.get("confidence"))
    except (TypeError, ValueError):
        conf = 0.0
    return {"verdict": verdict, "reasons": reasons, "confidence": max(0.0, min(1.0, conf))}


def _candidate_ok(item: dict) -> bool:
    name = str(item.get("role") or "").strip()
    kind = str(item.get("kind") or "").strip()
    task = str(item.get("task") or "").strip()
    if name in POOL:
        return True  # catalog: settle điền việc nếu thiếu
    return bool(_NAME.match(name) and kind in KINDS and task)


def interview_roster(
    order: str,
    proposal: dict | None,
    *,
    ask: Callable[[str, str], str],
    skip: bool | None = None,
) -> tuple[dict | None, list[dict], list[str]]:
    """Phỏng vấn từng ứng viên intake đề cử.

    ask(system, user) -> text model.
    Trả (proposal đã lọc PASS, danh sách FAIL, ghi chú).
    """
    if not isinstance(proposal, dict):
        return proposal, [], []
    if skip is None:
        skip = os.environ.get("FROG_NO_INTERVIEW", "").strip().lower() in ("1", "true", "yes")
    hired_in = [x for x in (proposal.get("hired") or []) if isinstance(x, dict)]
    notes: list[str] = []
    if len(hired_in) > CANDIDATE_MAX:
        notes.append(
            f"chống bùng nổ: intake đề cử {len(hired_in)} ứng viên, "
            f"chỉ phỏng vấn {CANDIDATE_MAX} người đầu")
        hired_in = hired_in[:CANDIDATE_MAX]

    passed: list[dict] = []
    rejected: list[dict] = []
    seen: set[str] = set()

    for item in hired_in:
        name = str(item.get("role") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        if not _candidate_ok(item):
            rejected.append({
                "role": name or "?", "reason": "hồ sơ thiếu kind/task hợp lệ — không phỏng vấn",
                "origin": "phỏng vấn", "verdict": "FAIL",
            })
            continue
        if skip:
            row = dict(item)
            row["interview"] = {"verdict": "PASS", "reasons": ["bỏ phỏng vấn (FROG_NO_INTERVIEW)"],
                                "confidence": 1.0}
            passed.append(row)
            continue
        catalog = POOL.get(name)
        kind = str(item.get("kind") or (catalog.kind if catalog else "")).strip()
        title = str(item.get("title") or (catalog.title if catalog else name.replace("_", " ")))
        task = str(item.get("task") or "").strip() or (
            catalog.duty if catalog else "(chưa ghi việc cụ thể)")
        reason = str(item.get("reason") or "").strip()
        user = (
            f"ĐƠN CỦA KHÁCH:\n{order}\n\n"
            f"ỨNG VIÊN:\n- mã vai: {name}\n- nghề: {title}\n- loại: {kind}\n"
            f"- việc đề xuất: {task}\n- lý do tuyển: {reason or '(không có)'}\n\n"
            f"Các vai đã PASS trước đó: {', '.join(r['role'] for r in passed) or '(chưa ai)'}\n"
            "Quyết định PASS hoặc FAIL."
        )
        try:
            text = ask(INTERVIEW_SYSTEM, user)
        except Exception as exc:  # noqa: BLE001 — lỗi gọi → FAIL, không kéo đổ cả đội
            rejected.append({
                "role": name, "reason": f"phỏng vấn lỗi: {exc}", "origin": "phỏng vấn",
                "verdict": "FAIL",
            })
            continue
        verdict = _parse_verdict(text)
        if verdict["verdict"] == "PASS":
            row = dict(item)
            row["interview"] = verdict
            if not str(row.get("reason") or "").strip():
                row["reason"] = "pass phỏng vấn"
            else:
                row["reason"] = f"{row['reason']} · pass phỏng vấn"
            passed.append(row)
        else:
            why = "; ".join(verdict["reasons"])
            rejected.append({
                "role": name, "reason": f"phỏng vấn không đạt: {why}",
                "origin": "phỏng vấn", "verdict": "FAIL",
                "confidence": verdict.get("confidence"),
            })

    out = dict(proposal)
    out["hired"] = passed
    considered = [c for c in (proposal.get("considered") or []) if isinstance(c, dict)]
    for row in rejected:
        considered.append({"role": row["role"], "reason": row["reason"], "origin": "phỏng vấn"})
    out["considered"] = considered
    return out, rejected, notes
