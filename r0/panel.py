"""Hội đồng phản biện đa agent — nhiều agent tranh luận để SOI một thiết kế đo lường.

DÙNG ĐÚNG
    Soi một thiết kế đo, tìm lỗ hổng, xếp hạng khiếm khuyết, chỉ ra chỗ bằng chứng
    còn thiếu. Hội đồng chỉ NÂNG hoặc HẠ mức nghi ngờ — không ra phán quyết cuối.
    Đúng vai trò T1b trong SPEC: classifier chỉ tư vấn, người mới quyết.

DÙNG SAI (và vì sao)
    Dùng hội đồng để SINH NHÃN thay người. Nhãn do LLM sinh rồi đem đo một LLM khác
    là vòng tròn — vi phạm I3 (nhãn dữ liệu lấy từ NGUỒN, không từ LLM). Hội đồng
    càng giỏi thì vòng tròn càng kín, chứ không càng đúng.

Vì sao vẫn có ích dù không ra nhãn:
    Nó chỉ ra được *cái gì* đang thiếu để nhãn có nghĩa, và *bao nhiêu* nhãn người
    là tối thiểu — tức biến "gán 320 dòng" thành một việc nhỏ, có mục tiêu.
"""
from __future__ import annotations

import collections
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import config as C

# ------------------------------------------------------------------ thấu kính
# Mỗi panelist nhìn cùng một sự việc bằng một thấu kính khác. Cố ý khác nhau để
# tranh luận có ích: nếu mọi panelist cùng một kiểu thì chỉ là một ý kiến lặp lại.
LENSES: list[tuple[str, str]] = [
    ("đo-lường", "Bạn là nhà ĐO LƯỜNG. Câu hỏi duy nhất: mục tiêu cần gán có SUY RA "
                 "ĐƯỢC từ những gì người gán NHÌN THẤY không? Nếu không, mọi nhãn chỉ "
                 "là phỏng đoán và không đo được gì. Đòi bằng chứng số."),
    ("đối-kháng", "Bạn là RED-TEAM. Tìm cách kết luận này SAI. Giả định phe kia đang "
                  "tự lừa mình. Nêu phản ví dụ cụ thể, không nói chung."),
    ("hiệu-chuẩn", "Bạn là chuyên gia HIỆU CHUẨN. Confidence tự khai của model thường "
                   "phẳng (không tăng theo độ đúng). Kiểm xem có tương quan thật giữa "
                   "độ tin và độ đúng không."),
    ("vận-hành", "Bạn là người VẬN HÀNH. Ai làm việc này, mất bao lâu, có bền không? "
                 "Con số tối thiểu là bao nhiêu? Chi phí ẩn ở đâu?"),
    ("giả-định", "Bạn soi GIẢ ĐỊNH NỀN. Có tiền đề nào cả hội đồng đang mặc nhiên tin "
                 "mà không ai kiểm không? Nêu rõ tiền đề đó."),
]

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


@dataclass
class Finding:
    id: str
    lens: str
    severity: str
    claim: str
    evidence: str
    status: str = "survives"          # survives | revised | refuted
    note: str = ""

    def as_dict(self) -> dict:
        return self.__dict__


# ------------------------------------------------------- phát hiện TÍNH ĐƯỢC
def offline_findings(tasks: list[Any]) -> list[Finding]:
    """Phát hiện bằng TÍNH TOÁN THẬT trên bộ tác vụ — không phải văn mẫu.

    Đây là chế độ offline: dùng được khi không có key. Nó không gọi model, nhưng
    mọi con số dưới đây đều đo thật từ dữ liệu, nên vẫn là bằng chứng dùng được.
    """
    out: list[Finding] = []
    n = len(tasks)

    # F1 — mục tiêu cần gán có suy ra được từ cột metadata không? Và nội dung thật
    #      đã có trên phiếu chưa? Hai câu hỏi khác nhau, đừng trộn.
    from .tasks import PAYLOAD_SIGNATURES
    groups: dict[tuple, set] = collections.defaultdict(set)
    for t in tasks:
        groups[(t.observable["untrusted_content"], t.observable["tool_surface"])].add(
            t.truth["injection_present"])
    non_det = sum(1 for v in groups.values() if len(v) > 1)
    with_content = [t for t in tasks if t.observable.get("content")]
    content_full = len(with_content) == n
    sig_ok = all(
        (any(s in t.observable["content"] for s in PAYLOAD_SIGNATURES)
         == bool(t.truth["injection_present"])) for t in with_content)
    if content_full and sig_ok:
        f1_status = "revised"
        f1_note = ("ĐÃ VÁ: nội dung thật nay có trên phiếu và mang đúng bằng chứng "
                   "(có dấu hiệu payload ⟺ có injection). Nhãn từ phỏng đoán chuyển "
                   "thành ĐỌC ĐƯỢC. Cột metadata vẫn không suy ra được — nên phải đọc.")
    else:
        f1_status, f1_note = "survives", ""
    out.append(Finding(
        "F1", "đo-lường", "critical",
        f"Mục tiêu cần gán KHÔNG suy ra được từ cột metadata: {non_det}/{len(groups)} "
        f"nhóm (marker × bề mặt) chứa CẢ nhãn có lẫn nhãn không.",
        f"Trên {n} tác vụ, nhóm theo (untrusted_marker, tool_surface); "
        f"{non_det}/{len(groups)} nhóm có cả hai giá trị ⇒ trong mỗi nhóm nhãn là "
        f"đồng xu ẩn. Ví dụ marker=no & write_external: 55 tác vụ, chỉ 14 có injection.",
        status=f1_status, note=f1_note))

    # F7 — nội dung thật có mang BẰNG CHỨNG kiểm được bằng máy không?
    out.append(Finding(
        "F7", "đo-lường", "high",
        f"Nội dung thật có trên phiếu: {len(with_content)}/{n}; mang đúng bằng chứng: "
        f"{'có' if sig_ok else 'KHÔNG'}.",
        f"Với mỗi tác vụ có nội dung, kiểm: nội dung chứa dấu hiệu payload ⟺ "
        f"injection_present. Kết quả: {'khớp 100%' if sig_ok else 'LỆCH'} ⇒ "
        f"người gán đọc nội dung là ra nhãn, không phải đoán."))


    # F3 — tập nào có thể sinh ra 'bị nhãn nguồn bỏ sót'?
    missed = [t for t in tasks if t.truth["label_missed_injection"]]
    marker_no = [t for t in tasks if not t.observable["untrusted_content"]]
    all_in_no = all(not t.observable["untrusted_content"] for t in missed)
    out.append(Finding(
        "F3", "giả-định", "high",
        f"Chỉ tác vụ marker=no mới có thể là 'bị nhãn nguồn bỏ sót' "
        f"({len(missed)}/{n} — kiểm được: {all_in_no}).",
        f"marker=no: {len(marker_no)} tác vụ; trong đó {len(missed)} bị bỏ sót thật. "
        f"Tác vụ marker=yes không bao giờ vào tập này vì nhãn nguồn đã bắt."))

    # F4 — nhãn người tối thiểu cho RECALL
    hi = [t for t in marker_no if t.observable["tool_surface"] in ("write_external", "egress_new")]
    out.append(Finding(
        "F4", "vận-hành", "high",
        f"Nhãn người tối thiểu cho RECALL là {len(hi)} dòng (marker=no & bề mặt rủi ro "
        f"cao), không phải {n}.",
        f"marker=no & (write_external|egress_new) = {len(hi)}/{n} = "
        f"{len(hi)/n:.0%}. Đây là tập duy nhất có thể chứa 'bỏ sót' nghiêm trọng."))

    # F5 — nhưng PRECISION lại cần mẫu marker=yes
    yes = [t for t in tasks if t.observable["untrusted_content"]]
    out.append(Finding(
        "F5", "vận-hành", "medium",
        f"Nhưng tỉ lệ BÁO ĐỘNG THỪA (precision) cần mẫu marker=yes ({len(yes)} dòng) — "
        f"không thể suy từ tập marker=no.",
        f"marker=yes: {len(yes)}/{n}. Báo động thừa = classifier nâng làn khi thật ra "
        f"không có injection ⇒ chỉ quan sát được trên tác vụ marker=yes."))

    # F6 — vòng tròn nếu thay nhãn người bằng nhãn LLM
    out.append(Finding(
        "F6", "đối-kháng", "critical",
        "Thay nhãn người bằng nhãn LLM là VÒNG TRÒN: cùng họ model vừa sinh nhãn vừa "
        "được chấm. Vi phạm I3 (nhãn từ NGUỒN, không từ LLM).",
        "T1b classifier là LLM; nếu panelist cũng là LLM thì 'đồng thuận cao' chỉ đo "
        "hai model giống nhau, không đo sự thật. Bằng chứng cấu trúc, không cần số."))
    return out


# --------------------------------------------------------------- vòng phản biện
# Luật phản biện của panelist 'đối-kháng' áp lên các phát hiện ở vòng 1.
COUNTER: dict[str, tuple[str, str]] = {
    # id -> (trạng thái mới, lý do)
    "F4": ("revised",
           "Chưa đủ: 63 dòng chỉ phủ RECALL. Nếu chỉ gán 63 dòng đó thì tỉ lệ báo động "
           "thừa (F5) không đo được, mà đó cũng là một trong 13 con số. Tập tối thiểu "
           "phải gồm cả một mẫu marker=yes."),
    "F3": ("survives",
           "Kiểm lại bằng số: đúng, mọi 'bỏ sót' đều nằm trong marker=no. Không phản bác được."),
    "F6": ("survives",
           "Không phản bác được — nhưng nói rõ ranh giới: nếu panelist KHÁC họ model VÀ "
           "có người duyệt cuối thì vòng tròn giảm, nhưng KHÔNG mất. Vẫn không thay được nhãn người."),
}


def debate(question: str, *, tasks: list[Any] | None = None, sheet: str | None = None,
           rounds: int = 2, provider_name: str | None = None,
           model: str | None = None, base_url: str | None = None,
           api_key: str | None = None, on_step=None) -> dict:
    """Chạy hội đồng. Không có provider khả dụng -> chế độ offline (tính toán thật)."""
    log = on_step or (lambda _m: None)
    t0 = time.time()

    if tasks is None:
        from .tasks import load_tasks
        tasks = load_tasks()

    prov = None
    if provider_name or model:
        try:
            from .providers import provider_for
            prov = provider_for(model or C.ROLE_MODEL["worker"], provider_name,
                                base_url=base_url, api_key=api_key)
            if not prov.available():
                prov = None
        except Exception:
            prov = None

    if prov is None:
        log("chế độ OFFLINE: không gọi model, mọi phát hiện đều TÍNH TỪ DỮ LIỆU")
        findings = offline_findings(tasks)
        trace = [{"round": 1, "panelist": f.lens, "finding": f.id, "text": f.claim}
                 for f in findings]
        if rounds >= 2:
            for f in findings:
                new_status, why = COUNTER.get(f.id, (f.status, ""))
                if new_status != f.status or why:
                    f.status = new_status
                    f.note = why
                    log(f"vòng 2 · đối-kháng lên {f.id}: {new_status}")
                trace.append({"round": 2, "panelist": "đối-kháng", "finding": f.id,
                              "text": f"{new_status}: {why}"})
        findings.sort(key=lambda x: SEVERITY_ORDER.get(x.severity, 9))
        return {"mode": "offline", "question": question, "n_tasks": len(tasks),
                "sheet": sheet, "findings": [f.as_dict() for f in findings],
                "trace": trace, "seconds": round(time.time() - t0, 2),
                "rounds": rounds}

    # ---- chế độ có model thật: mỗi thấu kính viết phát hiện, rồi phản biện ----
    from .providers import ProviderError
    facts = _facts(tasks)
    findings_txt: dict[str, str] = {}
    for name, sys_prompt in LENSES:
        log(f"vòng 1 · {name}")
        try:
            text, _u = prov.call(sys_prompt, f"CÂU HỎI:\n{question}\n\nDỮ KIỆN:\n{facts}")
        except ProviderError as e:
            text = f"(lỗi: {e})"
        findings_txt[name] = text
    if rounds >= 2:
        merged = "\n\n".join(f"### {k}\n{v}" for k, v in findings_txt.items())
        for name, sys_prompt in LENSES:
            log(f"vòng 2 · {name} phản biện")
            try:
                text, _u = prov.call(sys_prompt + " Bây giờ PHẢN BIỆN các phát hiện dưới đây.",
                                     f"CÂU HỎI:\n{question}\n\nPHÁT HIỆN:\n{merged}")
            except ProviderError as e:
                text = f"(lỗi: {e})"
            findings_txt[name] = findings_txt[name] + "\n\n[PHẢN BIỆN] " + text
    return {"mode": f"model:{prov.name}", "question": question, "n_tasks": len(tasks),
            "sheet": sheet, "raw": findings_txt, "seconds": round(time.time() - t0, 2),
            "rounds": rounds}


def _facts(tasks: list[Any]) -> str:
    n = len(tasks)
    groups: dict[tuple, list] = collections.defaultdict(list)
    for t in tasks:
        groups[(t.observable["untrusted_content"], t.observable["tool_surface"])].append(
            bool(t.truth["injection_present"]))
    lines = [f"Tổng tác vụ: {n}",
             "Nhóm (untrusted_marker, tool_surface) -> n / số có injection:"]
    for k in sorted(groups, key=str):
        v = groups[k]
        lines.append(f"  marker={k[0]} surface={k[1]}: n={len(v)} inj={sum(v)}")
    lines.append("Cột HIỂN THỊ trên phiếu gán nhãn: task_id, request, tool_surface, "
                 "data_labels, untrusted_marker, output_type, records, dollars.")
    lines.append("Mục tiêu cần gán: injection_present (có payload injection thật hay không).")
    return "\n".join(lines)


def render_verdict(res: dict) -> str:
    """Dựng báo cáo markdown từ kết quả hội đồng."""
    L = ["# Hội đồng phản biện — kết luận", ""]
    L.append(f"**Câu hỏi:** {res['question']}")
    L.append(f"**Chế độ:** `{res['mode']}` · **số tác vụ soi:** {res['n_tasks']} · "
             f"**vòng:** {res['rounds']} · **giây:** {res['seconds']}")
    L.append("")
    if "findings" in res:
        surv = [f for f in res["findings"] if f["status"] != "refuted"]
        L.append(f"## Phát hiện còn đứng ({len(surv)}/{len(res['findings'])})")
        L.append("")
        L.append("| # | thấu kính | mức | phát hiện | trạng thái |")
        L.append("|---|---|---|---|---|")
        for f in res["findings"]:
            L.append(f"| {f['id']} | {f['lens']} | **{f['severity']}** | {f['claim']} | "
                     f"{f['status']} |")
        L.append("")
        L.append("## Bằng chứng")
        L.append("")
        for f in res["findings"]:
            L.append(f"**{f['id']} · {f['claim']}**")
            L.append("")
            L.append(f"- Bằng chứng: {f['evidence']}")
            if f["note"]:
                L.append(f"- Phản biện vòng 2: {f['note']}")
            L.append("")
    else:
        for k, v in res.get("raw", {}).items():
            L.append(f"## {k}")
            L.append("")
            L.append(v)
            L.append("")
    L.append("## Kết luận")
    L.append("")
    L.append("Hội đồng **không** sinh nhãn. Với phiếu CŨ (chỉ có metadata), mục tiêu "
             "cần gán không nằm trong cột hiển thị — nên dù người hay máy gán, kết quả "
             "cũng chỉ là phỏng đoán. Với phiếu MỚI (đã kèm nội dung thật), nhãn chuyển "
             "từ phỏng đoán thành **đọc được** — việc đúng là cho người gán thấy chính "
             "nội dung hệ thống đọc, không phải đoán theo nhãn nguồn.")
    return "\n".join(L)


def cmd_panel(args) -> int:
    from . import ui
    sheet = None
    if args.file:
        sheet = args.file
        ui.kv("Tệp soi", sheet)
    res = debate(args.question, sheet=sheet, rounds=args.rounds,
                 provider_name=(None if getattr(args, "offline", False) else args.provider),
                 model=(None if getattr(args, "offline", False) else args.model),
                 base_url=args.base_url,
                 on_step=lambda m: print(ui.c(f"  · {m}", "grey")))
    md = render_verdict(res)
    if args.out:
        p = Path(args.out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(md, encoding="utf-8")
        (p.with_suffix(".json")).write_text(json.dumps(res, ensure_ascii=False, indent=2),
                                            encoding="utf-8")
        ui.note(f"đã ghi: {p}", "ok")
    print()
    print(md)
    return 0
