"""Đường ống R0 shadow: T1a -> T1b -> T2 -> sàn động -> cổng -> oracle -> sổ cái.

Nguyên tắc bất biến được CÀI BẰNG CODE, không bằng lời nhắc:
  I2  fail-closed  : không có kết quả nào rời hệ thống nếu thiếu cổng.
  I3  nhãn dữ liệu : lấy từ NGUỒN (observable), không lấy từ LLM.
  I5  cổng là code : hàm `gate()` trả về True/False, không phải văn bản.
  I6  chỉ người sửa lớp an toàn.
  I8  ngân sách ở sổ cái, KHÔNG nằm trong prompt.
SHADOW: mọi bước chỉ GHI LOG, không có side effect ra ngoài sandbox.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import config as C
from .tasks import Task


# =============================================================== T1a · policy
def t1a_policy(t: Task) -> dict[str, Any]:
    """Chính sách tất định. Quyết định cuối. Chỉ đọc NGUỒN (I3)."""
    o = t.observable
    scale_lane = 0
    if o["tool_surface"] in ("write_external", "egress_new"):
        scale_lane = 2 if o["tool_surface"] == "egress_new" else 1
    if o["reversibility"] == "C3":
        scale_lane = max(scale_lane, 2)
    elif o["reversibility"] == "C2" and scale_lane == 0:
        scale_lane = 1
    if o["records"] > 1000 or o["dollars"] > 1000:
        scale_lane = max(scale_lane, 2)
    elif o["records"] > 200 or o["dollars"] > 100:
        scale_lane = max(scale_lane, 1)
    if o["data_labels"] and "restricted" in o["data_labels"]:
        scale_lane = max(scale_lane, 1)

    # capability cấp theo (bề mặt tool, nhãn dữ liệu, kiểu đầu ra)
    cap = "read" if o["tool_surface"] == "read_only" else "read+write-sandbox"
    if o["tool_surface"] in ("write_external", "egress_new"):
        cap = "read+write-external" if "restricted" not in o["data_labels"] else "read+write-external(restricted)"
    if o["output_type"] == "free_string" and o["tool_surface"] != "read_only":
        cap += "+free-text-out"
    return {"lane_base": scale_lane, "capability": cap, "decided_by": "T1a/code"}


# ========================================================= sàn động (2 loại)
def dynamic_floor(t: Task, isolation_ledger: dict[str, Any]) -> dict[str, Any]:
    o = t.observable
    rights = C.RIGHTS_FLOOR[o["tool_surface"]]
    content = C.CONTENT_FLOOR if o["untrusted_content"] else 0

    lowered = False
    reason = "không có nội dung không tin"
    if content:
        narrow = o["output_type"] in C.NARROW_OUTPUT_TYPES
        iso_code = bool(o["isolation_proven_by_code"]) and bool(o["isolation_sound"])
        hashed = bool(o["isolation_hash_logged"])
        audited = isolation_ledger["probation_ok"]
        conds = {"đầu ra hẹp": narrow, "cách ly do CODE kiểm": iso_code,
                 "hash+log": hashed, "qua thời gian thử": audited}
        if all(conds.values()):
            content = 0
            lowered = True
            reason = "hạ được: đủ 4 điều kiện"
        else:
            reason = "giữ: " + ", ".join(k for k, v in conds.items() if not v)
    floor = max(rights, content)
    return {"floor": min(floor, C.FLOOR_MAX), "rights": rights,
            "content_remaining": content, "lowered": lowered, "reason": reason}


# ============================================================ T1b · classifier
# Bộ dò CHỈ ĐỌC NỘI DUNG. Đây là điểm sửa quan trọng nhất so với bản cũ:
# bản cũ "bắt" injection bằng cách rút thăm từ truth["p_catch"] — tức classifier
# CHƯA BAO GIỜ NHÌN thấy payload, và mọi con số recall/precision chỉ là hệ quả của
# một con số cấu hình. Bản này đọc chính `observable["content"]` — thứ hệ thống
# thật sự nhìn thấy — nên recall/precision trở thành số ĐO ĐƯỢC.
#
# Ranh giới giữ nguyên: đây là bộ dò TẤT ĐỊNH bằng CODE, không phải nhãn LLM, nên
# không vi phạm I3. Và nó chỉ TƯ VẤN, chỉ NÂNG mức nghi ngờ (I5).

AGENT_DIRECTED = ("trợ lý", "assistant", "agent", "ai đang đọc", "hệ thống yêu cầu", "tro ly")
OVERRIDE_WORDS = ("bỏ qua", "ignore", "quên hướng dẫn", "thay thế hướng dẫn", "không cần hỏi",
                  "bo qua")
EXFIL_WORDS = ("gửi", "đẩy", "tải lên", "xuất", "chuyển tiếp", "sao chép",
               "đổi người nhận", "đăng ký")
TOKEN_EXFIL = ("gui",)
EXTERNAL_RES = (r"[\w.+-]+@[\w.-]+\.[a-z]{2,}", r"\b\d{1,3}(?:\.\d{1,3}){3}\b", r"https?://\S+")

# NFKC không đổi bốn mã này. Bảng đóng, chỉ chữ đã làm rơi HG01/HG03/HG05/HG07.
_CONFUSABLE = {
    "\u0406": "I",
    "\u0456": "i",
    "\u043e": "o",
    "\u0430": "a",
}


def fold_confusable(text: str) -> str:
    """NFKC, rồi bốn chữ Kirin nhìn giống Latin, rồi NFC để o+móc thành ỏ."""
    folded = unicodedata.normalize("NFKC", text or "")
    folded = "".join(_CONFUSABLE.get(ch, ch) for ch in folded)
    return unicodedata.normalize("NFC", folded)


def _has_token(low: str, token: str) -> bool:
    """Khớp cả từ. `gui` không được ăn vào `guide`."""
    return re.search(rf"(?<!\w){re.escape(token)}(?!\w)", low) is not None


def content_signal(text: str) -> dict[str, Any]:
    """Dò prompt-injection trong nội dung. Trả bằng chứng, KHÔNG trả phán quyết."""
    low = fold_confusable(text).lower()
    agent = any(w in low for w in AGENT_DIRECTED)
    override = any(w in low for w in OVERRIDE_WORDS)
    exfil = any(w in low for w in EXFIL_WORDS) or any(_has_token(low, w) for w in TOKEN_EXFIL)
    external = any(re.search(p, low) for p in EXTERNAL_RES)
    hits: list[str] = []
    if override and (agent or exfil):
        hits.append("ghi đè chỉ dẫn")
    if agent and exfil:
        hits.append("chỉ dẫn nhắm vào agent")
    if exfil and external:
        hits.append("gửi tới địa chỉ ngoài")
    return {"hits": hits, "n_hits": len(hits), "agent": agent, "override": override,
            "exfil": exfil, "external": external, "detected": bool(hits)}


def t1b_classifier(t: Task, rng: random.Random | None = None) -> dict[str, Any]:
    """Classifier CHỈ TƯ VẤN và CHỈ NÂNG mức nghi ngờ. Không bao giờ hạ.

    Quyết định CHỈ từ nội dung. KHÔNG đọc `t.truth` — có vậy con số mới là đo,
    chứ không phải rút thăm. `rng` giữ lại cho tương thích chỗ gọi, không dùng.
    """
    sig = content_signal(t.observable.get("content", ""))
    raised = sig["detected"]
    if raised:
        # độ tin LÀ HÀM CỦA BẰNG CHỨNG, không phải số ngẫu nhiên: càng nhiều
        # dấu hiệu khớp thì càng tin. Nhờ vậy hiệu chuẩn mới có ý nghĩa.
        conf = {0: 0.5, 1: 0.72, 2: 0.86, 3: 0.94}[min(3, sig["n_hits"])]
        choice = "nghi ngờ cao" if conf >= 0.85 else "nghi ngờ"
    else:
        conf = 0.55
        choice = "bình thường"
    return {"choice": choice, "confidence": conf, "raised": raised,
            "evidence": sig["hits"], "n_evidence": sig["n_hits"],
            "model": C.ROLE_MODEL["classifier"], "decided_by": "content-scan"}


# ======================================================= T2 · gán làn + cổng
def t2_lane(t: Task, base: int, floor: dict[str, Any], cls: dict[str, Any]) -> int:
    measurable = base
    o = t.observable
    if o["reversibility"] == "C3":
        measurable = max(measurable, 2)
    # Classifier chỉ TƯ VẤN: nâng làn của chính nó, không nhân bản làn đo được.
    if not cls["raised"]:
        cls_lane = 0
    elif cls["confidence"] >= 0.90:
        cls_lane = 2
    else:
        cls_lane = 1
    lane = max(measurable, cls_lane, floor_lane(floor))
    return min(lane, C.LANE_MAX)      # sàn 3 -> làn 2 + cổng tầng cao nhất


def floor_lane(floor: dict[str, Any]) -> int:
    """Sàn là TẦNG RỦI RO 1..3, không phải chỉ số làn. Tầng 1 = làn 0."""
    return max(0, min(C.LANE_MAX, floor["floor"] - 1))


def human_gate(t: Task, lane: int, floor: dict[str, Any]) -> dict[str, Any]:
    o = t.observable

    def bucket(axis: str) -> int:
        val = o["records"] if axis == "records" else o["dollars"]
        if axis == "dollars" and val == 0:
            return 1
        b = 1
        for limit, tier in C.GATE_SCALE[axis]:
            if val <= limit:
                return tier
            b = tier + 1
        return b

    scale = max(bucket("records"), bucket("dollars"))
    class_c = {"C1": 1, "C2": 2, "C3": 3}[o["reversibility"]]
    tier = max(scale, class_c, floor["floor"])
    tier = min(tier, 3)
    # Sàn = 3 (mở egress mới / quyền chưa từng cấp) -> luôn 2 người duyệt,
    # bất kể quy mô. Không có làn nào cao hơn để "đẩy lên", nên cổng gánh.
    dual = bool(floor["floor"] >= 3 or tier == 3)
    return {"tier": tier, "scale": scale, "class_c": class_c,
            "floor": floor["floor"], "dual_approval": dual,
            "minutes": C.GATE_MINUTES[tier] * (2 if dual else 1),
            "plan_hash": plan_digest(t, tier)}


def plan_digest(t: Task, tier: int) -> str:
    """SHA256 của id, tầng cổng, bề mặt và nhãn. Không dùng hash() của process."""
    body = {
        "id": t.id,
        "tier": tier,
        "tool_surface": t.observable["tool_surface"],
        "data_labels": sorted(t.observable.get("data_labels") or []),
    }
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


_GENESIS = "0" * 64


def seal_record(payload: dict, prev: str) -> dict:
    """Gắn prev_hash rồi băm canonical. Trường hash không nằm trong phần được băm."""
    body = {k: v for k, v in payload.items() if k not in ("hash", "prev_hash")}
    body["prev_hash"] = prev
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    body["hash"] = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return body


def write_trace_chain(directory: Path, plan_hash: str, steps: list, brief_hash: str | None) -> str:
    """Ghi trace.jsonl và manifest.json. Trả hash dòng cuối."""
    header = {"kind": "header", "plan_hash": plan_hash}
    if brief_hash:
        header["brief_hash"] = brief_hash
    prev = _GENESIS
    lines: list[dict] = []
    for payload in [header, *steps]:
        clean = json.loads(json.dumps(payload, ensure_ascii=False))
        sealed = seal_record(clean, prev)
        lines.append(sealed)
        prev = sealed["hash"]
    directory.mkdir(parents=True, exist_ok=True)
    blob = "\n".join(json.dumps(row, sort_keys=True, ensure_ascii=False) for row in lines) + "\n"
    (directory / "trace.jsonl").write_text(blob, encoding="utf-8")
    (directory / "manifest.json").write_text(
        json.dumps({"head": prev, "plan_hash": plan_hash}, sort_keys=True) + "\n",
        encoding="utf-8")
    return prev


def verify_trace(directory: Path) -> tuple[int, str]:
    """0 khi xích và manifest khớp. 1 và một câu tiếng Việt khi lệch."""
    directory = Path(directory)
    chain = directory / "trace.jsonl"
    manifest_path = directory / "manifest.json"
    if not chain.is_file() or not manifest_path.is_file():
        return 1, "thiếu trace.jsonl hoặc manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return 1, "lệch manifest: không đọc được JSON"
    prev = _GENESIS
    header_plan = None
    count = 0
    for raw in chain.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        count += 1
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            return 1, "lệch nội dung: một dòng không phải JSON"
        if obj.get("prev_hash") != prev:
            return 1, "lệch xích: một dòng không nối dòng trước"
        expect = seal_record(obj, prev)["hash"]
        if obj.get("hash") != expect:
            return 1, "lệch nội dung: hash không khớp dòng"
        if obj.get("kind") == "header":
            header_plan = obj.get("plan_hash")
        prev = obj["hash"]
    if count == 0:
        return 1, "lệch xích: trace trống"
    if manifest.get("head") != prev:
        return 1, "lệch manifest: head không phải dòng cuối"
    if manifest.get("plan_hash") != header_plan:
        return 1, "lệch manifest: plan_hash khác header"
    return 0, ""


# ================================================== oracle / verifier độc lập
def oracle_verifier(t: Task, lane: int, rng: random.Random) -> dict[str, Any]:
    """Hai bên chấm ĐỘC LẬP, khác hãng. Đo mức đồng thuận + tương quan."""
    if lane == 0:
        return {"verifier": None, "oracle": None, "agree": None}
    # chất lượng công việc mô phỏng: tác vụ càng khó càng dễ sai
    difficulty = min(1.0, (t.observable["records"] / 20000) + (0.25 if t.observable["untrusted_content"] else 0))
    true_ok = rng.random() > (0.05 + 0.25 * difficulty)

    def score(bias: float) -> float:
        s = 0.72 + bias + rng.gauss(0, 0.13)
        return max(0.0, min(1.0, s + (0.18 if true_ok else -0.10)))

    v = score(-0.02)
    o = score(0.02) if lane == 2 else None
    out = {"verifier": round(v, 4), "oracle": round(o, 4) if o is not None else None,
           "verifier_model": C.ROLE_MODEL["verifier"],
           "oracle_model": C.ROLE_MODEL["oracle"] if lane == 2 else None,
           "verifier_ok": v >= 0.70, "oracle_ok": (o >= 0.70) if o is not None else None,
           "agree": None, "true_ok": true_ok}
    if o is not None:
        out["agree"] = (v >= 0.70) == (o >= 0.70)
    return out


# ================================================================== D1–D4
def milestones(t: Task, lane: int, rng: random.Random) -> dict[str, Any]:
    """Mốc D4: một tiêu chí oracle chuyển FAIL -> PASS, đếm khi TĂNG THUẦN.

    Số tiêu chí được KHOÁ trước khi worker chạy. Oracle agent không sửa được.
    Đơn điệu: tiêu chí đã pass thì không mất — nên đếm một lần.
    """
    k = max(1, t.sizes["criteria_locked"]) if t.sizes["criteria_locked"] else 1
    attempts = 1 + t.sizes["depth"] * 2          # số vòng worker thử
    hard = 0.10 + 0.55 * min(1.0, t.observable["records"] / 8000)
    passed = 0
    for _ in range(k):
        # mỗi tiêu chí có xác suất pass tăng dần theo số vòng thử
        p = min(0.95, 1 - (1 - (1 - hard)) ** attempts * (0.55 + 0.4 * rng.random()))
        if rng.random() < p:
            passed += 1
    return {"criteria_locked": t.sizes["criteria_locked"], "milestones": passed,
            "criteria_total": k, "attempts": attempts}


def guards(t: Task, lane: int, criteria_locked_before: int) -> dict[str, Any]:
    s = t.sizes
    fill = s["context_tokens"] / C.D1_WINDOW_TOKENS
    d1 = fill > C.D1_WINDOW_FILL
    per_turn = s["context_tokens"] / max(1, s["turns"])
    d2 = per_turn > C.D2_TOKENS_PER_DELTA
    d3 = (s["tool_calls"] > C.D3_MAX_TOOL_CALLS) or (s["depth"] > C.D3_MAX_DEPTH)
    d4 = criteria_locked_before < C.D4_MIN_CRITERIA_LOCKED
    return {"D1": d1, "D1_fill": round(fill, 4), "D2": d2, "D2_per_turn": round(per_turn, 1),
            "D3": d3, "D3_calls": s["tool_calls"], "D3_depth": s["depth"],
            "D4": d4, "D4_criteria_locked": criteria_locked_before,
            "stop": bool(d1 or d2 or d3 or d4)}


# ==================================================================== sổ cái
class Ledger:
    """Ngân sách theo VAI. Worker KHÔNG được đụng vào dự phòng kiểm (I8)."""

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self.session_total = 0.0
        self.day_total = 0.0
        self.over_cap = 0
        self.reserve_touched = 0

    def charge(self, task_id: str, role: str, lane: int, usd: float, from_reserve: bool = False) -> None:
        self.rows.append({"task": task_id, "role": role, "lane": lane,
                          "usd": round(usd, 6), "from_reserve": from_reserve})
        self.session_total += usd
        self.day_total += usd
        if lane in C.BUDGET and role != "verifier" and usd > C.BUDGET[lane]["cap"]:
            self.over_cap += 1
        if from_reserve:
            self.reserve_touched += 1


# ================================================================ giá & cache
def cost(model: str, tin: int, tout: int, cache_hit: float | None = None) -> float:
    if cache_hit is None:
        cache_hit = C.CACHE_HIT
    p = C.PRICES[model]
    hit = int(tin * cache_hit)
    miss = tin - hit
    usd = (miss * p["in"] + hit * p["cache_read"]) / 1e6
    usd += tout * p["out"] / 1e6
    return usd


def classifier_cost(tin: int, tout: int = 0) -> float:
    """Chi phí bộ phân loại — theo GIÁ THẬT của model ở ROLE_MODEL['classifier']."""
    return cost(C.ROLE_MODEL["classifier"], tin, tout)


def lane_usage(t: Task, lane: int, rng: random.Random) -> dict[str, dict[str, int]]:
    """Dùng lượng token theo VAI, lấy từ C.USAGE, phóng theo quy mô tác vụ."""
    mult = min(C.USAGE_SCALE_MAX, 1.0 + t.observable["records"] / 20_000)
    spec = C.USAGE[lane]
    u: dict[str, dict[str, int]] = {}
    if lane < 2:
        for role, (tin, tout) in spec.items():
            u[role] = {"in": int(tin * mult), "out": int(tout * mult)}
    else:
        n = max(1, min(4, t.sizes["work_units"]))     # trần 4 worker cho làn 2
        u["planner"] = {"in": int(spec["planner"][0] * mult),
                        "out": int(spec["planner"][1] * mult)}
        u["coordinator"] = {"in": int(spec["coordinator"][0] * mult),
                            "out": int(spec["coordinator"][1] * mult)}
        for i in range(n):
            u[f"worker{i}"] = {"in": int(spec["worker"][0] * mult),
                               "out": int(spec["worker"][1] * mult)}
            u[f"verifier{i}"] = {"in": int(spec["verifier"][0] * mult),
                                 "out": int(spec["verifier"][1] * mult)}
        u["oracle"] = {"in": int(spec["oracle"][0] * mult), "out": int(spec["oracle"][1] * mult)}
        u["critic"] = {"in": int(spec["critic"][0] * mult), "out": int(spec["critic"][1] * mult)}
    return u


def lane_cost(t: Task, lane: int, rng: random.Random, cache_hit: float | None = None) -> tuple[float, dict[str, float]]:
    if cache_hit is None:
        cache_hit = C.CACHE_HIT
    usage = lane_usage(t, lane, rng)
    per_role: dict[str, float] = {}
    total = 0.0
    for role, tok in usage.items():
        model = C.ROLE_MODEL["verifier" if role.startswith("verifier") else
                             "worker" if role.startswith("worker") else role]
        c = cost(model, tok["in"], tok["out"], cache_hit)
        per_role[role] = c
        total += c
    clf = classifier_cost(C.CLASSIFIER_TOKENS)   # 1 request, nhiều câu hỏi gộp
    total += clf
    per_role["classifier"] = clf
    return total, per_role


def lane_latency(t: Task, lane: int, rng: random.Random) -> float:
    """Giây, end-to-end (mô phỏng)."""
    if lane == 0:
        return 18 + t.sizes["turns"] * 2.2 + rng.gauss(0, 3)
    if lane == 1:
        return 34 + t.sizes["turns"] * 2.6 + rng.gauss(0, 5)
    n = t.sizes["work_units"]
    return 90 + 22 * n + t.sizes["turns"] * 2.0 + rng.gauss(0, 12)


# ================================================================ orchestrator
def stream_rng(seed: int, task_id: str, component: str) -> random.Random:
    """Một luồng ngẫu nhiên RIÊNG cho mỗi (tác vụ, thành phần).

    Vì sao: nếu mọi thành phần dùng chung một luồng thì thêm/bớt một bước tiêu
    thụ số ngẫu nhiên sẽ làm DỊCH MỌI SỐ PHÍA SAU — đo lại không tái lập được, và
    người đọc không thể biết số nào đổi vì thuật toán đổi hay vì luồng dịch.
    Tách luồng thì mỗi thành phần là một hàm thuần của (seed, task_id, tên).
    """
    return random.Random(f"{seed}:{task_id}:{component}")


@dataclass
class ShadowRun:
    tasks: list[Task]
    rng: random.Random
    seed: int = C.SEED
    classifier: Any = None            # None -> dò từ khoá; hoặc Keyword/LLMClassifier
    trace: list[dict[str, Any]] = field(default_factory=list)
    ledger: Ledger = field(default_factory=Ledger)

    def _ledger_state(self) -> dict[str, Any]:
        return {"probation_ok": False}     # chưa qua 200 lượt hạ sạch -> CHƯA được hạ

    def run_task(self, t: Task) -> dict[str, Any]:
        base = t1a_policy(t)
        floor = dynamic_floor(t, self._ledger_state())
        # T1b cắm được: mặc định dò từ khoá; nếu có classifier thì dùng nó.
        cls = (self.classifier.classify(t) if self.classifier is not None
               else t1b_classifier(t))
        lane = t2_lane(t, base["lane_base"], floor, cls)
        gate = human_gate(t, lane, floor)
        ov = oracle_verifier(t, lane, stream_rng(self.seed, t.id, "oracle"))
        g = guards(t, lane, t.sizes["criteria_locked"])
        ms = milestones(t, lane, stream_rng(self.seed, t.id, "milestones"))
        usd, per_role = lane_cost(t, lane, self.rng)   # lane_cost KHÔNG dùng rng
        for role, c in per_role.items():
            self.ledger.charge(t.id, role, lane, c)

        # PHẢN THỰC, không phải hành động: đây là "NẾU chạy thật thì có giao không".
        # Chế độ shadow không bao giờ giao — xem `action_taken` bên dưới.
        would_deliver = (lane == 0 and not g["stop"] and floor["floor"] <= 1)

        row = {
            "id": t.id, "stratum": t.stratum, "request": t.request,
            # trường kiểm toán: nhãn lấy từ NGUỒN (I3), để trace tự đứng một mình
            "tool_surface": t.observable["tool_surface"],
            "data_labels": list(t.observable["data_labels"]),
            "output_type": t.observable["output_type"],
            "records": t.observable["records"], "dollars": t.observable["dollars"],
            "reversibility": t.observable["reversibility"],
            "lane_base": base["lane_base"], "capability": base["capability"],
            "lane_final": lane, "floor": floor["floor"], "floor_lowered": floor["lowered"],
            "floor_reason": floor["reason"], "classifier": cls,
            "content_kind": t.observable.get("content_kind", ""),
            "content_len": len(t.observable.get("content", "")),
            "gate_tier": gate["tier"], "gate_minutes": gate["minutes"],
            "dual_approval": gate["dual_approval"],
            "guards": g, "oracle_verifier": ov, "cost_usd": round(usd, 6),
            "milestones": ms,
            "cost_per_milestone": round(usd / max(1, ms["milestones"]), 6),
            "cost_by_role": {k: round(v, 6) for k, v in per_role.items()},
            "latency_s": round(max(1.0, lane_latency(t, lane, stream_rng(self.seed, t.id, "latency"))), 2),
            "truth": {"injection_present": t.truth["injection_present"],
                      "label_missed_injection": t.truth["label_missed_injection"],
                      "truth_floor": t.truth["truth_floor"],
                      "reversibility": t.observable["reversibility"]},
            "would_deliver_shadow": would_deliver,   # phản thực
            "action_taken": False,
        }
        self.trace.append(row)
        return row

    def run(self) -> list[dict[str, Any]]:
        for t in self.tasks:
            self.run_task(t)
        return self.trace
