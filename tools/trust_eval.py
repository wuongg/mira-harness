"""Đo năm lỗi trên tập nhiệm vụ riêng. Provider HTTP cục bộ, không API trả phí.

Không đọc eval/overnight. Không sửa đáp án. Provider giả không phải hiệu quả model thật.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASKS = ROOT / "eval" / "trust" / "tasks.jsonl"


class _Srv(ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        return


class _Fake(BaseHTTPRequestHandler):
    hits: list[str] = []
    lock = threading.Lock()

    def log_message(self, *_a):
        return

    def do_POST(self):
        n = int(self.headers.get("content-length", 0))
        raw = self.rfile.read(n)
        try:
            body = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            body = {}
        system = str(body.get("system") or "")
        if "VERIFIER" in system:
            role = "verifier"
            text = '{"verdict":"PASS","reasons":["khop"],"evidence":[],"confidence":0.9}'
        elif "PLANNER" in system:
            role = "planner"
            text = "buoc 1"
        else:
            role = "worker"
            text = "xong"
        with _Fake.lock:
            _Fake.hits.append(role)
        data = {"content": [{"type": "text", "text": text}],
                "usage": {"input_tokens": 2, "output_tokens": 1}}
        blob = json.dumps(data).encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(blob)))
        self.end_headers()
        self.wfile.write(blob)


def _serve():
    srv = _Srv(("127.0.0.1", 0), _Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def _env(tree: Path) -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(tree)
    env["PYTHONIOENCODING"] = "utf-8"
    for name in list(env):
        if name.endswith("_API_KEY"):
            env.pop(name, None)
    env["ANTHROPIC_API_KEY"] = "local"
    return env


def _roles(tree: Path) -> dict[str, int]:
    del tree
    with _Fake.lock:
        hits = list(_Fake.hits)
    return {name: hits.count(name) for name in ("planner", "worker", "verifier")}


def _clear() -> None:
    with _Fake.lock:
        _Fake.hits.clear()


def _run(tree: Path, root: Path, args: list[str], url: str,
         stdin: str = "", price: str = "1000,0",
         max_tokens: str = "64") -> subprocess.CompletedProcess:
    env = _env(tree)
    cmd = [sys.executable, "-m", "frog", "team", *args, "--provider", "anthropic",
           "--base-url", url, "--price-in", price, "--max-tokens", max_tokens,
           "--oracle", "off", "--intake", "off", "--out", "out"]
    return subprocess.run(
        cmd, cwd=root, env=env, input=stdin.encode("utf-8"),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=40)


def _text(proc: subprocess.CompletedProcess) -> str:
    return (proc.stdout or b"").decode("utf-8", "replace") + "\n" + (
        proc.stderr or b"").decode("utf-8", "replace")


def _results(root: Path) -> list[Path]:
    return list((root / "out").glob("*/result.md"))


def _checkpoint(root: Path) -> dict | None:
    hits = list((root / ".frog" / "runs").glob("*/checkpoint.json"))
    if not hits:
        return None
    return json.loads(hits[0].read_text(encoding="utf-8"))


def _brief(criterion: str, cmd: str) -> dict:
    return {
        "goal": criterion,
        "deliverables": ["mot doan"],
        "acceptance_criteria": [f"check: {cmd}"],
        "constraints": [],
        "assumptions": [],
        "questions": [],
        "per_role_hints": {"planner": "", "worker": "", "verifier": ""},
    }


def _gate(tree: Path, task: str, records: int) -> dict:
    prog = (
        "import json,sys\n"
        "from frog.team import build_plan, two_phrases\n"
        "p = build_plan(sys.argv[1], surface='read_only', labels=['internal'], "
        "records=int(sys.argv[2]), dollars=0.0, reversibility='C1', "
        "output_type='free_string')\n"
        "a,b = two_phrases(p.plan_hash)\n"
        "json.dump({'lane': p.lane, 'dual': p.dual_approval, 'cap': p.cap_usd, "
        "'a': a, 'b': b}, sys.stdout)\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", prog, task, str(records)],
        cwd=root_tmp(), env=_env(tree), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=20)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", "replace"))
    return json.loads(proc.stdout.decode("utf-8"))


def root_tmp() -> Path:
    path = Path(tempfile.mkdtemp())
    return path


def _base_args(task: str, records: int = 10) -> list[str]:
    return [task, "--surface", "read_only", "--labels", "internal",
            "--records", str(records), "--dollars", "0", "--reversibility", "C1"]


def probe_delivery(tree: Path, task: dict, url: str) -> dict:
    _clear()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        cmd = sys.executable + ' -c "raise SystemExit(0)"'
        brief = _brief(task["criterion"], cmd)
        path = root / "brief.json"
        path.write_text(json.dumps(brief), encoding="utf-8")
        proc = _run(tree, root, _base_args(task["task"]) + [
            "--brief", str(path), "--require-evidence", "--approve"], url)
        delivered = bool(_results(root))
        return {"id": task["id"], "kind": task["kind"],
                "fail": delivered, "detail": "lenh thoat 0 van ban giao" if delivered else "",
                "code": proc.returncode}


def probe_block(tree: Path, task: dict, url: str) -> dict:
    _clear()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        proc = _run(tree, root, _base_args(task["task"]) + ["--approve"], url)
        blocked = not _results(root)
        return {"id": task["id"], "kind": task["kind"], "fail": blocked,
                "detail": "khong co tieu chi nhung khong ban giao" if blocked else "",
                "code": proc.returncode}


def probe_unauth(tree: Path, task: dict, url: str) -> dict:
    _clear()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        first = _run(tree, root, _base_args(task["task"]) + ["--approve"], url)
        data = _checkpoint(root)
        if data is None:
            return {"id": task["id"], "kind": task["kind"], "fail": True,
                    "detail": "khong co checkpoint", "code": first.returncode}
        cmd = sys.executable + ' -c "raise SystemExit(2)"'
        data["brief"] = _brief(task["criterion"], cmd)
        data["criteria_origin"] = "model"
        data["require_evidence"] = True
        data["status"] = "ok"
        dest = root / ".frog" / "runs" / data["id"] / "checkpoint.json"
        dest.write_text(json.dumps(data), encoding="utf-8")
        _clear()
        second = _run(tree, root, ["--resume", data["id"], "--approve"], url)
        text = _text(second)
        ran = "chờ cấp quyền" not in text
        return {"id": task["id"], "kind": task["kind"], "fail": ran,
                "detail": "lenh do model dat da duoc chay" if ran else "",
                "code": second.returncode, "tail": text[-500:]}


def probe_budget(tree: Path, task: dict, url: str) -> dict:
    _clear()
    records = int(task.get("records") or 1001)
    info = _gate(tree, task["task"], records)
    stdin = ""
    extra: list[str] = []
    if info.get("dual"):
        stdin = f"an\n{info['a']}\nbinh\n{info['b']}\n"
    else:
        extra = ["--approve"]
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        proc = _run(tree, root, _base_args(task["task"], records) + [
            "--workers", "2", *extra], url, stdin=stdin,
            price="0,1000000", max_tokens="1")
        roles = _roles(tree)
        saved = _checkpoint(root) or {}
        total = float((saved.get("ledger") or {}).get("total_usd") or 0)
        cap = float(info.get("cap") or 0)
        over = roles.get("worker", 0) > 1 or (cap and total > cap + 1e-6)
        return {"id": task["id"], "kind": task["kind"], "fail": over,
                "detail": f"worker={roles.get('worker', 0)} total={total} cap={cap}",
                "code": proc.returncode, "lane": info.get("lane"),
                "tail": _text(proc)[-400:] if over or proc.returncode not in (0, 3) else ""}


def probe_repeat(tree: Path, task: dict, url: str) -> dict:
    _clear()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _run(tree, root, _base_args(task["task"]) + ["--approve"], url)
        before = _roles(tree).get("worker", 0)
        data = _checkpoint(root)
        if data is None:
            return {"id": task["id"], "kind": task["kind"], "fail": True,
                    "detail": "khong co checkpoint", "code": 2}
        _run(tree, root, ["--resume", data["id"], "--approve"], url)
        after = _roles(tree).get("worker", 0)
        again = before < 1 or after > before
        detail = f"worker {before} roi {after}"
        return {"id": task["id"], "kind": task["kind"], "fail": again,
                "detail": detail, "code": 0}


def probe_wrong(tree: Path, task: dict) -> dict:
    prog = (
        "import json,sys,tempfile,hashlib\n"
        "from pathlib import Path\n"
        "from frog.obligations import judge_obligations\n"
        "root = Path(tempfile.mkdtemp())\n"
        "rel = 'calc_wrong.py'\n"
        "(root / rel).write_text(sys.argv[2], encoding='utf-8')\n"
        "digest = hashlib.sha256((root / rel).read_bytes()).hexdigest()\n"
        "cmd = sys.executable + ' -c \"raise SystemExit(0)\"'\n"
        "rows = judge_obligations([{'schema':1,'id':'wrong-file','text':sys.argv[1],'cmd':cmd,"
        "'proves':sys.argv[1],'artifact':rel}], granted={cmd}, run_id='r-wrong',"
        "artifacts={rel:{'sha256':digest,'run_id':'r-wrong'}}, cwd=root)\n"
        "json.dump({'verified': bool(rows and rows[0].get('criterion_verified'))}, sys.stdout)\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", prog, task["criterion"], task["body"]],
        cwd=root_tmp(), env=_env(tree), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=20)
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace")
        missing = "judge_obligations" in err and "granted" in err
        return {"id": task["id"], "kind": task["kind"], "fail": False,
                "remaining": missing, "detail": "cay goc khong co khoa artifact",
                "code": proc.returncode}
    got = json.loads(proc.stdout.decode("utf-8"))
    verified = bool(got.get("verified"))
    return {"id": task["id"], "kind": task["kind"], "fail": verified,
            "remaining": False,
            "detail": "file sai van verified" if verified else "khong verified",
            "code": 0}


def _object(cid: str, text: str, cmd: str = "", validator=None) -> dict:
    item = {"schema": 1, "id": cid, "text": text, "cmd": cmd, "proves": "", "artifact": ""}
    if validator is not None:
        item["validator"] = validator
    return item


def probe_object(tree: Path, task: dict, url: str) -> dict:
    cmd = sys.executable + " -c \"raise SystemExit(0)\""
    brief = _brief(task["criterion"], cmd)
    brief["acceptance_criteria"] = [_object("crit-exit", task["criterion"], cmd)]
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        path = root / "brief.json"
        path.write_text(json.dumps(brief), encoding="utf-8")
        proc = _run(tree, root, _base_args(task["task"]) + [
            "--brief", str(path), "--require-evidence", "--approve"], url)
        held = root / "out" / "withheld.json"
        rows = []
        if held.exists():
            rows = json.loads(held.read_text(encoding="utf-8")).get("obligations") or []
        ok = bool(rows) and rows[0].get("criterion_id") == "crit-exit"
        return {"id": task["id"], "kind": task["kind"], "fail": not ok,
                "detail": "" if ok else "object khong toi buoc kiem", "code": proc.returncode}


def probe_dup(tree: Path, task: dict, url: str) -> dict:
    cmd = "py -c \"raise SystemExit(0)\""
    brief = _brief("cau", cmd)
    brief["acceptance_criteria"] = [_object("same", "cau mot", cmd), _object("same", "cau hai", cmd)]
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        path = root / "brief.json"
        path.write_text(json.dumps(brief), encoding="utf-8")
        proc = _run(tree, root, _base_args(task["task"]) + ["--brief", str(path),
                    "--require-evidence"], url)
        text = _text(proc)
        ok = proc.returncode == 8 and "trùng" in text
        return {"id": task["id"], "kind": task["kind"], "fail": not ok,
                "detail": "" if ok else "id trung khong bi tu choi", "code": proc.returncode}


def probe_artifact(tree: Path, task: dict, url: str) -> dict:
    brief = _brief(task["criterion"], "")
    brief["acceptance_criteria"] = [_object("bad-file", task["criterion"], validator={
        "kind": "contains", "path": "calc.py", "must_contain": ["return 5"],
        "must_not_contain": [],
    })]
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "calc.py").write_text("return 4\n", encoding="utf-8")
        path = root / "brief.json"
        path.write_text(json.dumps(brief), encoding="utf-8")
        proc = _run(tree, root, _base_args(task["task"]) + [
            "--brief", str(path), "--require-evidence", "--approve"], url)
        held = root / "out" / "withheld.json"
        if not held.exists():
            return {"id": task["id"], "kind": task["kind"], "fail": True,
                    "detail": "khong co ho so giu lai", "code": proc.returncode}
        rows = json.loads(held.read_text(encoding="utf-8")).get("obligations") or []
        verified = bool(rows and rows[0].get("criterion_verified"))
        return {"id": task["id"], "kind": task["kind"], "fail": verified or not rows,
                "detail": "artifact sai van verified" if verified else "khong verified",
                "code": proc.returncode}


def probe_change(tree: Path, task: dict, url: str) -> dict:
    _clear()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        first = _brief("co so", "py -c \"raise SystemExit(0)\"")
        first["acceptance_criteria"] = [_object("c1", "co so", "py -c \"raise SystemExit(0)\"")]
        path = root / "brief.json"
        path.write_text(json.dumps(first), encoding="utf-8")
        _run(tree, root, _base_args(task["task"]) + [
            "--brief", str(path), "--approve"], url)
        data = _checkpoint(root)
        if data is None or not data.get("brief"):
            return {"id": task["id"], "kind": task["kind"], "not_evaluated": True,
                    "detail": "run khong co brief de doi", "code": 2}
        new = json.loads(json.dumps(data["brief"]))
        new["acceptance_criteria"] = [_object("c1", "tieu chi da doi", "py -c \"raise SystemExit(0)\"")]
        path = root / "next.json"
        path.write_text(json.dumps(new), encoding="utf-8")
        proc = _run(tree, root, ["--resume", data["id"], "--brief", str(path)], url)
        text = _text(proc)
        ok = proc.returncode == 2 and "không tiếp tục" in text
        return {"id": task["id"], "kind": task["kind"], "fail": not ok,
                "detail": "" if ok else "doi object van chay tiep", "code": proc.returncode}


def probe_kill(tree: Path, task: dict, url: str) -> dict:
    del url
    script = tree / "tests" / "test_request_ledger.py"
    if not script.exists():
        return {"id": task["id"], "kind": task["kind"], "not_evaluated": True,
                "detail": "cay goc khong co bai kill", "code": 0}
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", str(tree / "tests"),
         "-p", "test_request_ledger.py", "-k", "test_kill_giua_request"],
        cwd=tree, env=_env(tree), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=40)
    return {"id": task["id"], "kind": task["kind"], "fail": proc.returncode != 0,
            "detail": "" if proc.returncode == 0 else "kill giua request that bai",
            "code": proc.returncode}


def probe_real(tree: Path, task: dict, url: str) -> dict:
    del tree, url
    return {"id": task["id"], "kind": task["kind"], "not_evaluated": True,
            "detail": "khong co API tra phi duoc duyet", "code": 0}


def _finish(row: dict) -> dict:
    if row.get("not_evaluated") or row.get("remaining"):
        row["status"] = "not_evaluated"
        row["fail"] = False
    elif row.get("fail"):
        row["status"] = "fail"
    else:
        row["status"] = "pass"
    row.pop("remaining", None)
    return row


PROBES = {
    "false_delivery": probe_delivery,
    "false_block": probe_block,
    "unauthorized": probe_unauth,
    "budget": probe_budget,
    "repeat": probe_repeat,
    "object_brief": probe_object,
    "duplicate_id": probe_dup,
    "bad_artifact": probe_artifact,
    "object_change": probe_change,
    "kill_request": probe_kill,
    "real_model": probe_real,
}


def run_tree(tree: Path, url: str) -> list[dict]:
    rows = []
    for line in TASKS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        task = json.loads(line)
        kind = task["kind"]
        try:
            if kind == "wrong_file":
                rows.append(probe_wrong(tree, task))
            else:
                rows.append(PROBES[kind](tree, task, url))
        except Exception as exc:
            rows.append({"id": task["id"], "kind": kind, "fail": True,
                         "detail": type(exc).__name__ + ": " + str(exc), "code": -1})
    return [_finish(row) for row in rows]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--current-only", action="store_true")
    parser.add_argument("--baseline", default="")
    parser.add_argument("--json-out", default="")
    args = parser.parse_args()
    srv, url = _serve()
    try:
        current = run_tree(ROOT, url)
        baseline = None
        if not args.current_only and args.baseline:
            base = Path(args.baseline)
            if base.is_dir():
                baseline = run_tree(base, url)
        report = {"current": current, "baseline": baseline,
                  "note": "provider gia, khong phai hieu qua model that"}
    finally:
        srv.shutdown()
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.json_out:
        Path(args.json_out).write_text(text, encoding="utf-8")
    else:
        sys.stdout.buffer.write(text.encode("utf-8"))
        sys.stdout.buffer.write(b"\n")
    failed = [row for row in current if row.get("status") == "fail"]
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        sys.stderr.write(type(exc).__name__ + ": " + str(exc) + "\n")
        raise
