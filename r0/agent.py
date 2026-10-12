"""Vòng lặp agent: model gọi công cụ, ta chạy công cụ, trả kết quả lại, lặp.

Có cả chế độ headless (`r0-shadow agent "..."`) trả về envelope JSON giống
`openclaw agent exec --json`: ok/status/final/usage/costUsd/toolSummary.

Bất biến: mọi thay đổi đĩa đi qua Session.write_file (I1); không qua cổng thì
không ghi (I2); quyền do code quyết, không do model tự khai (I5).
"""
from __future__ import annotations

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


def _price(model: str, u: dict) -> float:
    """Luôn có số. Model lạ dùng giá ước lượng để trần tiền vẫn khóa được."""
    p = C.PRICES.get(model) or C.UNKNOWN_PRICE
    return (u.get("in", 0) * p["in"] + u.get("out", 0) * p["out"]) / 1e6


def _consider_finish(session: Session, summary: str, task: str = "") -> tuple[bool, str]:
    """True khi làn chấp nhận kết thúc. Từ chối thì trả lý do cho model."""
    ok, why = session.accept_finish()
    if not ok:
        session.log_event("finish_refused", reason=why, layer="verification")
        return False, why
    if session.lane_seen == 2:
        from .skills import remember_fact, short_fact
        remember_fact(session.root, task, short_fact(task))
    return True, summary


def _note_budget(session: Session, max_budget_usd: float | None, spent: float) -> None:
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
             provider=None) -> dict:
    """Điểm vào duy nhất. `protocol` = auto | native | text.

    Hai van an toàn, đếm bằng CODE chứ không hỏi model (I8):
      `max_turns`       — trần số vòng gọi công cụ (mặc định 25)
      `max_budget_usd`  — dừng ngay khi chi phí lượt vượt mức này
    """
    if getattr(session, "spawn", None) is None:
        session.spawn = (lambda t, d, mt=12, mb=None: _spawn(
            session, t, d, mt, mb, model=model, provider_name=provider_name,
            base_url=base_url, api_key=api_key, max_tokens=max_tokens,
            no_stream=no_stream, protocol=protocol, note=on_note))
    use_native = protocol == "native" or (protocol == "auto" and provider_name in ("anthropic", "openai", "xai"))
    if protocol == "auto":
        # tự suy từ tên model khi không khai provider
        if provider_name is None:
            from .providers import provider_for as _pf
            try:
                use_native = _pf(model).name in ("anthropic", "openai", "xai")
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

    sys_prompt = AGENT_SYSTEM + "\n\nThư mục gốc: " + str(session.root)
    sys_prompt += _project_context(session, task)
    _mem = session.memory_for_prompt()
    if _mem:
        sys_prompt += "\n\nGHI NHỚ DỰ ÁN (MIRA.md):\n" + _mem
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

    for _ in range(rounds):
        try:
            blocks, u = native.converse(prov, sys_prompt, msgs, tools,
                                        on_text=emit, stream_it=not no_stream)
        except ProviderError as e:
            return {"status": "error", "error": str(e), "final": final_text,
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
        spent = _price(model, usage_total)
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
            results.append({"type": "tool_result", "tool_use_id": c["id"],
                            "content": clip_result(res), "is_error": not ev.ok})
        if stop:
            break
        msgs.append({"role": "user", "content": results})
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
            "costUsd": _price(model, usage_total),
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

    sys_prompt = AGENT_SYSTEM + "\n\nThư mục gốc: " + str(session.root)
    sys_prompt += _project_context(session, task)
    _mem = session.memory_for_prompt()
    if _mem:
        sys_prompt += "\n\nGHI NHỚ DỰ ÁN (MIRA.md):\n" + _mem
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

    for _ in range(rounds):
        prompt = _render(convo, sys_prompt)
        try:
            if no_stream:
                text, u = prov.call(sys_prompt, prompt)
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
        spent = _price(model, usage_total)
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
            convo.append({"role": "user", "content": f"<result>\n{why}\n</result>"})
            continue
        if name not in TOOL_NAMES:
            convo.append({"role": "user", "content":
                          f"<result>LỖI: không có công cụ {name}. Có: {tool_catalog()}</result>"})
            continue
        seen(name, args)
        res, _ev = session.call(name, args)
        tools_used.append(name)
        convo.append({"role": "user", "content": f"<result>\n{clip_result(res)}\n</result>"})
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
            "costUsd": _price(model, usage_total),
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


def cmd_agent(args) -> int:
    """Headless: một lượt, rồi thoát. Dùng cho script và CI."""
    from . import ui
    root = Path(args.cwd or ".").resolve()
    if not root.is_dir():
        ui.note(f"không có thư mục {root}", "bad")
        return 2
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
    res = run_turn(task=args.task, session=session, model=model,
                   provider_name=args.provider, base_url=args.base_url,
                   max_tokens=args.max_tokens, on_tool=show_tool,
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
            ui.note(f"trạng thái {env['status']}: {env.get('error')}", "bad")
    return {"ok": 0, "blocked": 1, "error": 1, "timeout": 2,
            "stopped_budget": 1, "stopped_turns": 1}.get(env["status"], 1)


def task_short(t: str, n: int = 90) -> str:
    t = " ".join((t or "").split())
    return t if len(t) <= n else t[: n - 1] + "…"
