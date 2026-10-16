"""Hợp đồng ý định: đổi goal, tiêu chí hoặc ràng buộc thì kế hoạch cũ hết hiệu lực."""
from __future__ import annotations

import json


def _clean(items) -> list[str]:
    return [item.strip() for item in items if isinstance(item, str) and item.strip()]


def _criterion_token(item) -> str | None:
    """Giữ object trong diff. Không rút về chuỗi rồi bỏ phần còn lại."""
    if isinstance(item, str):
        text = item.strip()
        return text or None
    if isinstance(item, dict):
        return json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if item is None:
        return None
    return json.dumps(item, ensure_ascii=False, default=str)


def _criterion_tokens(items) -> list[str]:
    out = []
    for item in items or []:
        token = _criterion_token(item)
        if token:
            out.append(token)
    return out


def contract_diff(old: dict, new: dict) -> dict:
    """So hai brief đã đúng schema. Không gọi model."""
    old_goal = (old.get("goal") or "").strip()
    new_goal = (new.get("goal") or "").strip()
    old_criteria = _criterion_tokens(old.get("acceptance_criteria") or [])
    new_criteria = _criterion_tokens(new.get("acceptance_criteria") or [])
    old_limits = _clean(old.get("constraints") or [])
    new_limits = _clean(new.get("constraints") or [])
    old_done = _clean(old.get("deliverables") or [])
    new_done = _clean(new.get("deliverables") or [])
    added = [item for item in new_criteria if item not in old_criteria]
    removed = [item for item in old_criteria if item not in new_criteria]
    added_done = [item for item in new_done if item not in old_done]
    removed_done = [item for item in old_done if item not in new_done]
    limits_changed = old_limits != new_limits
    goal_changed = old_goal != new_goal
    lines = []
    if goal_changed:
        lines.append(f"goal: {old_goal} → {new_goal}")
    for item in added_done:
        lines.append(f"deliverable thêm: {item}")
    for item in removed_done:
        lines.append(f"deliverable bớt: {item}")
    for item in added:
        lines.append(f"tiêu chí thêm: {item}")
    for item in removed:
        lines.append(f"tiêu chí bớt: {item}")
    if limits_changed:
        lines.append("constraints đã đổi")
    invalidates = bool(lines)
    # Chưa có liên kết tiêu chí → bước. Đổi tiêu chí thì hủy cả run.
    return {
        "goal_changed": goal_changed,
        "added_criteria": added,
        "removed_criteria": removed,
        "added_deliverables": added_done,
        "removed_deliverables": removed_done,
        "constraints_changed": limits_changed,
        "invalidates": invalidates,
        "scope": "run" if invalidates else "",
        "lines": lines,
    }
