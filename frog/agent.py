"""Vòng lặp agent: model gọi công cụ, ta chạy công cụ, trả kết quả lại, lặp.

Có cả chế độ headless (`r0-shadow agent "..."`) trả về envelope JSON giống
`openclaw agent exec --json`: ok/status/final/usage/costUsd/toolSummary.

Bất biến: mọi thay đổi đĩa đi qua Session.write_file (I1); không qua cổng thì
không ghi (I2); quyền do code quyết, không do model tự khai (I5).
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Callable

from . import config as C
from . import native
from .providers import ProviderError, provider_for
from .stream import stream
from .tools import AGENT_SYSTEM, Session, clip_result, parse_tool, tool_catalog, TOOL_SPECS

TOOL_NAMES = set(TOOL_SPECS)

MAX_TOOL_ROUNDS = 25


def _fmt_tokens(u: dict) -> str:
    return f"{u.get('in', 0)}+{u.get('out', 0)} tok"


def _price(model: str, u: dict, declared: tuple[float, float] | None = None) -> float:
    """Giá đã biết. Không có cli, file, hay env thì ra 0. Không dùng UNKNOWN_PRICE."""
    from .prices import resolve_price
    p, _source = resolve_price(model, declared)
    if not p:
        return 0.0
    return (u.get("in", 0) * p["in"] + u.get("out", 0) * p["out"]) / 1e6


def _named_command(task: str) -> str:
    found = re.search(r"\b((?:python|pytest)\b[^\n]*)", task or "")
    return found.group(1).strip().rstrip(".") if found else ""


def _shell_ok(session: Session, cmd: str) -> bool:
    return any(row.get("action") == "run_shell" and row.get("cmd") == cmd and row.get("exit") == 0
               for row in session.audit)


def _consider_finish(session: Session, summary: str, task: str = "") -> tuple[bool, str]:
    """True khi làn chấp nhận kết thúc. Từ chối thì trả lý do cho model."""
    if getattr(session, "shape", "") == "edit":
        cmd = _named_command(task or session.task_text)
        if cmd and not _shell_ok(session, cmd):
            out = session.run_shell(cmd)
            if "[mã thoát 0]" not in out:
                session.log_event("finish_refused", reason="lệnh chưa thoát 0", layer="verification")
                if getattr(session, "repair_used", False):
                    session.halt = True
                    session.stop_layer = "verification"
                else:
                    session.repair_used = True
                return False, "lệnh trong câu việc chưa thoát 0"
    ok, why = session.accept_finish()
    if not ok:
        session.log_event("finish_refused", reason=why, layer="verification")
        return False, why
    from .skills import fact_from_audit, mint_skill, remember_fact
    if session.lane_seen == 2:
        for row in session.audit:
            if row.get("action") not in ("write_file", "edit_file", "multi_edit"):
                continue
            rel = row.get("path")
            if not rel:
                continue
            line = fact_from_audit([row], root=session.root)
            if line:
                remember_fact(session.root, task, line, path=str(rel))
    mint_skill(session.root, task or session.task_text, session.audit)
    return True, summary


PROMPT_CAP = 24000


def _spent(model: str, usage_total: dict, session: Session) -> float:
    declared = getattr(session, "declared_price", None)
    return _price(model, usage_total, declared) + float(getattr(session, "child_spent", 0) or 0)


def _shrink(convo: list[dict], audit: list[dict]) -> list[dict]:
    """Khi prompt dài, gọi condense_trace: sổ sửa cộng sáu tin cuối."""
    rendered = "\n".join(m.get("content") or "" for m in convo)
    if len(rendered) <= PROMPT_CAP:
        return convo
    from .repl import condense_trace
    trace = [{"kind": "message", "role": m.get("role") or "user",
              "content": m.get("content") or ""} for m in convo]
    _note, event = condense_trace(trace, audit=audit)
    if not event:
        return convo
    kept = int(event.get("kept") or 6)
    return [{"role": "user", "content": event["summary"]}, *convo[-kept:]]


def _priced_call(session, prov, model: str, system: str, user: str):
    """Có sổ cái thì ghi dispatched trước khi gửi. Không có thì gọi thẳng."""
    ledger = getattr(session, "ledger", None)
    if ledger is None:
        return prov.call(system, user)
    from .prices import resolve_price
    rates, source = resolve_price(model, getattr(session, "declared_price", None))
    if rates is None:
        return prov.call(system, user)
    text, usage, _usd, _rid = ledger.tracked_call(
        "worker", model, prov, system, user, rates, source=source,
        max_out=int(getattr(prov, "max_tokens", None) or 4096),
        declared_by_user=source == "cli")
    return text, usage or {"in": 0, "out": 0}


def _recruit(session: Session, task: str, prov, model: str, provider_name, base_url, api_key,
             max_tokens, max_turns, max_budget_usd) -> tuple[dict | None, tuple | None]:
    """Chỉ dạng hỏi mới tuyển. Không có dòng VAI thì trả lời đó đi tiếp vòng tool."""
    from .skills import worker_skill_block
    from .team import DIRECTOR_SYSTEM, ROLE_PROMPT, vet_roster
    from .tools import Session as ToolSession
    if session.shape != "ask" or session.recruited:
        return None, None
    text, usage = _priced_call(session, prov, model, DIRECTOR_SYSTEM, task)
    if "VAI:" not in text:
        return None, (text, usage)
    ok, why, roles, steps = vet_roster(text, session.root, allow_write=False)
    if not ok:
        text, usage2 = _priced_call(session, prov, model, DIRECTOR_SYSTEM,
                                    task + "\nTỪ CHỐI đội: " + why)
        usage = {"in": usage.get("in", 0) + usage2.get("in", 0),
                 "out": usage.get("out", 0) + usage2.get("out", 0)}
        if "VAI:" not in text:
            return None, (text, usage)
        ok, why, roles, steps = vet_roster(text, session.root, allow_write=False)
        if not ok:
            session.stop_layer = "verification"
            return {"status": "stopped_verification", "error": None,
                    "final": "TỪ CHỐI đội: " + why, "usage": usage, "turns": 2,
                    "toolSummary": {"calls": 0, "tools": []}, "protocol": "text",
                    "stopReason": "TỪ CHỐI đội", "audit": session.audit,
                    "trace": list(session.trace),
                    "costUsd": _price(model, usage, getattr(session, "declared_price", None)),
                    "model": model, "provider": getattr(prov, "name", "")}, None
    session.recruited = True
    known = {role.name: role for role in roles}
    ordered = [known[name] for name in steps]
    session.log_event("roster", steps=",".join(steps))
    last = ""
    for role in ordered:
        child = ToolSession(root=session.root, mode=session.mode, approve=session.approve,
                            depth=session.depth + 1)
        child.gate_task = session.task_text
        child.recruited = True
        child.role_tools = set(role.tools)
        child.role_system = ROLE_PROMPT.format(name=role.name, job=role.job)
        job = role.job
        if role.skill:
            block = worker_skill_block(session.root, role.skill)
            if block:
                job += "\n" + block
        left = None if max_budget_usd is None else max(0.0, max_budget_usd - session.child_spent)
        res = run_turn(task=job, session=child, model=model, provider_name=provider_name,
                       base_url=base_url, api_key=api_key, max_tokens=max_tokens,
                       no_stream=True, protocol="text", max_turns=max_turns,
                       max_budget_usd=left, provider=prov,
                       price_in=getattr(session, "declared_price", None))
        session.child_spent += float(res.get("costUsd") or 0)
        last = str(res.get("final") or "")
    from .team import _worker_for_disk
    final = _worker_for_disk(session.task_text, last)
    return {"status": "ok", "error": None, "final": final, "usage": usage, "turns": len(ordered),
            "toolSummary": {"calls": 0, "tools": []}, "protocol": "text",
            "stopReason": None, "audit": session.audit, "trace": list(session.trace),
            "costUsd": _price(model, usage, getattr(session, "declared_price", None)) + session.child_spent,
            "model": model, "provider": getattr(prov, "name", "")}, None


def _note_budget(session: Session, max_budget_usd: float | None, spent: float) -> None:
    if max_budget_usd is not None:
        session.budget_left = max(0.0, max_budget_usd - spent)


def _system_prompt(session: Session, task: str) -> str:
    lead = session.role_system.strip()
    base = AGENT_SYSTEM if not lead else lead + "\n\n" + AGENT_SYSTEM
    text = base + "\n\nThư mục gốc: " + str(session.root)
    text += _project_context(session, task)
    memory = session.memory_for_prompt()
    if memory:
        text += "\n\nGHI NHỚ DỰ ÁN (MIRA.md):\n" + memory
    return text


def _stop_if_halt(session: Session, why: str) -> tuple[str, str] | None:
    if not session.halt:
        return None
    return "stopped_verification", why


def _over_budget(session: Session, model: str, usage_total: dict,
                 max_budget_usd: float | None) -> str | None:
    spent = _spent(model, usage_total, session)
    _note_budget(session, max_budget_usd, spent)
    if max_budget_usd is not None and spent >= max_budget_usd:
        return f"đã tiêu ${spent:.4f} ≥ trần ${max_budget_usd:.4f}"
    return None
    if max_budget_usd is not None:
        session.budget_left = max(0.0, max_budget_usd - spent)


def run_turn(*, task: str, session: Session, model: str,
             provider_name: str | None = None, base_url: str | None = None,
             api_key: str | None = None, max_tokens: int = 4096,
             history: list[dict] | None = None,
             on_text: Callable[[str], None] | None = None,
             on_tool: Callable[[str, dict], None] | None = None,
             on_note: Callable[[str], None] | None = None,
             no_stream: bool = False, protocol: str = "auto",
             max_turns: int | None = None,
             max_budget_usd: float | None = None,
             provider=None, price_in: tuple[float, float] | None = None) -> dict:
    """Điểm vào duy nhất. `protocol` = auto | native | text.

    Hai van an toàn, đếm bằng CODE chứ không hỏi model (I8):
      `max_turns`       — trần số vòng gọi công cụ (mặc định 25)
      `max_budget_usd`  — dừng ngay khi chi phí lượt vượt mức này
    """
    session.declared_price = price_in
    from .prices import resolve_price
    if resolve_price(model, price_in)[0] is None:
        return {"status": "blocked", "error": f"model {model} chưa có giá",
                "final": "", "usage": {"in": 0, "out": 0}, "turns": 0,
                "toolSummary": {"calls": 0, "tools": []}}
    inherited = getattr(session, "gate_task", "") or ""
    if inherited:
        session.task_text = inherited
        session.gate_task = ""
    else:
        session.task_text = task or ""
    from .tools import shape_of
    session.shape = shape_of(session.task_text)
    session.saw_untrusted = False
    from .skills import recall_facts
    if recall_facts(session.root, session.task_text).strip():
        session.saw_untrusted = True
    if getattr(session, "spawn", None) is None:
        session.spawn = (lambda t, d, mt=12, mb=None: _spawn(
            session, t, d, mt, mb, model=model, provider_name=provider_name,
            base_url=base_url, api_key=api_key, max_tokens=max_tokens,
            no_stream=no_stream, protocol=protocol, note=on_note))
    use_native = protocol == "native" or (protocol == "auto" and provider_name in ("anthropic", "openai", "xai", "openrouter"))
    if protocol == "auto":
        # tự suy từ tên model khi không khai provider
        if provider_name is None:
            from .providers import provider_for as _pf
            try:
                use_native = _pf(model).name in ("anthropic", "openai", "xai", "openrouter")
            except Exception:
                use_native = False
    if use_native:
        return _run_native_loop(task=task, session=session, model=model,
                                provider_name=provider_name, base_url=base_url,
                                api_key=api_key, max_tokens=max_tokens,
                                history=history, on_text=on_text, on_tool=on_tool,
                                on_note=on_note, no_stream=no_stream,
                                max_turns=max_turns, max_budget_usd=max_budget_usd)
    return _run_text_loop(task=task, session=session, model=model,
                          provider_name=provider_name, base_url=base_url,
                          api_key=api_key, max_tokens=max_tokens, history=history,
                          on_text=on_text, on_tool=on_tool, on_note=on_note,
                          no_stream=no_stream,
                          max_turns=max_turns, max_budget_usd=max_budget_usd,
                          provider=provider)


def _project_context(session: Session, task: str) -> str:
    """Catalog, bản đồ, fact. Ghi số skill, token và số skill còn giữ vào sổ."""
    from .skills import catalog_for_prompt, context_block, load_skills
    skills = load_skills(session.root)
    if skills:
        _text, stats = catalog_for_prompt(skills, task)
        session.log_event("skill_catalog", skills=stats["skills"], tokens=stats["tokens"],
                          kept=stats["kept"], layer="context")
    block = context_block(session.root, task)
    return ("\n\n" + block) if block else ""


def _spawn(parent: Session, task: str, depth: int, max_turns: int, max_budget,
           *, model: str, provider_name, base_url, api_key, max_tokens: int,
           no_stream: bool, protocol: str, note) -> dict:
    """Chạy một agent CON trong cùng thư mục gốc. Trần độ sâu do parent giữ."""
    left = getattr(parent, "budget_left", None)
    if left is not None:
        share = left * C.SUBAGENT["share"]
        max_budget = share if max_budget is None else min(max_budget, share)
    child = Session(root=parent.root, mode=parent.mode, approve=parent.approve,
                    depth=depth, max_depth=getattr(parent, "max_depth", 3),
                    allow_always=set(parent.allow_always),
                    budget_left=max_budget, checker=parent.checker)
    child.gate_task = parent.task_text or parent.gate_task
    child.spawn = (lambda t, d, mt=12, mb=None: _spawn(
        child, t, d, mt, mb, model=model, provider_name=provider_name,
        base_url=base_url, api_key=api_key, max_tokens=max_tokens,
        no_stream=no_stream, protocol=protocol, note=note))
    if note:
        note(f"↳ agent con (độ sâu {depth}): {str(task)[:60]}")
    return run_turn(task=task, session=child, model=model,
                    provider_name=provider_name, base_url=base_url, api_key=api_key,
                    max_tokens=max_tokens, no_stream=no_stream, protocol=protocol,
                    max_turns=max_turns or 12, max_budget_usd=max_budget)


def _run_native_loop(*, task: str, session: Session, model: str,
                     provider_name: str | None, base_url: str | None,
                     api_key: str | None, max_tokens: int,
                     history: list[dict] | None,
                     on_text, on_tool, on_note, no_stream: bool,
                     max_turns: int | None = None,
                     max_budget_usd: float | None = None) -> dict:
    """Vòng lặp dùng native tool-calling — không có giao thức văn bản."""
    emit = on_text or (lambda _s: None)
    seen = on_tool or (lambda _n, _a: None)
    note = on_note or (lambda _m: None)
    prov = provider_for(model, provider_name, base_url=base_url,
                        api_key=api_key, max_tokens=max_tokens)
    if not prov.available():
        return {"status": "blocked", "error": f"thiếu key cho {prov.name}",
                "final": "", "usage": {"in": 0, "out": 0}, "turns": 0,
                "toolSummary": {"calls": 0, "tools": []}, "protocol": "native"}

    sys_prompt = _system_prompt(session, task)
    tools = native.neutral_tools()
    msgs: list[dict] = list(history or []) + [
        {"role": "user", "content": [{"type": "text", "text": task}]}]
    usage_total = {"in": 0, "out": 0}
    tools_used: list[str] = []
    final_text = ""
    turns = 0
    status = "ok"
    stop_reason = None
    t0 = time.time()
    rounds = max_turns if (max_turns and max_turns > 0) else MAX_TOOL_ROUNDS
    recent: list[tuple] = []

    for _ in range(rounds):
        try:
            blocks, u = native.converse(prov, sys_prompt, msgs, tools,
                                        on_text=emit, stream_it=not no_stream)
        except ProviderError as e:
            return {"status": "error", "error": str(e), "final": final_text,
                    "usage": usage_total, "turns": turns,
                    "toolSummary": {"calls": len(tools_used), "tools": sorted(set(tools_used))},
                    "protocol": "native"}
        except Exception as e:                          # noqa: BLE001
            return {"status": "error", "error": f"{type(e).__name__}: {e}", "final": final_text,
                    "usage": usage_total, "turns": turns,
                    "toolSummary": {"calls": len(tools_used), "tools": sorted(set(tools_used))},
                    "protocol": "native"}
        turns += 1
        session.log_event("model_turn", turn=turns, protocol="native")
        usage_total["in"] += u.get("in", 0)
        usage_total["out"] += u.get("out", 0)
        if not blocks:
            blocks = [{"type": "text", "text": ""}]
        msgs.append({"role": "assistant", "content": blocks})

        # ---- van NGÂN SÁCH: đếm từ token đã tiêu, KHÔNG hỏi model (I8) ----
        spent = _spent(model, usage_total, session)
        _note_budget(session, max_budget_usd, spent)
        if max_budget_usd is not None and spent >= max_budget_usd:
            status = "stopped_budget"
            stop_reason = f"đã tiêu ${spent:.4f} ≥ trần ${max_budget_usd:.4f}"
            final_text = final_text or native.text_of(blocks)
            note(stop_reason)
            break

        calls = native.tool_calls(blocks)
        if not calls:
            summary = native.text_of(blocks)
            ok, why = _consider_finish(session, summary, task)
            if ok:
                final_text = summary
                break
            halted = _stop_if_halt(session, why)
            if halted:
                status, stop_reason = halted
                final_text = final_text or why
                note(why)
                break
            msgs.append({"role": "user", "content": [{"type": "text", "text": why}]})
            continue

        results: list[dict] = []
        stop = False
        for c in calls:
            name, args = c["name"], c.get("input") or {}
            if name == "finish":
                summary = str(args.get("summary") or native.text_of(blocks))
                ok, why = _consider_finish(session, summary, task)
                if ok:
                    final_text = summary
                    note("finish")
                    stop = True
                    break
                halted = _stop_if_halt(session, why)
                if halted:
                    status, stop_reason = halted
                    final_text = final_text or why
                    note(why)
                    stop = True
                    break
                results.append({"type": "tool_result", "tool_use_id": c["id"],
                                "content": why, "is_error": True})
                continue
            if name not in native.SCHEMAS:
                results.append({"type": "tool_result", "tool_use_id": c["id"],
                                "content": f"LỖI: không có công cụ {name}", "is_error": True})
                continue
            seen(name, args)
            res, ev = session.call(name, args)
            tools_used.append(name)
            mark = (name, json.dumps(args, sort_keys=True, ensure_ascii=False), res[:80])
            recent.append(mark)
            if len(recent) >= 3 and recent[-1] == recent[-2] == recent[-3]:
                status = "stopped_turns"
                session.stop_layer = "tool"
                stop_reason = "cùng tool cùng kết quả ba lần"
                final_text = final_text or stop_reason
                note(stop_reason)
                stop = True
                break
            results.append({"type": "tool_result", "tool_use_id": c["id"],
                            "content": clip_result(res), "is_error": not ev.ok})
        if stop:
            break
        msgs.append({"role": "user", "content": results})
        reason = _over_budget(session, model, usage_total, max_budget_usd)
        if reason:
            status = "stopped_budget"
            stop_reason = reason
            final_text = final_text or reason
            note(reason)
            break
    else:
        if session.stop_layer == "verification":
            status = "stopped_verification"
            stop_reason = "thiếu kiểm chứng"
        else:
            status = "stopped_turns"
            stop_reason = f"chạm trần {rounds} vòng gọi công cụ"
        final_text = final_text or "(dừng: quá nhiều vòng gọi công cụ)"
        note(stop_reason)

    session.log_event("stop", reason=stop_reason or "xong", layer=session.stop_layer)
    return {"status": status, "error": None, "final": final_text,
            "usage": usage_total, "turns": turns,
            "toolSummary": {"calls": len(tools_used), "tools": sorted(set(tools_used))},
            "seconds": round(time.time() - t0, 2),
            "model": model, "provider": prov.name, "protocol": "native",
            "costUsd": _spent(model, usage_total, session),
            "stopReason": stop_reason,
            "audit": session.audit, "trace": list(session.trace), "convo": msgs}


def _run_text_loop(*, task: str, session: Session, model: str,
             provider_name: str | None = None, base_url: str | None = None,
             api_key: str | None = None, max_tokens: int = 4096,
             history: list[dict] | None = None,
             on_text: Callable[[str], None] | None = None,
             on_tool: Callable[[str, dict], None] | None = None,
             on_note: Callable[[str], None] | None = None,
             no_stream: bool = False,
             max_turns: int | None = None,
             max_budget_usd: float | None = None,
             provider=None) -> dict:
    """Một lượt hỏi–đáp đầy đủ, có thể gọi nhiều công cụ."""
    emit = on_text or (lambda _s: None)
    seen = on_tool or (lambda _n, _a: None)
    note = on_note or (lambda _m: None)
    if provider is not None:
        prov = provider
    else:
        prov = provider_for(model, provider_name, base_url=base_url,
                            api_key=api_key, max_tokens=max_tokens)
    if not prov.available():
        return {"status": "blocked",
                "error": f"thiếu key cho {prov.name} — đặt biến môi trường",
                "final": "", "usage": {"in": 0, "out": 0}, "turns": 0,
                "toolSummary": {"calls": 0, "tools": []}}

    sys_prompt = _system_prompt(session, task)
    usage_total = {"in": 0, "out": 0}
    convo = list(history or [])
    convo.append({"role": "user", "content": task})
    tools_used: list[str] = []
    final_text = ""
    turns = 0
    status = "ok"
    stop_reason = None
    t0 = time.time()
    rounds = max_turns if (max_turns and max_turns > 0) else MAX_TOOL_ROUNDS
    recruited, primed = _recruit(session, task, prov, model, provider_name, base_url, api_key,
                                 max_tokens, max_turns, max_budget_usd)
    if recruited is not None:
        session.log_event("stop", reason=recruited.get("stopReason") or "xong", layer=session.stop_layer)
        recruited["seconds"] = round(time.time() - t0, 2)
        return recruited
    forced: list[tuple[str, dict]] = [primed] if primed else []
    recent: list[tuple] = []

    for _ in range(rounds):
        convo = _shrink(convo, session.audit)
        prompt = _render(convo, sys_prompt)
        try:
            if forced:
                text, u = forced.pop(0)
                emit(text)
            elif no_stream:
                text, u = _priced_call(session, prov, model, sys_prompt, prompt)
                emit(text)
            else:
                text, u = stream(prov, sys_prompt, prompt, on_text=emit)
        except ProviderError as e:
            return {"status": "error", "error": str(e), "final": final_text,
                    "usage": usage_total, "turns": turns,
                    "toolSummary": {"calls": len(tools_used), "tools": tools_used}}
        turns += 1
        session.log_event("model_turn", turn=turns, protocol="text")
        usage_total["in"] += u.get("in", 0)
        usage_total["out"] += u.get("out", 0)
        convo.append({"role": "assistant", "content": text})

        # ---- van NGÂN SÁCH: đếm từ token đã tiêu, KHÔNG hỏi model (I8) ----
        spent = _spent(model, usage_total, session)
        _note_budget(session, max_budget_usd, spent)
        if max_budget_usd is not None and spent >= max_budget_usd:
            status = "stopped_budget"
            stop_reason = f"đã tiêu ${spent:.4f} ≥ trần ${max_budget_usd:.4f}"
            final_text = final_text or _strip_tool(text)
            note(stop_reason)
            break

        call = parse_tool(text)
        if not call:
            summary = _strip_tool(text)
            ok, why = _consider_finish(session, summary, task)
            if ok:
                final_text = summary
                break
            halted = _stop_if_halt(session, why)
            if halted:
                status, stop_reason = halted
                final_text = final_text or why
                note(why)
                break
            convo.append({"role": "user", "content": f"<result>\n{why}\n</result>"})
            continue
        name, args = call
        if name == "finish":
            summary = str(args.get("summary") or _strip_tool(text))
            ok, why = _consider_finish(session, summary, task)
            if ok:
                final_text = summary
                note("finish")
                break
            halted = _stop_if_halt(session, why)
            if halted:
                status, stop_reason = halted
                final_text = final_text or why
                note(why)
                break
            convo.append({"role": "user", "content": f"<result>\n{why}\n</result>"})
            continue
        if name not in TOOL_NAMES:
            convo.append({"role": "user", "content":
                          f"<result>LỖI: không có công cụ {name}. Có: {tool_catalog()}</result>"})
            continue
        seen(name, args)
        res, _ev = session.call(name, args)
        tools_used.append(name)
        mark = (name, json.dumps(args, sort_keys=True, ensure_ascii=False), res[:80])
        recent.append(mark)
        if len(recent) >= 3 and recent[-1] == recent[-2] == recent[-3]:
            status = "stopped_turns"
            session.stop_layer = "tool"
            stop_reason = "cùng tool cùng kết quả ba lần"
            final_text = final_text or stop_reason
            note(stop_reason)
            break
        convo.append({"role": "user", "content": f"<result>\n{clip_result(res)}\n</result>"})
        reason = _over_budget(session, model, usage_total, max_budget_usd)
        if reason:
            status = "stopped_budget"
            stop_reason = reason
            final_text = final_text or reason
            note(reason)
            break
    else:
        if session.stop_layer == "verification":
            status = "stopped_verification"
            stop_reason = "thiếu kiểm chứng"
        else:
            status = "stopped_turns"
            stop_reason = f"chạm trần {rounds} vòng gọi công cụ"
        final_text = final_text or "(dừng: quá nhiều vòng gọi công cụ)"
        note(stop_reason)

    session.log_event("stop", reason=stop_reason or "xong", layer=session.stop_layer)
    return {"status": status, "error": None, "final": final_text,
            "usage": usage_total, "turns": turns,
            "toolSummary": {"calls": len(tools_used), "tools": sorted(set(tools_used))},
            "seconds": round(time.time() - t0, 2),
            "model": model, "provider": prov.name,
            "costUsd": _spent(model, usage_total, session),
            "stopReason": stop_reason,
            "audit": session.audit,
            "protocol": "text",
            "trace": list(session.trace),
            "convo": convo}


def _render(convo: list[dict], sys_prompt: str) -> str:
    """Gộp hội thoại thành một prompt phẳng — hợp với mọi nhà cung cấp."""
    out = []
    for m in convo:
        out.append(f"### {m['role']}\n{m['content']}")
    out.append("### LƯỢT CỦA BẠN\n(gọi công cụ hoặc finish)")
    return "\n\n".join(out)


def _strip_tool(text: str) -> str:
    import re
    return re.sub(r"<tool>.*?</tool>", "", text or "", flags=re.S).strip()


def envelope(task: str, res: dict, session: Session, session_id: str) -> dict:
    """Envelope JSON ổn định — mô phỏng dạng của `openclaw agent exec --json`."""
    return {"ok": res["status"] == "ok",
            "status": res["status"],
            "final": res.get("final", ""),
            "usage": {"input": res["usage"]["in"], "output": res["usage"]["out"],
                      "total": res["usage"]["in"] + res["usage"]["out"]},
            "costUsd": res.get("costUsd"),
            "assistantTurns": res.get("turns", 0),
            "toolSummary": res.get("toolSummary", {}),
            "model": res.get("model"), "provider": res.get("provider"),
            "protocol": res.get("protocol"),
            "sessionId": session_id,
            "mode": session.mode,
            "seconds": res.get("seconds"),
            "stopReason": res.get("stopReason"),
            "audit": res.get("audit", []),
            **({"error": {"message": res["error"], "kind": "provider"}} if res.get("error") else {})}


def auto_approve_allowed(surface: str, labels: list[str] | None = None) -> bool:
    """--yes và bypass chỉ sống trong vùng đọc hoặc sandbox, không nhãn hạn chế."""
    if surface not in ("read_only", "write_sandbox"):
        return False
    banned = {"confidential", "restricted"}
    return not any(part in banned for part in (labels or []))


def cmd_agent(args) -> int:
    """Headless: một lượt, rồi thoát. Dùng cho script và CI."""
    from . import ui
    root = Path(args.cwd or ".").resolve()
    if not root.is_dir():
        ui.note(f"không có thư mục {root}", "bad")
        return 2
    labels = [part.strip() for part in (getattr(args, "labels", None) or "internal").split(",") if part.strip()]
    surface = getattr(args, "surface", None) or "read_only"
    if (getattr(args, "yes", False) or args.mode == "bypass") and not auto_approve_allowed(surface, labels):
        print("Từ chối tự duyệt: bề mặt hoặc nhãn nằm ngoài vùng đọc và sandbox.", file=sys.stderr)
        return 7
    session = Session(root=root, mode=args.mode,
                      approve=(lambda t, a: True) if args.yes else (lambda t, a: False))
    if args.mode == "plan":
        ui.note("Chế độ chỉ bàn: không ghi tệp, không chạy lệnh.", "info")
    model = args.model or C.ROLE_MODEL["worker"]

    def show_tool(name, a):
        if not args.json:
            brief = a.get("cmd") or a.get("path") or a.get("pattern") or ""
            print("  " + ui.c(name, "accent") + ui.c(f"  {str(brief)[:80]}", "dim"))

    if not args.json:
        print(ui.c(task_short(args.task), "bright", "bold"))
    declared = None
    raw_price = getattr(args, "price_in", None)
    if raw_price:
        left, right = [float(part) for part in str(raw_price).split(",")]
        declared = (left, right)
    res = run_turn(task=args.task, session=session, model=model,
                   provider_name=args.provider, base_url=args.base_url,
                   max_tokens=args.max_tokens, on_tool=show_tool, price_in=declared,
                   protocol=getattr(args, "protocol", "auto"),
                   no_stream=getattr(args, "no_stream", False),
                   max_turns=getattr(args, "max_turns", 0) or None,
                   max_budget_usd=getattr(args, "max_budget_usd", None),
                   on_text=(None if args.json else (lambda s: print(s, end="", flush=True))),
                   on_note=(None if args.json else (lambda m: print(ui.c(f"  · {m}", "grey")))))

    sid = args.session_id or "headless"
    env = envelope(args.task, res, session, sid)
    if args.json:
        import json
        print(json.dumps(env, ensure_ascii=False, indent=2))
    else:
        print()
        cost = env["costUsd"]
        ui.note(f"{env['assistantTurns']} lượt · {_fmt_tokens(res['usage'])} · "
                + (f"${cost:.6f}" if cost is not None else "chưa có giá cho model này"),
                "info")
        if env["status"] != "ok":
            err = env.get("error") or {}
            msg = err.get("message") if isinstance(err, dict) else str(err)
            low = (msg or "").lower()
            if "reasoning_effort" in low or "function tools" in low:
                ui.note("Model này từ chối công cụ trên chat completions. "
                        "Thử --protocol text hoặc model khác (ví dụ gpt-5.6-luna).", "bad")
            ui.note(f"trạng thái {env['status']}: {msg}", "bad")
    return {"ok": 0, "blocked": 1, "error": 1, "timeout": 2,
            "stopped_budget": 1, "stopped_turns": 1}.get(env["status"], 1)


def task_short(t: str, n: int = 90) -> str:
    t = " ".join((t or "").split())
    return t if len(t) <= n else t[: n - 1] + "…"
