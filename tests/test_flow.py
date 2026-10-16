"""Một lượt: intake, check, ngắt, đổi brief, provider lỗi. Không gọi mạng."""
from __future__ import annotations

import io
import json
import os
import shlex
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from frog.intake import run_intake
from frog.providers import ProviderError
from frog.team import Ledger, checkpoint_path, cmd_team, write_checkpoint


def _brief(criteria):
    return {
        "goal": "tóm tắt",
        "deliverables": ["một đoạn"],
        "acceptance_criteria": criteria,
        "constraints": [],
        "assumptions": [],
        "questions": [],
        "per_role_hints": {"planner": "", "worker": "", "verifier": ""},
    }


class _Talk:
    calls: list[str] = []
    fail = False

    def __init__(self, *_a, **_k):
        self.name = "fake"
        self.attempts = 1

    def available(self):
        return True

    def call(self, system, _user):
        if _Talk.fail:
            raise ProviderError("máy giả từ chối")
        kind = "verifier" if "VERIFIER" in system else "worker"
        _Talk.calls.append(kind)
        if kind == "verifier":
            text = json.dumps({"verdict": "PASS", "reasons": ["khop"],
                               "evidence": [], "confidence": 0.9})
        else:
            text = "xong"
        return text, {"in": 2, "out": 1}


class _Here:
    def __init__(self, root: Path):
        self.root = root
        self.prev = ""

    def __enter__(self):
        self.prev = os.getcwd()
        os.chdir(self.root)
        return self.root

    def __exit__(self, *_a):
        os.chdir(self.prev)
        return False


def _args(root: Path, **extra):
    base = dict(
        resume=None, task="tóm tắt tài liệu công khai", brief=None,
        provider="anthropic", model=None, base_url=None, api_key="k",
        max_tokens=64, oracle="off", require_evidence=True,
        surface="read_only", labels="public", records=10, dollars=0.0,
        reversibility="C1", output_type="free_string", dry_run=False,
        intake="off", approve=True, price_in="1000,0", workers=1,
        sub_depth=0, out=str(root / "out"), clarify_max=0,
    )
    base.update(extra)
    return SimpleNamespace(**base)


class FlowTest(unittest.TestCase):
    def setUp(self):
        _Talk.calls = []
        _Talk.fail = False

    def test_intake_roi_check_roi_giao(self):
        cmd = shlex.join([sys.executable, "-c", "import sys; raise SystemExit(0)"])
        brief = _brief([f"check: {cmd}"])

        class Intake:
            name = "fake"

            def call(self, _s, _u):
                return json.dumps(brief), {"in": 2, "out": 1}

        got = run_intake(
            "tóm tắt tài liệu công khai", Intake(), Ledger(),
            clarify_max=0, ask=lambda _q: "", model="sonnet-5.5",
            declared_price=(1000.0, 0.0))
        self.assertTrue(got["ok"])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "brief.json"
            path.write_text(json.dumps(got["brief"]), encoding="utf-8")
            buf = io.StringIO()
            with _Here(root), redirect_stdout(buf), patch("frog.team.provider_for", _Talk):
                code = cmd_team(_args(root, brief=str(path)))
            text = buf.getvalue()
            self.assertEqual(code, 3)
            self.assertIn("đã chạy lệnh, chưa xác minh tiêu chí:", text)
            self.assertTrue((root / "out" / "withheld.json").is_file())
            self.assertEqual(list((root / "out").glob("*/result.md")), [])

    def test_ngat_roi_resume_khong_goi_lai_buoc_dau(self):
        cmd = shlex.join([sys.executable, "-c", "import sys; raise SystemExit(0)"])
        brief = _brief([f"check: {cmd}"])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "brief.json"
            path.write_text(json.dumps(brief), encoding="utf-8")
            snap = {}
            real = write_checkpoint

            def spy(folder, payload):
                real(folder, payload)
                if payload["next_index"] == 1 and "payload" not in snap:
                    snap["payload"] = json.loads(json.dumps(payload))

            with _Here(root), redirect_stdout(io.StringIO()), patch("frog.team.provider_for", _Talk), \
                    patch("frog.team.write_checkpoint", spy):
                cmd_team(_args(root, brief=str(path), surface="write_external",
                               labels="internal", approve=False))
            self.assertIn("payload", snap)
            self.assertGreaterEqual(len(_Talk.calls), 1)
            write_checkpoint(root, snap["payload"])
            _Talk.calls = []
            buf = io.StringIO()
            with _Here(root), redirect_stdout(buf), patch("frog.team.provider_for", _Talk), \
                    patch("builtins.input", return_value="n"):
                code = cmd_team(_args(root, resume=snap["payload"]["id"], task=None,
                                      brief=None, require_evidence=False))
        self.assertEqual(_Talk.calls, ["verifier"])
        self.assertNotEqual(code, 2)

    def test_doi_brief_khong_dung_ket_qua_cu(self):
        old = _brief(["có một đoạn"])
        new = _brief(["có một đoạn"])
        new["deliverables"] = ["bảng số"]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_checkpoint(root, {
                "id": "run1", "version": 1, "next_index": 1,
                "task": "tóm tắt tài liệu công khai",
                "steps": [{"role": "worker", "text": "xong"}],
                "ledger": {"rows": [{"role": "worker", "model": "m", "provider": "fake",
                                     "in": 2, "out": 1, "usd": 0.01, "priced": True}],
                           "total_usd": 0.01, "total_in": 2, "total_out": 1,
                           "subagent_runs": 0},
                "staging": None, "status": "ok", "fail_reason": None,
                "brief": old, "brief_hash": "cu",
                "hints": {"surface": "read_only", "labels": ["public"], "records": 10,
                          "dollars": 0, "reversibility": "C1", "output_type": "free_string"},
                "workers": 1, "require_evidence": True,
            })
            new_path = root / "new.json"
            new_path.write_text(json.dumps(new), encoding="utf-8")
            buf = io.StringIO()
            with _Here(root), redirect_stdout(buf), patch("frog.team.provider_for", _Talk):
                code = cmd_team(_args(root, resume="run1", task=None, brief=str(new_path)))
            saved = json.loads(checkpoint_path(root, "run1").read_text(encoding="utf-8"))
        self.assertEqual(code, 2)
        self.assertIn("deliverable thêm", buf.getvalue())
        self.assertEqual(saved["brief"]["deliverables"], ["một đoạn"])
        self.assertEqual(_Talk.calls, [])

    def test_tieu_chi_chu_noi_chua_kiem_va_cach_xu_ly(self):
        brief = _brief(["doan van co nguon"])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "brief.json"
            path.write_text(json.dumps(brief), encoding="utf-8")
            buf = io.StringIO()
            with _Here(root), redirect_stdout(buf), patch("frog.team.provider_for", _Talk):
                code = cmd_team(_args(root, brief=str(path)))
            text = buf.getvalue()
        self.assertEqual(code, 3)
        self.assertIn("cần xác nhận:", text)
        self.assertIn("chưa được kiểm tự động", text)
        self.assertIn("bị chặn", text)

    def test_provider_loi_khong_bao_xong(self):
        _Talk.fail = True
        cmd = shlex.join([sys.executable, "-c", "import sys; raise SystemExit(0)"])
        brief = _brief([f"check: {cmd}"])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "brief.json"
            path.write_text(json.dumps(brief), encoding="utf-8")
            buf = io.StringIO()
            with _Here(root), redirect_stdout(buf), patch("frog.team.provider_for", _Talk):
                code = cmd_team(_args(root, brief=str(path)))
            text = buf.getvalue()
            runs = list((root / ".frog" / "runs").glob("*/checkpoint.json"))
            data = json.loads(runs[0].read_text(encoding="utf-8"))
        self.assertEqual(code, 3)
        self.assertNotIn("Executor đã ghi", text)
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["ledger"]["total_usd"], 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
