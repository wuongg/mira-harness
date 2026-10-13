"""Đội agent thật: đưa một task, nó tự phân vai rồi thi hành.

Khác harness đo lường ở chỗ: ở đây THỰC SỰ gọi model. Phần phân vai dùng đúng
logic của SPEC (T1a → T1b → T2 → sàn động → cổng người), nên làn và cổng mà bạn
thấy không phải do LLM quyết — nó do code tất định quyết, đúng bất biến I5.

Bất biến được cài bằng code:
  I1  Cửa ghi cây nguồn là promote sau cổng; `_executor_write()` chỉ ghi `--out`
  I2  fail-closed                   -> verifier FAIL hoặc cổng chưa duyệt ⇒ KHÔNG ghi
  I3  nhãn dữ liệu từ NGUỒN         -> lấy từ tham số dòng lệnh, không từ model
  I5  cổng là code                   -> `human_gate()` trả số, không trả văn bản
  I8  ngân sách ở sổ cái             -> `Ledger`, dừng khi vượt trần làn

Làn 2 có thể chạy N worker + N verifier SONG SONG (thread pool). Song song chỉ
đổi THỜI GIAN, không đổi ai được phép ghi gì: mọi cổng, khoá đường dẫn và
fail-closed vẫn do code quyết.
"""
from __future__ import annotations

import json
import os
import random
import re
import shlex
import shutil
import subprocess
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Callable

from . import config as C
from .providers import ProviderError, provider_for
from .tasks import Task

# ---------------------------------------------------------------- phân vai
ROLES_BY_LANE = {
    0: ["worker"],
    1: ["worker", "verifier"],
    2: ["planner", "worker", "verifier"],
}

# Vai chạy trước (có phụ thuộc tuần tự) và sau (tổng hợp) trong làn 2.
HEAD_ROLES = ("planner",)
TAIL_ROLES = ()

# Đội con: chia phần trần CÒN LẠI của cha, không cấp trần mới (I8).
SUBAGENT_SHARE = C.SUBAGENT["share"]
SUBAGENT_MAX_DEPTH = C.SUBAGENT["max_depth"]
SUBAGENT_MAX_RUNS = C.SUBAGENT["max_runs"]

ROLE_SYSTEM = {
    "planner": ("Bạn là PLANNER. Chẻ mục tiêu thành các bước con rõ ràng, độc lập. "
                "Khoá tiêu chí nghiệm thu cho TỪNG bước. Trả về danh sách đánh số, "
                "mỗi bước kèm tiêu chí kiểm được. Không thực hiện việc, chỉ lập kế hoạch."),
    "coordinator": ("Bạn là COORDINATOR. Nhận kế hoạch và điều phối: chỉ ra thứ tự, "
                    "phụ thuộc giữa các bước, và bước nào có thể chạy song song. "
                    "Trả về bảng phân công ngắn gọn."),
    "worker": ("Bạn là WORKER. Thực hiện yêu cầu và trả về KẾT QUẢ CÔNG VIỆC. "
               "Bạn chỉ ĐỀ XUẤT — mọi thay đổi thật do Executor thực hiện sau khi có duyệt. "
               "Nêu rõ giả định và chỗ còn thiếu dữ liệu."),
    "verifier": ("Bạn là VERIFIER độc lập. Kiểm tra kết quả của worker. "
                 "Trả đúng một object JSON, không chữ nào khác, với các khóa "
                 "verdict, reasons, evidence, confidence. "
                 "verdict chỉ là PASS hoặc FAIL. reasons là danh sách lý do, không rỗng. "
                 "evidence là danh sách bằng chứng. confidence là số từ 0 đến 1."),
    "oracle": ("Bạn là ORACLE. Chấm kết quả theo các tiêu chí nghiệm thu. "
               "Trả đúng một object JSON, không chữ nào khác, với các khóa "
               "verdict, reasons, evidence, confidence, score. "
               "verdict chỉ là PASS hoặc FAIL. score là số từ 0 đến 1. "
               "Không đề xuất cải tiến."),
    "critic": ("Bạn là CRITIC. Tìm lỗ hổng, giả định sai, và chỗ có thể thất bại của "
               "kế hoạch và kết quả. Ưu tiên rủi ro an toàn. Không khen."),
}

ROLE_USER = {
    "planner": "MỤC TIÊU:\n{task}\n\nQuy mô: {records} bản ghi · ngân sách dự kiến ${dollars:.0f}\nBồi hoàn: {reversibility}",
    "coordinator": "MỤC TIÊU:\n{task}\n\nKẾ HOẠCH TỪ PLANNER:\n{prev}",
    "worker": "YÊU CẦU:\n{task}\n\nQuy mô: {records} bản ghi · ${dollars:.0f}\nBồi hoàn: {reversibility}\nSàn rủi ro: {floor}",
    "verifier": "YÊU CẦU GỐC:\n{task}\n\nKẾT QUẢ CỦA WORKER:\n{prev}\n\nKiểm tra độc lập.",
    "oracle": "YÊU CẦU GỐC:\n{task}\n\nKẾT QUẢ:\n{prev}\n\nChấm theo tiêu chí nghiệm thu.",
    "critic": "MỤC TIÊU:\n{task}\n\nKẾT QUẢ:\n{prev}\n\nTìm lỗ hổng.",
}

READ_TOOLS = ("read_file", "list_dir", "grep", "glob", "web_search")
WRITE_TOOLS = ("write_file", "edit_file", "multi_edit", "delete_file")
DIRECTOR_SYSTEM = (
    "Bạn là GIÁM ĐỐC. Chỉ trả các dòng "
    "VAI: ten | việc ngắn | tool1,tool2 | skill "
    "và BUOC: ten. Bỏ mọi chữ khác. Không gọi công cụ."
)
ROLE_PROMPT = "Bạn là {name}. Việc được giao: {job}. Chỉ dùng công cụ đã được phép."


def policy_of(step: dict) -> str:
    """Trace cũ không có khóa. Đọc được, không bịa là đã cắt."""
    value = step.get("context_policy") if isinstance(step, dict) else None
    if value in ("full", "summarized", "truncated"):
        return value
    return "full"


def budget_context(task: str, steps: list[str], *, limit: int = 12000) -> dict:
    """Giữ câu việc và hai bước cuối. Bước cũ hơn được tóm tắt, không cắt im lặng."""
    task = task or ""
    kept = [s for s in (steps or []) if s]

    def joined(parts: list[str]) -> str:
        return "\n\n".join(p for p in parts if p)

    if len(kept) <= 2 and len(task) + len(joined(kept)) <= limit:
        return {"task": task, "prev": joined(kept), "policy": "full"}

    recent = kept[-2:]
    older = []
    for index, step in enumerate(kept[:-2], start=1):
        first = ((step.splitlines() or [""])[0])[:180]
        older.append(f"bước {index}: {first} … [đã tóm tắt]")
    policy = "summarized"
    notice = "đã tóm tắt"

    def body() -> str:
        return joined([notice, *older, *recent])

    while older and len(task) + len(body()) > limit:
        older.pop(0)
        policy = "truncated"
        notice = "đã cắt theo chính sách"
    if len(task) + len(body()) > limit:
        policy = "truncated"
        notice = "đã cắt theo chính sách"
        room = limit - len(task) - len(notice) - 4
        recent = [step[: max(0, room)] for step in recent[:1]]
        if recent and recent[0] and "đã cắt theo chính sách" not in recent[0]:
            recent[0] = recent[0] + "\nđã cắt theo chính sách"
    return {"task": task, "prev": body(), "policy": policy}


def role_prompt(role: str, task: str, steps: list[str], fields: dict, *, limit: int = 12000) -> tuple[str, str]:
    budget = budget_context(task, steps, limit=limit)
    text = ROLE_USER[role].format(task=budget["task"], prev=budget["prev"], **fields)
    if role == "planner" and budget["prev"]:
        text += "\n\nKẾ HOẠCH TRƯỚC:\n" + budget["prev"]
    return text, budget["policy"]


@dataclass
class Role:
    name: str
    job: str
    tools: list[str]
    skill: str = ""


def parse_roster(text: str) -> tuple[list[Role], list[str]]:
    """Chỉ giữ dòng VAI và BUOC. Chữ ngoài các dòng đó bỏ."""
    roles: list[Role] = []
    steps: list[str] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if line.upper().startswith("VAI:"):
            body = line.split(":", 1)[1]
            parts = [p.strip() for p in body.split("|")]
            name = parts[0] if parts else ""
            job = parts[1] if len(parts) > 1 else ""
            tools = [t.strip() for t in re.split(r"[, ]+", parts[2]) if t.strip()] if len(parts) > 2 else []
            skill = parts[3] if len(parts) > 3 else ""
            if name:
                roles.append(Role(name, job, tools, skill))
        elif line.upper().startswith("BUOC:"):
            name = line.split(":", 1)[1].strip()
            if name:
                steps.append(name)
    return roles, steps


def vet_roster(text: str, root: Path | None, *, allow_write: bool = False) -> tuple[bool, str, list[Role], list[str]]:
    """Từ chối đội sai trước khi chạy. Trả lý do tiếng Việt."""
    roles, steps = parse_roster(text)
    if not roles or not steps:
        return False, "thiếu VAI hoặc BUOC", [], []
    if len(roles) > 3:
        return False, "quá ba vai", [], []
    known = {r.name for r in roles}
    if any(s not in known for s in steps):
        return False, "bước không có trong danh sách vai", [], []
    catalog: set[str] = set()
    if root is not None:
        from .skills import load_skills
        catalog = {s["name"] for s in load_skills(root)}
    writers = 0
    for role in roles:
        if role.skill and role.skill not in catalog:
            return False, f"skill {role.skill} không có trong catalog", [], []
        if not role.tools:
            return False, f"vai {role.name} không có tool", [], []
        for tool in role.tools:
            if tool in WRITE_TOOLS:
                if not allow_write:
                    return False, f"tool {tool} ngoài trần đọc", [], []
                writers += 1
            elif tool not in READ_TOOLS:
                return False, f"tool {tool} ngoài trần đọc", [], []
    if writers > 1:
        return False, "hai vai ghi", [], []
    return True, "", roles, steps


@dataclass
class TeamPlan:
    task_text: str
    lane: int
    floor: int
    floor_reason: str
    capability: str
    gate_tier: int
    gate_minutes: float
    dual_approval: bool
    roles: list[str]
    roles_reason: str
    task: Task | None = None
    cap_usd: float = 0.0
    plan_hash: str = ""
    declared_price: tuple[float, float] | None = None

    def as_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k != "task"}
        return d


def make_task(task_text: str, *, surface: str = "read_only",
              labels: list[str] | None = None, records: int = 50,
              dollars: float = 0.0, reversibility: str = "C1",
              output_type: str = "free_string", untrusted: bool | None = None) -> Task:
    """Dựng một Task THẬT từ yêu cầu người dùng + nhãn do NGƯỜI khai (I3)."""
    labels = labels or ["internal"]
    if untrusted is None:
        untrusted = any(w in task_text.lower() for w in
                        ("email", "nguyên văn", "đối tác", "bên thứ ba", "khách gửi", "paste"))
    return Task(
        id="T0001", stratum="live", request=task_text,
        observable={"tool_surface": surface, "data_labels": labels,
                    "untrusted_content": untrusted, "reversibility": reversibility,
                    "output_type": output_type, "records": records, "dollars": float(dollars),
                    "isolation_proven_by_code": surface in ("read_only", "write_sandbox"),
                    "isolation_sound": surface in ("read_only", "write_sandbox"),
                    "isolation_hash_logged": False},
        truth={"stratum_desc": "tác vụ thật", "injection_present": untrusted,
               "label_missed_injection": False,
               "truth_floor": C.RIGHTS_FLOOR[surface], "p_catch": 0.8, "p_false": 0.1},
        sizes={"tool_calls": 10, "depth": 2, "context_tokens": 20000,
               "criteria_locked": 3, "turns": 4, "work_units": 2},
    )


def build_plan(task_text: str, **hints) -> TeamPlan:
    from .pipeline import dynamic_floor, human_gate, t1a_policy

    t = make_task(task_text, **hints)
    base = t1a_policy(t)
    floor = dynamic_floor(t, {"probation_ok": False})
    lane = base["lane_base"]
    if floor["floor"] >= 2:
        lane = max(lane, floor["floor"] - 1)
    lane = min(lane, C.LANE_MAX)
    gate = human_gate(t, lane, floor)
    roles = ROLES_BY_LANE[lane]
    reason = (f"T1a xếp làn cơ sở {base['lane_base']} theo bề mặt tool "
              f"{t.observable['tool_surface']} + bồi hoàn {t.observable['reversibility']}; "
              f"sàn rủi ro {floor['floor']} ({floor['reason']})")
    return TeamPlan(task_text=task_text, lane=lane, floor=floor["floor"],
                    floor_reason=floor["reason"], capability=base["capability"],
                    gate_tier=gate["tier"], gate_minutes=gate["minutes"],
                    dual_approval=gate["dual_approval"], roles=roles,
                    roles_reason=reason, task=t,
                    cap_usd=C.BUDGET.get(lane, {}).get("cap", 0.0),
                    plan_hash=gate["plan_hash"])


_COPY_SKIP = {".git", "__pycache__", ".env"}


def prepare_staging(root: Path) -> Path:
    """Bản sao cây nguồn cho một run. Bỏ .git, .env, __pycache__ và staging cũ."""
    root = Path(root).resolve()
    rid = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
    staging = root / ".mira" / "staging" / rid
    staging.mkdir(parents=True)

    def ignore(directory, names):
        skipped = [name for name in names if name in _COPY_SKIP]
        if Path(directory).resolve() == (root / ".mira") and "staging" not in skipped:
            skipped.append("staging")
        return skipped

    for child in root.iterdir():
        if child.name in _COPY_SKIP:
            continue
        dest = staging / child.name
        if child.is_dir():
            shutil.copytree(child, dest, ignore=ignore)
        elif child.is_file():
            shutil.copy2(child, dest)
    return staging


def checkpoint_path(root: Path, run_id: str) -> Path:
    return Path(root) / ".mira" / "runs" / run_id / "checkpoint.json"


def write_checkpoint(root: Path, payload: dict) -> None:
    """Ghi nguyên tử. File tạm cùng thư mục rồi os.replace."""
    dest = checkpoint_path(root, payload["id"])
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, dest)


def _ledger_ok(blob: dict) -> bool:
    rows = blob.get("rows") or []
    got = round(sum(float(row.get("usd", 0.0)) for row in rows), 6)
    return round(float(blob.get("total_usd", 0.0)), 6) == got


def ledger_from_checkpoint(blob: dict) -> Ledger:
    """Gán rows đã chi. Không gọi charge."""
    led = Ledger()
    led.rows = list(blob.get("rows") or [])
    led.total_usd = float(blob.get("total_usd", 0.0))
    led.total_in = int(blob.get("total_in", 0))
    led.total_out = int(blob.get("total_out", 0))
    led.subagent_runs = int(blob.get("subagent_runs", 0))
    return led


def load_checkpoint(root: Path, run_id: str) -> dict:
    path = checkpoint_path(root, run_id)
    if not path.is_file():
        raise CheckpointError("không có checkpoint cho id này")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not _ledger_ok(data.get("ledger") or {}):
        raise CheckpointError("checkpoint lệch sổ cái")
    return data


class CheckpointError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def withhold_staging(staging: Path) -> Path:
    """Đổi tên staging thành *.withheld. Không đụng cây nguồn."""
    staging = Path(staging)
    if not staging.exists() or staging.name.endswith(".withheld"):
        return staging
    dest = staging.with_name(staging.name + ".withheld")
    if dest.exists():
        shutil.rmtree(dest)
    staging.rename(dest)
    return dest


_PHRASE_WORDS = (
    "cửa", "sổ", "trăng", "non", "gió", "lúa",
    "đồi", "sông", "mây", "đá", "nắng", "rừng",
)


def two_phrases(seed: str) -> tuple[str, str]:
    """Hai cụm bốn từ tiếng Việt, khác nhau, cùng một plan_hash."""
    rng = random.Random(seed or "mira")
    words = list(_PHRASE_WORDS)
    rng.shuffle(words)
    return " ".join(words[:4]), " ".join(words[4:8])


def _rel_skipped(rel: Path) -> bool:
    parts = rel.parts
    if ".git" in parts or "__pycache__" in parts or ".env" in parts:
        return True
    return len(parts) >= 2 and parts[0] == ".mira" and parts[1] == "staging"


def promote_staging(real_root: Path, staging: Path, audit: list) -> list[str]:
    """Đưa file khác bản nguồn vào cây thật. Chỉ gọi sau verifier và cổng người."""
    real_root = Path(real_root).resolve()
    staging = Path(staging).resolve()
    promoted: list[str] = []
    for path in sorted(staging.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(staging)
        if _rel_skipped(rel):
            continue
        dest = real_root / rel
        new = path.read_bytes()
        old = dest.read_bytes() if dest.is_file() else None
        if old == new:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        os.replace(str(path), str(dest))
        rel_s = rel.as_posix()
        audit.append({"action": "promote", "path": rel_s})
        promoted.append(rel_s)
    return promoted


def expand_roles(roles: list[str], lane: int, workers: int) -> list[str]:
    """N worker / N verifier khi làn 2 chạy song song; ngược lại giữ nguyên."""
    if lane != 2 or workers <= 1:
        return list(roles)
    out: list[str] = []
    for r in roles:
        if r in ("worker", "verifier"):
            out += [r] * workers
        else:
            out.append(r)
    return out


# ---------------------------------------------------------------- sổ cái
@dataclass
class Ledger:
    rows: list[dict] = field(default_factory=list)
    total_usd: float = 0.0
    total_in: int = 0
    total_out: int = 0
    subagent_runs: int = 0          # đếm đội con trong CẢ cây (chặn bùng nổ)

    def __post_init__(self) -> None:
        self._lock = threading.RLock()

    def charge(self, role: str, model: str, usage: dict, provider: str,
               *, price: dict | None = None, declared_by_user: bool = False,
               price_source: str = "") -> float:
        tin, tout = usage.get("in", 0), usage.get("out", 0)
        p = price if price is not None else C.PRICES.get(model)
        if p:
            usd = (tin * p["in"] + tout * p["out"]) / 1e6
        else:
            usd = 0.0
        row = {"role": role, "model": model, "provider": provider,
               "in": tin, "out": tout, "usd": round(usd, 6),
               "priced": bool(p), "price_source": price_source}
        if declared_by_user:
            row["declared_by_user"] = True
        with self._lock:
            self.rows.append(row)
            self.total_usd += usd
            self.total_in += tin
            self.total_out += tout
            return usd

    def summary(self) -> dict:
        by_role: dict[str, float] = {}
        for r in self.rows:
            by_role[r["role"]] = round(by_role.get(r["role"], 0.0) + r["usd"], 6)
        return {"total_usd": round(self.total_usd, 6), "by_role": by_role,
                "tokens_in": self.total_in, "tokens_out": self.total_out,
                "subagent_runs": self.subagent_runs,
                "all_priced": all(r["priced"] for r in self.rows) if self.rows else True,
                "declared_by_user": any(r.get("declared_by_user") for r in self.rows),
                "price_sources": [r.get("price_source", "") for r in self.rows]}


# ------------------------------------------------------------- thực thi
def _verdict_envelope(text: str, *, require_score: bool = False) -> dict | None:
    """Chỉ nhận một object JSON. Sai kiểu, thiếu khóa, hoặc khóa lạ thì bỏ."""
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    allowed = {"verdict", "reasons", "evidence", "confidence"}
    if require_score:
        allowed = allowed | {"score"}
    if set(obj) != allowed:
        return None
    if obj.get("verdict") not in ("PASS", "FAIL"):
        return None
    reasons = obj.get("reasons")
    if (not isinstance(reasons, list) or not reasons
            or not all(isinstance(item, str) and item.strip() for item in reasons)):
        return None
    evidence = obj.get("evidence")
    if not isinstance(evidence, list) or not all(isinstance(item, str) for item in evidence):
        return None
    conf = obj.get("confidence")
    if isinstance(conf, bool) or not isinstance(conf, (int, float)) or not 0 <= float(conf) <= 1:
        return None
    if require_score:
        score = obj.get("score")
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not 0 <= float(score) <= 1:
            return None
    return obj


def staging_evidence(root: Path, staging: Path, task: str, worker_text: str) -> dict:
    """Chỉ chạy lệnh có tên trong câu của NGƯỜI. Lệnh do model bịa không được chạy."""
    from .agent import _named_command
    from .tools import _shell_env
    root = Path(root).resolve()
    staging = Path(staging).resolve()
    diff = False
    for path in staging.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(staging)
        if _rel_skipped(rel):
            continue
        dest = root / rel
        old = dest.read_bytes() if dest.is_file() else None
        if old != path.read_bytes():
            diff = True
            break
    claimed = bool(re.search(r"đã sửa|\bedited\b", worker_text or "", re.IGNORECASE))
    cmd = _named_command(task)
    exit_code = None
    if cmd:
        argv = shlex.split(cmd, posix=True)
        if argv:
            proc = subprocess.run(argv, shell=False, cwd=str(staging), timeout=60,
                                  capture_output=True, text=True, env=_shell_env())
            exit_code = proc.returncode
    return {"empty_diff": not diff, "claimed": claimed, "cmd": cmd, "exit": exit_code}


def execute_plan(plan: TeamPlan, *, provider_name: str | None = None,
                 model_override: str | None = None, base_url: str | None = None,
                 api_key: str | None = None, max_tokens: int = 4096,
                 workers: int = 1,
                 depth: int = 0,
                 ledger: "Ledger | None" = None,
                 on_step: Callable[[str], None] | None = None,
                 dry_run: bool = False,
                 root: Path | None = None,
                 oracle: str | None = None,
                 run_id: str | None = None,
                 resume_steps: list | None = None,
                 resume_staging: str | None = None,
                 record: bool = True) -> dict:
    """Chạy kế hoạch. Trả về bản ghi đầy đủ. KHÔNG tự ghi ra đĩa.

    `workers > 1` + làn 2: N worker chạy SONG SONG, rồi N verifier chạy song song.
    `depth > 0`: mỗi worker được mở một ĐỘI CON (làn 1: worker + verifier riêng),
    chia phần trần CÒN LẠI của cha — không cấp trần mới. `ledger` truyền xuống để
    cả cây dùng chung một sổ cái, nên trần của cha vẫn là cổng chặn cuối (I8).
    Thứ tự bước trả về vẫn theo chỉ số nên HÌNH DẠNG kết quả tất định; nội dung do
    model sinh nên vẫn ngẫu nhiên — đúng bản chất live.
    """
    log = on_step or (lambda _m: None)
    ledger = ledger if ledger is not None else Ledger()
    skill_names: list[str] = []
    skill_at = [-1]
    skill_retried = [False]
    steps: list[dict] = []
    prev = ""
    staging_box: list[Path | None] = [None]
    status = "ok"
    fail_reason = None
    run_id = run_id or uuid.uuid4().hex[:12]
    pending = [dict(step) for step in (resume_steps or [])]
    if resume_staging:
        staging_box[0] = Path(resume_staging)

    def _reuse(factory):
        if pending:
            return pending.pop(0)
        return factory()

    def _snapshot() -> None:
        if root is None or not record:
            return
        obs = plan.task.observable
        price = getattr(plan, "declared_price", None)
        write_checkpoint(root, {
            "id": run_id,
            "next_index": len(steps),
            "task": plan.task_text,
            "steps": steps,
            "ledger": {
                "rows": list(ledger.rows),
                "total_usd": round(ledger.total_usd, 6),
                "total_in": ledger.total_in,
                "total_out": ledger.total_out,
                "subagent_runs": ledger.subagent_runs,
            },
            "staging": str(staging_box[0]) if staging_box[0] is not None else None,
            "status": status,
            "fail_reason": fail_reason,
            "hints": {
                "surface": obs["tool_surface"],
                "labels": list(obs["data_labels"]),
                "records": obs["records"],
                "dollars": obs["dollars"],
                "reversibility": obs["reversibility"],
                "output_type": obs["output_type"],
            },
            "declared_price": list(price) if price else None,
            "workers": workers,
        })

    def _note(st: dict) -> dict:
        steps.append(st)
        _snapshot()
        return st

    verifier_verdict = None
    verifier_raw = ""
    verifier_parsed = None
    oracle_score = None
    lock = threading.Lock()
    fanout = plan.lane == 2 and workers > 1

    def _model_of(role: str) -> str:
        return model_override or C.ROLE_MODEL.get(role, "sonnet-5.5")

    def _prior() -> list[str]:
        return [s["text"] for s in steps if isinstance(s, dict) and s.get("text")]

    def _as_steps(prior) -> list[str]:
        if prior is None:
            return []
        if isinstance(prior, str):
            return [prior] if prior else []
        return [s for s in prior if isinstance(s, str) and s]

    def _user_of(role: str, prior, shard: tuple[int, int] | None) -> tuple[str, str]:
        fields = {
            "records": plan.task.observable["records"],
            "dollars": plan.task.observable["dollars"],
            "reversibility": plan.task.observable["reversibility"],
            "floor": plan.floor,
        }
        u, policy = role_prompt(role, plan.task_text, _as_steps(prior), fields)
        if shard:
            u += (f"\n\n[PHẦN {shard[0]}/{shard[1]} — chỉ làm phần này, "
                  f"không lặp lại phần của phần khác]")
        prompts = getattr(plan, "role_prompts", None) or {}
        if role in prompts:
            u = prompts[role] + "\n\n" + u
        if root is not None and role in ("planner", "worker"):
            from .skills import catalog_for_prompt, load_skills, memory_block, worker_skill_block
            skills = load_skills(root)
            if skills:
                cat, stats = catalog_for_prompt(skills, plan.task_text)
                u += (f"\n\n{cat}\n(catalog: {stats['skills']} skill, "
                      f"{stats['tokens']} token, giữ {stats['kept']})")
            mem = memory_block(root, plan.task_text)
            if mem:
                u += "\n\n" + mem
            if role == "planner":
                u += "\nNếu cần skill, dòng cuối đúng dạng: SKILLS: ten, ten"
            elif 0 <= skill_at[0] < len(skill_names):
                u += "\n\n" + worker_skill_block(root, skill_names[skill_at[0]])
        return u, policy

    def _rates(model: str) -> tuple[dict | None, str]:
        from .prices import resolve_price
        return resolve_price(model, plan.declared_price)

    def _call(role: str, prior=None, shard: tuple[int, int] | None = None) -> dict:
        """Một lần gọi model. An toàn khi chạy trong nhiều luồng."""
        _user, policy = _user_of(role, prior, shard)
        model = _model_of(role)
        rates, source = _rates(model)
        if rates is None:
            return {"role": role, "model": model, "shard": shard, "blocked": True,
                    "error": f"model {model} chưa có giá", "context_policy": policy}
        prov = provider_for(model, provider_name, base_url=base_url,
                            api_key=api_key, max_tokens=max_tokens)
        if not prov.available():
            key = "ANTHROPIC_API_KEY" if prov.name == "anthropic" else "OPENAI_API_KEY"
            return {"role": role, "model": model, "shard": shard, "blocked": True,
                    "error": f"thiếu key cho {prov.name} — đặt {key}",
                    "context_policy": policy}
        t0 = time.time()
        try:
            text, usage = prov.call(ROLE_SYSTEM[role], _user)
        except ProviderError as e:
            return {"role": role, "model": model, "shard": shard, "error": str(e),
                    "attempt": getattr(prov, "attempts", 1), "context_policy": policy}
        with lock:                                  # sổ cái phải nguyên tử (I8)
            usd = ledger.charge(role, model, usage, prov.name, price=rates,
                                declared_by_user=source == "cli", price_source=source)
        return {"role": role, "model": model, "shard": shard, "provider": prov.name,
                "text": text, "usage": usage, "usd": round(usd, 6),
                "seconds": round(time.time() - t0, 2),
                "attempt": getattr(prov, "attempts", 1),
                "context_policy": policy}

    def _fanout(items: list[tuple[str, str, tuple[int, int] | None]]) -> list[dict]:
        """Chạy nhiều lần gọi SONG SONG; trả về ĐÚNG THỨ TỰ chỉ số."""
        return _parallel(_call, items)

    def _parallel(fn, items: list) -> list:
        if not items:
            return []
        if len(items) == 1:
            return [fn(*items[0])]
        with ThreadPoolExecutor(max_workers=len(items)) as ex:
            futs = [ex.submit(fn, *it) for it in items]
            return [f.result() for f in futs]

    def _log_step(st: dict) -> None:
        tag = st["role"] + (f"#{st['shard'][0]}" if st.get("shard") else "")
        if st.get("sub"):
            log(f"{tag:<12} ↳ đội con làn {st['sub']['lane']} · {st['sub']['status']}"
                f" · ${st['sub'].get('usd', 0.0):.5f} · sâu {st['sub']['depth']}")
            return
        if st.get("blocked"):
            log(f"{tag:<12} BỎ QUA — {st['error']}")
        elif st.get("error"):
            log(f"{tag:<12} LỖI — {st['error']}")
        else:
            log(f"{tag:<12} {st['model']:<16} {st['usage']['in']:>6}+{st['usage']['out']:<5} tok"
                f"  ${st['usd']:.5f}  {st['seconds']:5.1f}s")

    def _sub_task(shard: tuple[int, int] | None) -> str:
        if not shard:
            return plan.task_text
        return f"{plan.task_text}\n\n[PHẦN {shard[0]}/{shard[1]} — chỉ làm phần này]"

    def _worker_step(pv: str, shard: tuple[int, int] | None) -> dict:
        """Một worker: hoặc gọi thẳng model, hoặc mở đội con nếu còn độ sâu.

        Chỉ LÀN 2 mới được mở đội con — làn 0/1 giữ đúng định nghĩa 1 agent / 1 cặp.
        Đội con là làn 2 khi còn độ sâu để lồng tiếp, ngược lại là làn 1 (vẫn có
        verifier riêng, nhưng rẻ hơn).
        """
        if depth <= 0 or plan.lane < 2:
            return _call("worker", prior=pv, shard=shard)

        # --- đội con: chia phần trần CÒN LẠI, không cấp trần mới (I8) ---
        with lock:
            remaining = (plan.cap_usd - ledger.total_usd) if plan.cap_usd else None
            over_runs = ledger.subagent_runs >= SUBAGENT_MAX_RUNS
            if not over_runs:
                ledger.subagent_runs += 1
        if over_runs:
            return {"role": "worker", "shard": shard, "blocked": True,
                    "error": f"chạm trần {SUBAGENT_MAX_RUNS} đội con trong cây"}
        if remaining is not None and remaining <= 0:
            return {"role": "worker", "shard": shard, "blocked": True,
                    "error": "hết ngân sách trước khi mở đội con"}
        sub_cap = (remaining * SUBAGENT_SHARE) if remaining is not None else 0.0
        sub_lane = 2 if depth > 1 else 1
        sub = TeamPlan(task_text=_sub_task(shard), lane=sub_lane, floor=plan.floor,
                       floor_reason=plan.floor_reason, capability=plan.capability,
                       gate_tier=plan.gate_tier, gate_minutes=plan.gate_minutes,
                       dual_approval=plan.dual_approval,
                       roles=ROLES_BY_LANE[sub_lane], roles_reason="đội con của worker",
                       task=plan.task, cap_usd=sub_cap)
        before = ledger.total_usd
        log(f"{'worker' + (f'#{shard[0]}' if shard else ''):<12} ↳ mở đội con làn {sub_lane}"
            f" (sâu {depth}" + (f", trần ${sub_cap:.4f}" if plan.cap_usd else "") + ")")
        sub_res = execute_plan(sub, provider_name=provider_name, model_override=model_override,
                               base_url=base_url, api_key=api_key, max_tokens=max_tokens,
                               workers=1, depth=depth - 1, ledger=ledger, on_step=log,
                               root=root, record=False)
        text = _aggregate(sub_res)
        st = {"role": "worker", "shard": shard, "model": _model_of("worker"),
              "provider": "nested", "text": text, "usage": {"in": 0, "out": 0},
              "usd": round(ledger.total_usd - before, 6), "seconds": 0.0,
              "sub": {"lane": sub_lane, "depth": depth, "status": sub_res["status"],
                      "verifier_verdict": sub_res["verifier_verdict"],
                      "usd": round(ledger.total_usd - before, 6)}}
        if sub_res["status"] != "ok":
            st["degraded"] = True
        return st

    def _worker_edit(pv: str) -> dict:
        """Một worker sửa trong staging. Không mở worker thứ hai trên cùng một cây."""
        from .agent import run_turn
        from .tools import Session
        model = _model_of("worker")
        rates, source = _rates(model)
        budget = budget_context(plan.task_text, _as_steps(pv))
        shown = budget["prev"] or plan.task_text
        if budget["policy"] != "full":
            shown = plan.task_text + "\n\n" + budget["prev"]
        if rates is None:
            return {"role": "worker", "model": model, "blocked": True,
                    "error": f"model {model} chưa có giá", "edited": False,
                    "context_policy": budget["policy"]}
        staging_box[0] = prepare_staging(Path(root))
        child = Session(root=staging_box[0], mode="acceptEdits", approve=lambda _t, _a: True)
        child.gate_task = plan.task_text
        child.recruited = True
        res = run_turn(task=shown, session=child, model=model,
                       provider_name=provider_name, base_url=base_url, api_key=api_key,
                       max_tokens=max_tokens, protocol="text", no_stream=True,
                       price_in=plan.declared_price)
        usage = res.get("usage") or {"in": 0, "out": 0}
        usd = ledger.charge("worker", model, usage, "run_turn", price=rates,
                            declared_by_user=source == "cli", price_source=source)
        return {"role": "worker", "model": _model_of("worker"), "provider": "run_turn",
                "text": res.get("final") or "", "usage": usage,
                "usd": usd, "seconds": float(res.get("seconds") or 0),
                "edited": True, "audit": list(child.audit), "error": res.get("error"),
                "context_policy": budget["policy"]}

    def _over_cap() -> bool:
        return bool(plan.cap_usd) and ledger.total_usd > plan.cap_usd

    oracle_gate = "disabled"
    if oracle == "on" and plan.lane == 2:
        oracle_gate = "on"
        if "oracle" not in plan.roles:
            plan.roles = list(plan.roles) + ["oracle"]
    run_tail = ("oracle",) if oracle_gate == "on" else ()

    # ------------------------------------------------------------- dry-run
    if dry_run:
        for role in expand_roles(plan.roles, plan.lane, workers):
            steps.append({"role": role, "model": _model_of(role), "skipped": "dry-run",
                          "system": ROLE_SYSTEM[role], "user_len": None})
            log(f"{role:<12} {_model_of(role):<16} (dry-run, không gọi)")
        return {"status": "ok", "fail_reason": None, "verifier_verdict": None,
                "oracle_score": None, "oracle_gate": oracle_gate, "steps": steps,
                "ledger": ledger.summary(), "plan": plan.as_dict()}

    head = [r for r in plan.roles if r in HEAD_ROLES]
    tail = [r for r in plan.roles if r in run_tail]
    has_worker = "worker" in plan.roles
    has_verifier = "verifier" in plan.roles

    def _stop_budget() -> None:
        nonlocal status, fail_reason
        status = "stopped_budget"
        fail_reason = f"vượt trần làn {plan.lane} (${plan.cap_usd})"
        log(f"  → DỪNG: {fail_reason}")

    # --- pha 1: planner → coordinator (tuần tự, có phụ thuộc dữ liệu) ---
    for role in head:
        st = _reuse(lambda role=role: _call(role, prior=_prior()))
        _log_step(st)
        _note(st)
        if st.get("error") or st.get("blocked"):
            status = "blocked" if st.get("blocked") else "error"
            fail_reason = st["error"]
            break
        if role == "planner":
            prev = st["text"]
            if root is not None:
                from .skills import choose_skills, load_skills, parse_skill_line
                known = {s["name"] for s in load_skills(root)}
                kept, refused = choose_skills(parse_skill_line(prev), known)
                if refused and not skill_retried[0] and not st.get("error"):
                    skill_retried[0] = True
                    prev += "\nTỪ CHỐI skill: " + ", ".join(refused)
                    st2 = _reuse(lambda: _call("planner", prior=_prior() + [f"TỪ CHỐI skill: {', '.join(refused)}"]))
                    _log_step(st2)
                    _note(st2)
                    if st2.get("error") or st2.get("blocked"):
                        status = "blocked" if st2.get("blocked") else "error"
                        fail_reason = st2["error"]
                        break
                    prev = st2.get("text") or ""
                    kept, refused = choose_skills(parse_skill_line(prev), known)
                skill_names[:] = kept
                if refused:
                    prev += "\nTỪ CHỐI skill: " + ", ".join(refused)
        if _over_cap():
            _stop_budget()
            break
    else:
        # --- pha 2: worker (song song nếu làn 2 + workers > 1) ---
        worker_steps: list[dict] = []
        if has_worker and skill_names:
            texts: list[str] = []
            for index, _name in enumerate(skill_names):
                skill_at[0] = index
                st = _reuse(lambda: _call("worker", prior=_prior()))
                _log_step(st)
                _note(st)
                worker_steps.append(st)
                if st.get("error") or st.get("blocked"):
                    status = "blocked" if st.get("blocked") else "error"
                    fail_reason = st["error"]
                    break
                if st.get("text"):
                    texts.append(st["text"])
                    prev = "\n\n".join(f"[worker {n + 1}] {bit}" for n, bit in enumerate(texts))
                if _over_cap():
                    _stop_budget()
                    break
            skill_at[0] = -1
        elif has_worker:
            from .tools import shape_of
            if root is not None and shape_of(plan.task_text) == "edit":
                worker_steps = [_reuse(lambda: _worker_edit(_prior()))]
                for st in worker_steps:
                    _log_step(st)
                    _note(st)
                bad = next((s for s in worker_steps if s.get("error") or s.get("blocked")), None)
                if bad:
                    status = "blocked" if bad.get("blocked") else "error"
                    fail_reason = bad["error"]
                if _over_cap():
                    _stop_budget()
                prev = worker_steps[0].get("text") or ""
            else:
                if fanout:
                    items = [(_prior(), (i + 1, workers)) for i in range(workers)]
                else:
                    items = [(_prior(), None)]
                if len(items) == 1:
                    worker_steps = [_reuse(lambda: _worker_step(*items[0]))]
                else:
                    worker_steps = _parallel(_worker_step, items)
                for st in worker_steps:
                    _log_step(st)
                    _note(st)
                bad = next((s for s in worker_steps if s.get("error") or s.get("blocked")), None)
                if bad:
                    status = "blocked" if bad.get("blocked") else "error"
                    fail_reason = bad["error"]
                if _over_cap():
                    _stop_budget()
                prev = "\n\n".join(f"[worker {i + 1}] {s.get('text', '')}"
                                   for i, s in enumerate(worker_steps) if s.get("text"))

        # --- pha 3: verifier (song song, mỗi worker một verifier) ---
        if status == "ok" and has_verifier:
            if fanout and worker_steps:
                ver_steps = _fanout([("verifier", _prior(),
                                      (i + 1, len(worker_steps)))
                                     for i in range(len(worker_steps))])
            else:
                ver_steps = [_reuse(lambda: _call("verifier", prior=_prior()))]
            for st in ver_steps:
                env = _verdict_envelope(st.get("text", ""))
                st["verdict_raw"] = st.get("text", "")
                st["verdict_parsed"] = env
                _log_step(st)
                _note(st)
            parsed = [s.get("verdict_parsed") for s in ver_steps]
            if ver_steps:
                verifier_raw = ver_steps[-1].get("text", "")
                verifier_parsed = parsed[-1]
            verdicts = [None if env is None else env["verdict"] for env in parsed]
            if not verdicts or any(v is None for v in verdicts):
                verifier_verdict = None
            elif all(v == "PASS" for v in verdicts):
                verifier_verdict = "PASS"
                if root is not None:
                    from .skills import fact_from_audit, remember_fact
                    line = fact_from_audit(None)
                    if line:
                        remember_fact(root, plan.task_text, line)
            else:
                verifier_verdict = next(v for v in verdicts if v != "PASS")
            if _over_cap():
                _stop_budget()

        # --- pha 4: oracle → critic (tổng hợp) ---
        if status == "ok":
            for role in tail:
                st = _reuse(lambda role=role: _call(role, prior=_prior()))
                _log_step(st)
                _note(st)
                if st.get("error") or st.get("blocked"):
                    status = "blocked" if st.get("blocked") else "error"
                    fail_reason = st["error"]
                    break
                if role == "oracle" and oracle_gate == "on":
                    env = _verdict_envelope(st.get("text", ""), require_score=True)
                    st["verdict_raw"] = st.get("text", "")
                    st["verdict_parsed"] = env
                    if env is None:
                        status, fail_reason = "withheld", "oracle không theo giao thức, giữ lại"
                    else:
                        oracle_score = float(env["score"])
                if _over_cap():
                    _stop_budget()
                    break

    # ---- fail-closed (I2) ----
    evidence = None
    if status == "ok" and staging_box[0] is not None and root is not None:
        bits = [s.get("text") or "" for s in steps if s.get("role") == "worker"]
        if any(s.get("edited") for s in steps if s.get("role") == "worker"):
            bits.append("đã sửa")
        evidence = staging_evidence(Path(root), staging_box[0], plan.task_text, "\n".join(bits))
        if evidence["empty_diff"] and evidence["claimed"]:
            status, fail_reason = "withheld", "diff trống dù worker nói đã sửa"
        elif evidence["exit"] not in (None, 0):
            status, fail_reason = "withheld", "lệnh trong câu việc không thoát 0"
    if status == "ok" and plan.lane >= 1:
        if verifier_verdict is None:
            status, fail_reason = "withheld", "verifier không theo giao thức, giữ lại"
        elif verifier_verdict != "PASS":
            status, fail_reason = "withheld", f"verifier trả {verifier_verdict}"
    if status == "ok" and plan.lane == 2 and oracle_score is not None and oracle_score < 0.7:
        status, fail_reason = "withheld", f"oracle chấm {oracle_score} < 0,70"
    # đội con không qua kiểm -> làm bẩn cả lượt, KHÔNG giao (đọc chặt của I2)
    if status == "ok" and any(s.get("degraded") for s in steps):
        status, fail_reason = "withheld", "có đội con không qua kiểm"

    staging_out = None
    if staging_box[0] is not None:
        if status != "ok":
            staging_out = str(withhold_staging(staging_box[0]))
        else:
            staging_out = str(staging_box[0])

    _snapshot()
    return {"id": run_id, "status": status, "fail_reason": fail_reason,
            "verifier_verdict": verifier_verdict, "oracle_score": oracle_score,
            "verdict_raw": verifier_raw, "verdict_parsed": verifier_parsed,
            "oracle_gate": oracle_gate,
            "steps": steps, "ledger": ledger.summary(), "plan": plan.as_dict(),
            "depth": depth, "nested": any(s.get("sub") for s in steps),
            "staging": staging_out, "staging_evidence": evidence,
            "promoted": [], "promote_audit": [],
            "role_prompts": getattr(plan, "role_prompts", None),
            "brief_hash": getattr(plan, "brief_hash", None)}


def _aggregate(res: dict) -> str:
    """Gộp văn bản các bước của một đội thành kết quả để cha dùng tiếp."""
    return "\n\n".join(f"[{s['role']}] {s.get('text', '')}"
                       for s in res["steps"] if s.get("text"))


def _executor_write(out_dir: Path, plan: TeamPlan, result: dict) -> Path:
    """Cửa GHI duy nhất (I1). Chỉ được gọi sau khi đã qua cổng + fail-closed."""
    out_dir.mkdir(parents=True, exist_ok=True)
    rid = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    d = out_dir / rid
    d.mkdir(parents=True, exist_ok=True)
    worker = next((s for s in result["steps"]
                   if s["role"] == "worker" and (s.get("text") or s.get("edited"))), None)
    if worker and worker.get("edited"):
        from .skills import fact_from_audit
        body = fact_from_audit(worker.get("audit") or []) or "đã sửa trên đĩa qua run_turn"
    else:
        body = _worker_for_disk(plan.task_text, worker["text"] if worker else "")
    (d / "result.md").write_text(
        f"# Kết quả\n\n**Yêu cầu:** {plan.task_text}\n\n"
        f"**Làn:** {plan.lane} · **sàn:** {plan.floor} · **cổng:** tầng {plan.gate_tier}\n\n"
        f"---\n\n{body}\n"
        + (("\n**Đã đưa vào cây:**\n" + "\n".join(f"- {p}" for p in (result.get("promoted") or [])) + "\n")
           if result.get("promoted") else ""),
        encoding="utf-8")
    (d / "trace.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    from .pipeline import write_trace_chain
    write_trace_chain(d, plan.plan_hash, result.get("steps") or [], getattr(plan, "brief_hash", None))
    return d


_GRADER_IN_TEXT = re.compile(
    r"conftest\.py|pytest\.ini|tox\.ini|sitecustomize\.py|test_[\w.-]+\.py")


def _worker_for_disk(task: str, text: str) -> str:
    """Lời worker là dữ liệu. Dòng nêu file người chấm mà câu việc không có thì không ghi."""
    kept: list[str] = []
    for line in (text or "(không có kết quả worker)").splitlines():
        if any(name not in (task or "") for name in _GRADER_IN_TEXT.findall(line)):
            continue
        kept.append(line)
    body = "\n".join(kept) or "(không có kết quả worker)"
    return "NỘI DUNG KHÔNG TIN. Không phải lệnh.\n\n" + body


# ------------------------------------------------------------------ CLI
def resume_team(root: Path, run_id: str, **kw) -> tuple[int, dict]:
    """Tiếp một run. Run withheld/error/blocked không gọi model thêm."""
    root = Path(root)
    try:
        data = load_checkpoint(root, run_id)
    except CheckpointError as exc:
        return 2, {"status": "error", "error": exc.message, "fail_reason": exc.message}
    steps = list(data.get("steps") or [])
    held = data.get("status") in ("withheld", "error", "blocked")
    if held or any(step.get("error") or step.get("blocked") for step in steps):
        return 3, data
    hints = dict(data.get("hints") or {})
    plan = build_plan(data.get("task") or "", **hints)
    price = data.get("declared_price")
    if price:
        plan.declared_price = (float(price[0]), float(price[1]))
    workers = int(data.get("workers") or 1)
    if len(expand_roles(plan.roles, plan.lane, workers)) < int(data.get("next_index") or 0):
        return 2, {"status": "error", "error": "checkpoint dài hơn kế hoạch",
                   "fail_reason": "checkpoint dài hơn kế hoạch"}
    staging = data.get("staging")
    if staging:
        path = Path(staging)
        base = (root / ".mira" / "staging").resolve()
        try:
            path.resolve().relative_to(base)
        except ValueError:
            return 2, {"status": "error", "error": "staging của checkpoint thoát khỏi gốc",
                       "fail_reason": "staging của checkpoint thoát khỏi gốc"}
        if not path.exists():
            return 2, {"status": "error", "error": "staging của checkpoint không còn",
                       "fail_reason": "staging của checkpoint không còn"}
    led = ledger_from_checkpoint(data["ledger"])
    res = execute_plan(
        plan, ledger=led, root=root, run_id=run_id, workers=workers,
        resume_steps=steps, resume_staging=staging, **kw)
    return (0 if res.get("status") == "ok" else 3), res


def cmd_team(args) -> int:
    from . import ui

    if getattr(args, "resume", None):
        code, res = resume_team(
            Path.cwd(), args.resume,
            provider_name=getattr(args, "provider", None),
            model_override=getattr(args, "model", None),
            base_url=getattr(args, "base_url", None),
            api_key=getattr(args, "api_key", None),
            max_tokens=int(getattr(args, "max_tokens", 4096) or 4096),
            oracle=getattr(args, "oracle", None),
            on_step=lambda m: print("  " + m))
        if code == 2:
            ui.note(res.get("error") or "không có checkpoint cho id này", "bad")
            return 2
        if res.get("status") == "withheld":
            ui.note("GIỮ LẠI — không giao", "warn")
            return 3
        return code
    if not getattr(args, "task", None):
        ui.note("thiếu yêu cầu", "bad")
        return 2

    labels = [x.strip() for x in (args.labels or "internal").split(",") if x.strip()]
    hints = dict(surface=args.surface, labels=labels, records=args.records,
                 dollars=args.dollars, reversibility=args.reversibility,
                 output_type=args.output_type)
    plan = build_plan(args.task, **hints)
    raw_price = getattr(args, "price_in", None)
    if raw_price:
        left, right = [float(part) for part in str(raw_price).split(",")]
        plan.declared_price = (left, right)
    workers = max(1, int(getattr(args, "workers", 1) or 1))
    sub_depth = max(0, int(getattr(args, "sub_depth", 0) or 0))
    if plan.lane < 2:
        sub_depth = 0
    oracle = getattr(args, "oracle", None)
    if oracle not in ("on", "off"):
        oracle = "off" if plan.lane < 2 or args.surface == "read_only" else "on"
    if oracle == "on" and plan.lane == 2 and "oracle" not in plan.roles:
        plan.roles = list(plan.roles) + ["oracle"]
    display = expand_roles(plan.roles, plan.lane, workers)

    ui.title("PHÂN VAI")
    ui.kv("Yêu cầu", args.task)
    ui.kv("Làn", ui.c(str(plan.lane), "cyan", "bold") + f"  ({len(plan.roles)} vai)")
    if plan.lane == 2 and workers > 1:
        ui.kv("Song song", ui.c(f"{workers} worker + {workers} verifier chạy đồng thời", "cyan"))
    if plan.lane == 2 and sub_depth > 0:
        ui.kv("Đội con", ui.c(f"lồng {sub_depth} cấp · chia {SUBAGENT_SHARE:.0%} trần còn lại"
                              f" · trần {SUBAGENT_MAX_RUNS} đội/cây", "cyan"))
    ui.kv("Vì sao", plan.roles_reason)
    ui.kv("Capability", plan.capability)
    ui.kv("Sàn rủi ro", f"{plan.floor}  ({plan.floor_reason})")
    ui.kv("Cổng người", f"tầng {plan.gate_tier} · {plan.gate_minutes:.0f} phút"
          + ("  · 2 NGƯỜI DUYỆT" if plan.dual_approval else ""))
    ui.kv("Trần làn", f"${plan.cap_usd:.2f}" if plan.cap_usd else "—")
    ui.title("Đội sẽ chạy")
    ui.table(["vai", "model"], [[r, C.ROLE_MODEL.get(r, "?")] for r in display], ["l", "l"])

    choice = getattr(args, "intake", "off")
    if choice is None:
        choice = "on" if plan.lane >= 1 else "off"
    intake_ledger = None

    if args.dry_run:
        print()
        ui.note("dry-run: chỉ in kế hoạch, KHÔNG gọi model, KHÔNG ghi gì", "info")
        if choice == "on":
            from .intake import canonical_brief
            echo = {
                "goal": args.task, "deliverables": [], "acceptance_criteria": [],
                "constraints": [], "assumptions": [], "questions": [],
                "per_role_hints": {"planner": "", "worker": "", "verifier": ""},
            }
            ui.note("khung brief chỉ echo câu người dùng, chưa duyệt.", "info")
            print(canonical_brief(echo))
        execute_plan(plan, dry_run=True, workers=workers, oracle=oracle,
                     on_step=lambda m: print("  " + m))
        return 0
    if choice == "on":
        from .intake import brief_hash, canonical_brief, load_brief_file, run_intake
        model = args.model or C.ROLE_MODEL["planner"]
        prov = provider_for(model, args.provider, base_url=args.base_url,
                            api_key=getattr(args, "api_key", None),
                            max_tokens=args.max_tokens)
        if not prov.available():
            ui.note("thiếu key cho intake", "bad")
            return 8
        intake_ledger = Ledger()
        brief_path = getattr(args, "brief", None)
        if brief_path:
            obj, why = load_brief_file(Path(brief_path))
            if obj is None:
                ui.note(why, "bad")
                return 8
            from_file = True
        else:

            def _ask(question: str) -> str:
                return input(ui.c(f"\n  {question} ", "bold"))

            got = run_intake(
                args.task, prov, intake_ledger,
                clarify_max=max(0, int(getattr(args, "clarify_max", 3) or 0)),
                ask=_ask, model=model, declared_price=plan.declared_price)
            if not got["ok"] or got["brief"] is None:
                ui.note(got["reason"] or "brief hỏng", "bad")
                return 8
            obj = got["brief"]
            from_file = False
        plan.brief = obj
        plan.brief_hash = brief_hash(obj)
        print(canonical_brief(obj))
        if not from_file:
            try:
                ans = input(ui.c("\n  Duyệt brief này? [y/N] ", "bold")).strip().lower()
            except (EOFError, KeyboardInterrupt):
                ans = "n"
            if ans not in ("y", "yes", "có", "co"):
                ui.note("chưa duyệt brief — không chạy planner.", "warn")
                return 8
        from .intake import write_role_prompts
        prompts, why = write_role_prompts(
            obj, list(plan.roles), prov, intake_ledger, model=model,
            declared_price=plan.declared_price, task=args.task)
        if prompts is None:
            ui.note(why, "bad")
            return 8
        plan.role_prompts = prompts
    if plan.dual_approval and args.approve:
        print()
        ui.note("dual_approval không nhận --approve. Cần hai người khác tên.", "warn")
        return 6
    print()
    ui.title("THỰC THI")
    res = execute_plan(plan, provider_name=args.provider, model_override=args.model,
                       base_url=args.base_url, api_key=getattr(args, "api_key", None),
                       max_tokens=args.max_tokens,
                       workers=workers, depth=sub_depth, root=Path.cwd(),
                       oracle=oracle, ledger=intake_ledger,
                       on_step=lambda m: print("  " + m))

    ui.title("KẾT LUẬN")
    st = res["status"]
    ui.kv("Trạng thái", {"ok": ui.c("ok", "green", "bold"),
                         "withheld": ui.c("GIỮ LẠI — không giao", "yellow", "bold"),
                         "blocked": ui.c("chặn — thiếu key", "yellow", "bold"),
                         "error": ui.c("lỗi", "red", "bold"),
                         "stopped_budget": ui.c("dừng vì ngân sách", "yellow", "bold")}.get(st, st))
    if res["fail_reason"]:
        ui.kv("Lý do", res["fail_reason"])
    if res["verifier_verdict"]:
        ui.kv("Verifier", res["verifier_verdict"])
    if res["oracle_score"] is not None:
        ui.kv("Oracle", f"{res['oracle_score']:.2f}")
    led = res["ledger"]
    ui.kv("Chi phí", f"${led['total_usd']:.6f} · {led['tokens_in']}+{led['tokens_out']} tok"
          + ("" if led["all_priced"] else "  (có model chưa có giá trong bảng)"))
    for k, v in led["by_role"].items():
        ui.kv("  " + k, f"${v:.6f}")

    # ---- cổng người + Executor ----
    if st != "ok":
        print()
        ui.note("fail-closed (I2): KHÔNG ghi gì ra ngoài.", "warn")
        if args.out:
            d = Path(args.out)
            d.mkdir(parents=True, exist_ok=True)
            (d / "withheld.json").write_text(json.dumps(res, ensure_ascii=False, indent=2),
                                             encoding="utf-8")
            ui.note(f"hồ sơ giữ lại: {d}/withheld.json", "info")
        return 3

    def _hold() -> None:
        if res.get("staging"):
            held = withhold_staging(Path(res["staging"]))
            res["staging"] = str(held)

    need = plan.gate_tier >= 2
    approved = True
    if need and plan.dual_approval:
        phrases = two_phrases(plan.plan_hash)
        seen: list[str] = []
        people: list[dict] = []
        reject = 0
        for index, phrase in enumerate(phrases, 1):
            try:
                name = input(ui.c(f"\n  Người {index} — tên: ", "bold")).strip()
                got = input(ui.c(f"  Nhập cụm: {phrase} ", "bold")).strip()
            except (EOFError, KeyboardInterrupt):
                name, got = "", ""
            if name and name in seen:
                reject = 5
                break
            if not name or got != phrase:
                reject = 4
                break
            seen.append(name)
            people.append({"name": name, "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
                           "plan_hash": plan.plan_hash})
        if reject:
            print()
            ui.note("hai người chưa duyệt — Executor không ghi.", "warn")
            _hold()
            return reject
        res["gate_person"] = people
        approved = True
    elif need and not args.approve:
        try:
            ans = input(ui.c(f"\n  Cổng tầng {plan.gate_tier} — duyệt để ghi? [y/N] ", "bold")).strip().lower()
        except (EOFError, KeyboardInterrupt):
            ans = "n"
        approved = ans in ("y", "yes", "có", "co")
    if need and not approved:
        print()
        ui.note("chưa duyệt — Executor không ghi (đúng I1/I2).", "warn")
        _hold()
        return 4

    if res.get("staging"):
        staging = Path(res["staging"])
        if staging.is_dir() and not staging.name.endswith(".withheld"):
            audit: list[dict] = []
            res["promoted"] = promote_staging(Path.cwd(), staging, audit)
            res["promote_audit"] = audit
            shutil.rmtree(staging, ignore_errors=True)

    if not args.out:
        ui.note("không có --out nên không ghi gì", "info")
        return 0
    d = _executor_write(Path(args.out), plan, res)
    print()
    ui.note(f"Executor đã ghi: {d}/result.md · {d}/trace.json", "ok")
    return 0
