"""So bang chung va hop dong: ban c8461bb va ban hien tai, cung mot file dap an.

Khong goi model. Dap an nam trong eval/overnight/scenarios.jsonl va da bam
trong scenarios.sha256 truoc khi cham diem.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import shlex
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ROOT / "eval" / "overnight" / "scenarios.jsonl"
FROZEN = ROOT / "eval" / "overnight" / "scenarios.sha256"


def _baseline(criteria, steps, evidence):
    """Ban sao judge o c8461bb. Trich dan hoac file doi la proven."""
    import re
    file_re = re.compile(r"[\w./\\-]+\.(?:py|txt|md|json|toml|ya?ml|csv)\b")
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
        named = file_re.findall(text.replace("\\", "/"))
        if any(text and text in quote for quote in quotes):
            state = "proven"
        elif named and all(name in changed for name in named):
            state = "proven"
        else:
            state = "unproven"
        rows.append(state)
    return rows


def _fill(text: str, py: str) -> str:
    return text.replace("{py}", shlex.quote(py))


def _evidence(row, py: str):
    from mira.obligations import judge_obligations
    criteria = [_fill(item, py) for item in row["criteria"]]
    quotes = [_fill(item, py) for item in row.get("quotes") or []]
    steps = [{"verdict_parsed": {"evidence": quotes}}]
    evidence = {"changed": row.get("changed") or []}
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        current = [
            item["state"] for item in judge_obligations(criteria, steps, evidence, cwd=cwd)
        ]
        marker = cwd / "marker.txt"
        marker_ok = not row.get("marker_absent") or not marker.exists()
    base = _baseline(criteria, steps, evidence)
    return current, base, marker_ok


def _contract(row):
    from mira.contract import contract_diff
    from mira.intake import brief_hash
    diff = contract_diff(row["old"], row["new"])
    same = brief_hash(row["old"]) == brief_hash(row["new"])
    line_ok = True
    if row.get("expect_line"):
        line_ok = row["expect_line"] in diff["lines"]
    return diff["invalidates"], (not same), line_ok


def _brief():
    return {
        "goal": "tom tat",
        "deliverables": ["mot doan"],
        "acceptance_criteria": ["co nguon"],
        "constraints": [],
        "assumptions": [],
        "questions": [],
        "per_role_hints": {"planner": "", "worker": "", "verifier": ""},
    }


def _resume(row, py: str):
    from mira.providers import ProviderError
    from mira.team import cmd_team, write_checkpoint
    calls = []

    class Talk:
        def __init__(self, *_a, **_k):
            self.name = "fake"
            self.attempts = 1

        def available(self):
            return True

        def call(self, _system, _user):
            if row["change"] == "provider-error":
                raise ProviderError("may gia tu choi")
            calls.append("x")
            return "xong", {"in": 2, "out": 1}

    def args(root: Path, **extra):
        base = dict(
            resume=None, task="tom tat tai lieu cong khai", brief=None,
            provider="anthropic", model=None, base_url=None, api_key="k",
            max_tokens=64, oracle="off", require_evidence=False,
            surface="read_only", labels="public", records=10, dollars=0.0,
            reversibility="C1", output_type="free_string", dry_run=False,
            intake="off", approve=True, price_in="1000,0", workers=1,
            sub_depth=0, out=str(root / "out"), clarify_max=0,
        )
        base.update(extra)
        return SimpleNamespace(**base)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        prev = os.getcwd()
        os.chdir(root)
        try:
            if row["change"] == "provider-error":
                path = root / "brief.json"
                brief = _brief()
                brief["acceptance_criteria"] = [
                    f'check: {py} -c "import sys; raise SystemExit(0)"'
                ]
                path.write_text(json.dumps(brief), encoding="utf-8")
                buf = io.StringIO()
                with redirect_stdout(buf), patch("mira.team.provider_for", Talk):
                    code = cmd_team(args(root, brief=str(path), require_evidence=True))
                runs = list((root / ".mira" / "runs").glob("*/checkpoint.json"))
                data = json.loads(runs[0].read_text(encoding="utf-8"))
                return {
                    "exit": code,
                    "calls": len(calls),
                    "status": data["status"],
                    "usd": data["ledger"]["total_usd"],
                }
            brief = _brief()
            if row["change"] == "saved-gate":
                brief["acceptance_criteria"] = [
                    f'check: {py} -c "import sys; raise SystemExit(2)"'
                ]
            write_checkpoint(root, {
                "id": "run-eval", "version": 1, "next_index": 1,
                "task": "tom tat tai lieu cong khai",
                "steps": [{"role": "worker", "text": "xong", "model": "m",
                           "usage": {"in": 2, "out": 1}, "usd": 0.01, "seconds": 0.0}],
                "ledger": {"rows": [], "total_usd": 0.0, "total_in": 0,
                           "total_out": 0, "subagent_runs": 0},
                "staging": None, "status": "ok", "fail_reason": None,
                "brief": brief, "brief_hash": "cu",
                "hints": {"surface": "read_only", "labels": ["public"], "records": 10,
                          "dollars": 0, "reversibility": "C1",
                          "output_type": "free_string"},
                "workers": 1,
                "require_evidence": row["change"] == "saved-gate",
            })
            brief_arg = None
            if row["change"] == "assumptions":
                new = json.loads(json.dumps(brief))
                new["assumptions"] = ["tai lieu nam o thu muc nay"]
                path = root / "new.json"
                path.write_text(json.dumps(new), encoding="utf-8")
                brief_arg = str(path)
            buf = io.StringIO()
            with redirect_stdout(buf), patch("mira.team.provider_for", Talk):
                code = cmd_team(args(
                    root, resume="run-eval", task=None, brief=brief_arg,
                    require_evidence=False))
            return {"exit": code, "calls": len(calls), "text": buf.getvalue()}
        finally:
            os.chdir(prev)


def main() -> int:
    raw = SCENARIOS.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    frozen = FROZEN.read_text(encoding="utf-8").strip()
    print(f"frozen {frozen}")
    print(f"file   {digest}")
    if digest != frozen:
        print("dap an doi sau khi dong bang — khong cham")
        return 2
    py = sys.executable
    rows = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    false_deliver = 0
    false_block = 0
    current_bad = []
    for row in rows:
        if row["group"] == "evidence":
            current, base, marker_ok = _evidence(row, py)
            if current != row["expect_current"] or not marker_ok:
                current_bad.append((row["id"], current, marker_ok))
            for got, want in zip(base, row["expect_current"]):
                if got == "proven" and want != "proven":
                    false_deliver += 1
                if got != "proven" and want == "proven":
                    false_block += 1
            if base != row["expect_baseline"]:
                current_bad.append((row["id"] + ":baseline", base, True))
        elif row["group"] == "contract":
            invalidates, hash_diff, line_ok = _contract(row)
            if invalidates != row["expect_invalidates"] or not line_ok:
                current_bad.append((row["id"], invalidates, line_ok))
            if "expect_hash_diff" in row and hash_diff != row["expect_hash_diff"]:
                current_bad.append((row["id"] + ":hash", hash_diff, True))
        else:
            got = _resume(row, py)
            if got["exit"] != row["expect_exit"]:
                current_bad.append((row["id"], got, True))
            if "expect_calls" in row and got["calls"] != row["expect_calls"]:
                current_bad.append((row["id"] + ":calls", got["calls"], True))
            if "expect_status" in row and got.get("status") != row["expect_status"]:
                current_bad.append((row["id"] + ":status", got.get("status"), True))
            if "expect_usd" in row and got.get("usd") != row["expect_usd"]:
                current_bad.append((row["id"] + ":usd", got.get("usd"), True))
    print(f"scenarios {len(rows)}")
    print(f"baseline_false_deliver {false_deliver}")
    print(f"baseline_false_block {false_block}")
    print(f"current_mismatch {len(current_bad)}")
    for item in current_bad:
        print("mismatch", item)
    print("note fixture harness, khong phai diem model that")
    return 1 if current_bad else 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    raise SystemExit(main())
