"""Hợp đồng ý định: đổi goal, tiêu chí hoặc ràng buộc thì kế hoạch cũ hết hiệu lực."""
from __future__ import annotations


def _clean(items) -> list[str]:
    return [item.strip() for item in items if isinstance(item, str) and item.strip()]


def contract_diff(old: dict, new: dict) -> dict:
    """So hai brief đã đúng schema. Không gọi model."""
    old_goal = (old.get("goal") or "").strip()
    new_goal = (new.get("goal") or "").strip()
    old_criteria = _clean(old.get("acceptance_criteria") or [])
    new_criteria = _clean(new.get("acceptance_criteria") or [])
    old_limits = _clean(old.get("constraints") or [])
    new_limits = _clean(new.get("constraints") or [])
    added = [item for item in new_criteria if item not in old_criteria]
    removed = [item for item in old_criteria if item not in new_criteria]
    limits_changed = old_limits != new_limits
    goal_changed = old_goal != new_goal
    return {
        "goal_changed": goal_changed,
        "added_criteria": added,
        "removed_criteria": removed,
        "constraints_changed": limits_changed,
        "invalidates": goal_changed or bool(added) or bool(removed) or limits_changed,
    }
