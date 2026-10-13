"""Mỗi tiêu chí nghiệm thu phải có bằng chứng, không chỉ lời PASS."""
from __future__ import annotations

import re

_FILE = re.compile(r"[\w./\\-]+\.(?:py|txt|md|json|toml|ya?ml|csv)\b")


def judge_obligations(criteria: list[str], steps: list[dict],
                      evidence: dict | None) -> list[dict]:
    """proven khi verifier trích đúng câu, hoặc file nêu trong tiêu chí thực sự đổi."""
    quotes = []
    for step in steps:
        parsed = step.get("verdict_parsed") or {}
        for item in parsed.get("evidence") or []:
            if isinstance(item, str):
                quotes.append(item)
    changed = set((evidence or {}).get("changed") or [])
    rows = []
    for raw in criteria:
        text = (raw or "").strip()
        named = _FILE.findall(text.replace("\\", "/"))
        if any(text and text in quote for quote in quotes):
            state, reason = "proven", "verifier trích đúng tiêu chí"
        elif named and all(name in changed for name in named):
            state, reason = "proven", "file trong tiêu chí khác bản nguồn"
        else:
            state, reason = "unproven", "chưa có trích dẫn hoặc file đổi khớp tiêu chí"
        rows.append({"criterion": text, "state": state, "reason": reason})
    return rows


def unproven(rows: list[dict]) -> list[dict]:
    return [row for row in rows if row["state"] != "proven"]
