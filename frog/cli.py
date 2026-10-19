"""Giao diện dòng lệnh của harness R0 shadow.

    frog                           # vào phiên (giống gõ claude)
    frog install                   # đặt lệnh frog vào PATH
    r0-shadow run                  # chạy shadow
    r0-shadow report               # xem kết quả dạng bảng
    r0-shadow labels export        # sinh phiếu gán nhãn
    r0-shadow labels status        # xem đã điền được bao nhiêu
    r0-shadow compare --a A --b B  # so hai lần chạy
    r0-shadow task T0007           # xem một tác vụ
    r0-shadow doctor               # kiểm tra môi trường
    r0-shadow selftest             # kiểm tra bất biến
"""
from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
from pathlib import Path

from . import config as C
from . import ui
from .labels import apply_labels, export_labels, label_stats, load_labels
from .stats import cmd_stats
from .tui import cmd_tui
from .detect import cmd_detect_compare
from .classifiers import KeywordClassifier, build_classifier
from .metrics import compute, ledger_summary, save
from .pipeline import ShadowRun
from .tasks import load_tasks
from .team import cmd_team
from .agent import cmd_agent

from . import __version__ as VERSION
DEFAULT_RUN = "out"


# ------------------------------------------------------------------ tiện ích
def _read_metrics(run_dir: str) -> dict:
    p = Path(run_dir) / "metrics.json"
    if not p.exists():
        ui.note(f"không thấy {p} — chạy `r0-shadow run --out {run_dir}` trước", "bad")
        raise SystemExit(2)
    return json.loads(p.read_text(encoding="utf-8"))


def _read_trace(run_dir: str) -> list[dict]:
    p = Path(run_dir) / "trace.jsonl"
    if not p.exists():
        ui.note(f"không thấy {p}", "bad")
        raise SystemExit(2)
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


# --------------------------------------------------------------------- run
def cmd_run(args) -> int:
    C.CACHE_HIT = args.cache_hit
    tasks = load_tasks()
    if args.n:
        tasks = tasks[: args.n]
    cache_dir = None if getattr(args, "no_cache", False) else f"{args.out}/classifier-cache"
    clf, err = build_classifier(getattr(args, "classifier", "keyword"),
                                provider_name=getattr(args, "provider", None),
                                model=getattr(args, "model", None),
                                base_url=getattr(args, "base_url", None),
                                api_key=getattr(args, "api_key", None),
                                cache_dir=cache_dir)
    if err:
        ui.note(err, "bad")
        return 2
    if not args.quiet:
        print(ui.c(f"Chạy shadow · {len(tasks)} tác vụ · cache hit {args.cache_hit:.0%} · seed {args.seed}", "bold"))
        who = clf.name + (f" ({clf.model})" if getattr(clf, "model", None) else "")
        print(ui.c(f"  classifier: {who}", "grey"))
        print(ui.c("  (chế độ shadow: ghi log, KHÔNG hành động)", "grey"))
    run = ShadowRun(tasks=tasks, rng=random.Random(args.seed), seed=args.seed, classifier=clf)
    trace = run.run()

    m = compute(trace)
    if args.labels:
        labels = load_labels(args.labels)
        m["label_mode"] = {**label_stats(tasks, labels), "applied_to_trace": apply_labels(trace, labels)}
    m["ledger"] = ledger_summary(run.ledger.rows)
    m["run_config"] = {"cache_hit": args.cache_hit, "seed": args.seed, "n": len(trace),
                       "mode": "shadow · không hành động",
                       "labels": args.labels or "nhãn tổng hợp",
                       "classifier": clf.name,
                       "classifier_model": getattr(clf, "model", None)}
    if hasattr(clf, "summary"):
        m["classifier_mode"] = clf.summary()
    m["ledger_detail"] = {"session_total": round(run.ledger.session_total, 4),
                          "day_total": round(run.ledger.day_total, 4),
                          "over_cap_events": run.ledger.over_cap,
                          "session_cap": C.SESSION_CAP, "day_cap": C.DAY_CAP}
    save(trace, m, Path(args.out))

    if args.json:
        print(json.dumps(m, ensure_ascii=False, indent=2))
    elif not args.quiet:
        _print_report(m, args.out)
    return 0


def _print_report(m: dict, run_dir: str, top: int = 0) -> None:
    rc = m.get("run_config", {})
    print()
    ui.hr("═")
    print(ui.c("  KẾT QUẢ R0 SHADOW", "bold"))
    ui.hr("═")
    ui.kv("Tác vụ", m["n"])
    ui.kv("Chế độ", rc.get("mode", "shadow"))
    ui.kv("Cache hit", f"{rc.get('cache_hit', 0):.0%}")
    ui.kv("Seed", rc.get("seed"))
    ui.kv("Nguồn nhãn", rc.get("labels", "nhãn tổng hợp"))
    sh = m.get("shadow", {})
    ui.kv("Hành động đã thực hiện", ui.c(str(sh.get("action_taken", 0)), "green", "bold")
          + ui.c("  (bất biến I2: phải = 0)", "grey"))

    ui.title("Phân bố làn")
    rows = []
    for lane in ("0", "1", "2"):
        n = m["lane_distribution"].get(lane, 0)
        cb = m["cost_by_lane"].get(lane, {})
        rows.append([f"làn {lane}", n, ui.pct(m["lane_distribution_pct"].get(lane, 0)),
                     f"${cb.get('p50', 0):.4f}", f"${cb.get('p95', 0):.4f}",
                     f"${cb.get('cap', 0):.2f}" if cb.get("cap") else "—"])
    ui.table(["", "n", "%", "chi phí p50", "p95", "trần"], rows, ["l", "r", "r", "r", "r", "r"])

    ui.title("Chi phí mỗi mốc D4")
    rows = [[f"làn {l}", v["milestones_total"], f"${v['p50']:.4f}", f"${v['p95']:.4f}"]
            for l, v in sorted(m.get("cost_per_milestone", {}).items())]
    if rows:
        ui.table(["", "tổng mốc", "p50/mốc", "p95/mốc"], rows, ["l", "r", "r", "r"])
    mo = m.get("milestones_overall", {})
    ui.note(f"{mo.get('mean_per_task', 0):.2f} mốc/tác vụ · {ui.pct(mo.get('zero_milestone_rate', 0))} tác vụ không ra mốc nào")

    ui.title("Cổng người")
    rows = [[f"tầng {t}", m["gate_tier_distribution"].get(t, 0),
             ui.pct(m["gate_tier_distribution_pct"].get(t, 0))] for t in ("1", "2", "3")]
    ui.table(["", "n", "%"], rows, ["l", "r", "r"])
    ui.kv("Giờ audit mỗi tuần", ui.c(f"{m['audit_hours_per_week']:.2f} h", "yellow", "bold")
          + ui.c("  ← nút thắt lớn nhất", "grey"))
    ui.kv("Bắt buộc 2 người duyệt", ui.pct(m.get("dual_approval_rate", 0)))

    ui.title("T1b — classifier")
    ui.kv("Nhãn nguồn bỏ sót injection", f"{m['label_missed_injection_n']} ({ui.pct(m['label_missed_injection_rate'])})")
    ui.kv("T1b bắt được", f"{m['t1b_caught_when_label_missed']}/{m['label_missed_injection_n']}"
          f"  recall {m['t1b_recall_on_missed']:.4f}  precision {m['t1b_precision']:.4f}")
    ui.kv("Giá phải trả", f"nâng {ui.pct(m['t1b_raise_rate'])} · nâng vô ích {ui.pct(m['over_escalation_rate'])}")

    ui.title("Oracle ↔ Verifier")
    ov = m.get("oracle_verifier")
    if ov:
        ui.kv("Tương quan", f"r = {ov['pearson_r']:.4f} · κ = {ov['cohen_kappa']:.4f}")
        ui.kv("Cử tri độc lập thật", ui.c(f"≈ {ov['effective_independent_voters']}", "yellow", "bold")
              + ui.c("  (2 bên, không phải 2 cử tri)", "grey"))

    ui.title("Sàn rủi ro")
    fl = m.get("floor_lowering", {})
    ui.kv("Thử hạ / hạ được", f"{fl.get('attempted', 0)} / {fl.get('succeeded', 0)}")
    ui.kv("Sàn dưới mức sự thật", f"{m.get('floor_below_truth_rate', 0):.4f}")

    ui.title("Sổ cái theo vai")
    led = m.get("ledger", {})
    rows = [[k, f"${v:.4f}"] for k, v in led.get("by_role", {}).items()]
    ui.table(["vai", "USD"], rows, ["l", "r"])
    ui.kv("Tổng", ui.c(f"${led.get('total_usd', 0):.4f}", "bold"))

    ui.title("Ngưỡng D (p95 đo được)")
    ui.kv("D1 khối lượng prompt", f"{m['D1_fill_p95']:.4f} cửa sổ")
    ui.kv("D2 Δ mỗi lượt", f"{m['D2_per_turn_p95']:.0f} token")
    ui.kv("D3 tool call", f"{m['D3_calls_p95']} lượt")

    if top:
        ui.title(f"{top} tác vụ tốn kém nhất")
        tr = sorted(_read_trace(run_dir), key=lambda r: -r["cost_usd"])[:top]
        ui.table(["id", "làn", "USD", "yêu cầu"],
                 [[r["id"], r["lane_final"], f"${r['cost_usd']:.4f}", r["request"][:46]] for r in tr],
                 ["l", "r", "r", "l"])

    ui.hr("═")
    ui.note(f"trace: {run_dir}/trace.jsonl · số liệu: {run_dir}/metrics.json", "info")


# ---------------------------------------------------------------- report
def cmd_report(args) -> int:
    m = _read_metrics(args.run)
    if args.json:
        print(json.dumps(m, ensure_ascii=False, indent=2))
    else:
        _print_report(m, args.run, top=args.top)
    return 0


# ---------------------------------------------------------------- labels
def cmd_labels_export(args) -> int:
    tasks = load_tasks()
    if args.n:
        tasks = tasks[: args.n]
    p = export_labels(tasks, args.out)
    ui.note(f"đã ghi phiếu: {p} ({len(tasks)} dòng)", "ok")
    ui.note("phiếu KHÔNG chứa đáp án; xếp theo task_id để thứ tự dòng không lộ tầng")
    ui.note("điền cột human_injection = yes / no cho dòng bạn chắc; để trống nếu không chắc")
    return 0


def cmd_labels_status(args) -> int:
    import csv
    p = Path(args.file)
    if not p.exists():
        ui.note(f"không thấy {p} — chạy `r0-shadow labels export` trước", "bad")
        return 2
    rows = list(csv.DictReader(p.open(encoding="utf-8")))
    done = [r for r in rows if (r.get("human_injection") or "").strip()]
    yes = sum(1 for r in done if r["human_injection"].strip().lower() in ("yes", "y", "1", "true", "có", "co", "x"))
    ui.kv("Phiếu", str(p))
    ui.kv("Tổng dòng", len(rows))
    ui.kv("Đã điền", f"{len(done)} ({ui.pct(len(done)/len(rows)) if rows else '—'})")
    ui.kv("Trong đó = có injection", yes)
    if done:
        total = len(rows)
        print()
        print(f"  {ui.bar(len(done), total)} {len(done)}/{total}")
    if len(done) < len(rows):
        ui.note(f"còn {len(rows)-len(done)} dòng trống — để trống cũng hợp lệ, sẽ bị bỏ qua", "warn")
    ui.note("chạy: r0-shadow run --out out-lab --labels " + str(p), "info")
    return 0


def cmd_labels_triage(args) -> int:
    """Danh sách ngắn: nên gán nhãn dòng nào TRƯỚC, và vì sao."""
    from .labels import triage, write_triage
    from .tasks import load_tasks
    tasks = load_tasks()
    rows = triage(tasks)
    p = write_triage(rows, args.out)
    r1 = [r for r in rows if r["rank"] == 1]
    r2 = [r for r in rows if r["rank"] == 2]
    r3 = [r for r in rows if r["rank"] == 3]
    ui.kv("Tổng", f"{len(rows)} tác vụ")
    ui.kv("Hạng 1 — recall", f"{len(r1)} dòng (marker=no & bề mặt rủi ro cao)")
    ui.kv("Hạng 2 — precision", f"{len(r2)} dòng (marker=yes)")
    ui.kv("Hạng 3 — phụ", f"{len(r3)} dòng")
    ui.note(f"tối thiểu nên gán: {len(r1) + min(len(r2), 30)} dòng "
            f"(hạng 1 + 30 mẫu hạng 2) thay vì {len(rows)}", "info")
    ui.note(f"đã ghi: {p}", "ok")
    return 0


def cmd_labels_check(args) -> int:
    import csv
    p = Path(args.file)
    if not p.exists():
        ui.note(f"không thấy {p}", "bad")
        return 2
    rows = list(csv.DictReader(p.open(encoding="utf-8")))
    cols = set(rows[0].keys()) if rows else set()
    bad = 0
    for r in rows:
        v = (r.get("human_injection") or "").strip().lower()
        if v and v not in ("yes", "no", "y", "n", "1", "0", "true", "false", "có", "co", "không", "khong", "x"):
            ui.note(f"{r.get('task_id')}: giá trị lạ {v!r}", "bad")
            bad += 1
    for forbidden in ("truth", "injection_present", "truth_floor"):
        if forbidden in cols:
            ui.note(f"phiếu chứa cột đáp án {forbidden!r} — nhãn người sẽ bị nhiễm", "bad")
            bad += 1
    if bad == 0:
        ui.note(f"phiếu hợp lệ: {len(rows)} dòng, không có cột đáp án, không có giá trị lạ", "ok")
        return 0
    return 1


# --------------------------------------------------------------- compare
def cmd_compare(args) -> int:
    a, b = _read_metrics(args.a), _read_metrics(args.b)
    ui.title(f"So sánh: {args.a}  →  {args.b}")
    rows = []

    def add(name, va, vb, fmt=str, lower_better=False):
        try:
            d = vb - va
        except TypeError:
            rows.append([name, str(va), str(vb), "—"])
            return
        arrow = "=" if abs(d) < 1e-12 else ("-" if d < 0 else "+")
        good = (d < 0) if lower_better else (d > 0)
        mark = ui.c(arrow, "green" if good and abs(d) > 1e-12 else ("red" if abs(d) > 1e-12 else "grey"))
        rows.append([name, fmt(va), fmt(vb), f"{mark} {d:+.4f}".rstrip("0").rstrip(".")])

    add("tổng chi phí USD", a["ledger"]["total_usd"], b["ledger"]["total_usd"],
        lambda x: f"${x:.4f}", lower_better=True)
    for lane in ("0", "1", "2"):
        if lane in a["cost_by_lane"] and lane in b["cost_by_lane"]:
            add(f"làn {lane} p50", a["cost_by_lane"][lane]["p50"], b["cost_by_lane"][lane]["p50"],
                lambda x: f"${x:.4f}", lower_better=True)
    add("escalate V-C", a["VC_escalate_rate"], b["VC_escalate_rate"], lambda x: f"{x:.4f}")
    add("giờ audit/tuần", a["audit_hours_per_week"], b["audit_hours_per_week"],
        lambda x: f"{x:.2f} h", lower_better=True)
    add("T1b recall", a["t1b_recall_on_missed"] or 0, b["t1b_recall_on_missed"] or 0, lambda x: f"{x:.4f}")
    add("T1b precision", a["t1b_precision"], b["t1b_precision"], lambda x: f"{x:.4f}")
    add("nâng làn vô ích", a["over_escalation_rate"], b["over_escalation_rate"],
        lambda x: f"{x:.4f}", lower_better=True)
    add("oracle r", a["oracle_verifier"]["pearson_r"], b["oracle_verifier"]["pearson_r"], lambda x: f"{x:.4f}")
    add("cử tri độc lập", a["oracle_verifier"]["effective_independent_voters"],
        b["oracle_verifier"]["effective_independent_voters"], lambda x: f"{x:.2f}")
    add("D1 p95", a["D1_fill_p95"], b["D1_fill_p95"], lambda x: f"{x:.4f}", lower_better=True)
    add("D2 p95", a["D2_per_turn_p95"], b["D2_per_turn_p95"], lambda x: f"{x:.0f}", lower_better=True)
    add("D3 p95", a["D3_calls_p95"], b["D3_calls_p95"], lambda x: f"{x:.0f}", lower_better=True)

    ui.table(["chỉ số", args.a, args.b, "lệch"], rows, ["l", "r", "r", "r"])
    for k in ("lane_distribution", "gate_tier_distribution"):
        if a.get(k) != b.get(k):
            ui.note(f"{k} khác nhau: {a.get(k)} → {b.get(k)}", "warn")
    return 0


# ------------------------------------------------------------------ task
def cmd_task(args) -> int:
    trace = _read_trace(args.run)
    hit = [r for r in trace if r["id"].lower() == args.id.lower()]
    if not hit:
        ui.note(f"không thấy tác vụ {args.id} trong {args.run}", "bad")
        return 2
    r = hit[0]
    ui.title(f"Tác vụ {r['id']} · tầng {r['stratum']}")
    ui.kv("Yêu cầu", r["request"])
    ui.kv("Bề mặt tool", r["tool_surface"])
    ui.kv("Nhãn dữ liệu", ", ".join(r["data_labels"]))
    ui.kv("Kiểu đầu ra", r["output_type"])
    ui.kv("Quy mô", f"{r['records']} bản ghi · ${r['dollars']:.0f}")
    ui.kv("Bồi hoàn", r["reversibility"])
    ui.title("Quyết định")
    ui.kv("Làn cơ sở (T1a)", r["lane_base"])
    ui.kv("Capability", r["capability"])
    ui.kv("Sàn rủi ro", f"{r['floor']}" + (ui.c(f"  ({r['floor_reason']})", "grey")))
    ui.kv("Classifier", f"{r['classifier']['choice']} · conf {r['classifier']['confidence']:.2f}")
    ui.kv("LÀN CUỐI", ui.c(str(r["lane_final"]), "bold", "cyan"))
    ui.kv("Cổng người", f"tầng {r['gate_tier']} · {r['gate_minutes']:.0f} phút"
          + ("  (2 người duyệt)" if r.get("dual_approval") else ""))
    ui.title("Chi phí & thời gian")
    ui.kv("Tổng", f"${r['cost_usd']:.6f}")
    for k, v in r["cost_by_role"].items():
        ui.kv("  " + k, f"${v:.6f}")
    ui.kv("Mốc D4", f"{r['milestones']['milestones']}/{r['milestones']['criteria_total']}"
          f" · ${r['cost_per_milestone']:.6f}/mốc")
    ui.kv("Độ trễ", f"{r['latency_s']:.1f} s")
    ui.title("Chấm điểm")
    ov = r["oracle_verifier"]
    if ov.get("oracle") is not None:
        ui.kv("Verifier", f"{ov['verifier']:.4f} ({ov['verifier_model']})")
        ui.kv("Oracle", f"{ov['oracle']:.4f} ({ov['oracle_model']})")
        ui.kv("Đồng thuận", "có" if ov.get("agree") else "không")
    else:
        ui.kv("Verifier", f"{ov.get('verifier')}" if ov.get("verifier") is not None else "—")
    g = r["guards"]
    flags = [k for k in ("D1", "D2", "D3", "D4") if g[k]]
    ui.kv("Cờ D", ", ".join(flags) if flags else "không")
    ui.kv("Hành động", ui.c(str(r["action_taken"]), "green"))
    return 0


# ---------------------------------------------------------------- doctor
def cmd_doctor(args) -> int:
    ok = True
    ui.title("Kiểm tra môi trường")
    v = sys.version_info
    good = v >= (3, 9)
    ok &= good
    ui.note(f"Python {v.major}.{v.minor}.{v.micro}" + ("" if good else " — cần 3.9+"), "ok" if good else "bad")
    try:
        import frog  # noqa
        ui.note(f"gói frog import được từ {Path(frog.__file__).parent}", "ok")
        from .keys import KEYS_PATH
        ui.note(f"khóa và phiên nằm ở {KEYS_PATH.parent}", "ok")
    except Exception as e:
        ok = False
        ui.note(f"không import được gói frog: {e}", "bad")
    d = Path(args.out)
    try:
        d.mkdir(parents=True, exist_ok=True)
        t = d / ".write-test"
        t.write_text("x", encoding="utf-8")
        t.unlink()
        ui.note(f"ghi được vào {d.resolve()}", "ok")
    except Exception as e:
        ok = False
        ui.note(f"không ghi được vào {d}: {e}", "bad")
    ui.note(f"terminal {'có' if sys.stdout.isatty() else 'không'} tương tác"
            + ("" if sys.stdout.isatty() else " (gõ frog trần sẽ in trợ giúp, không vào phiên)"), "info")
    ui.note(f"màu {'bật' if ui._COLOR else 'tắt'}"
            + ("" if ui._COLOR else " — đặt FORCE_COLOR=1 để bật"), "info")
    try:
        tasks = load_tasks()
        ui.note(f"nạp được {len(tasks)} tác vụ · {len({t.stratum for t in tasks})} tầng", "ok")
    except Exception as e:
        ok = False
        ui.note(f"không nạp được bộ tác vụ: {e}", "bad")
    try:
        subprocess.run([sys.executable, "-c", "import unittest"], check=True, capture_output=True)
        ui.note("unittest sẵn sàng (dùng cho `selftest`)", "ok")
    except Exception:
        ui.note("không chạy được unittest — `selftest` sẽ không hoạt động", "warn")
    print()
    ui.note("môi trường OK" if ok else "có vấn đề ở trên", "ok" if ok else "bad")
    return 0 if ok else 1


def cmd_verify(args) -> int:
    from .pipeline import verify_trace
    code, reason = verify_trace(Path(args.dir))
    if code != 0 and reason:
        print(reason, file=sys.stderr)
    return code


def cmd_selftest(args) -> int:
    root = Path(__file__).resolve().parents[1]
    tests = root / "tests"
    if not tests.exists():
        ui.note(f"không thấy thư mục tests ở {tests}", "bad")
        return 2
    return subprocess.call([sys.executable, "-m", "unittest", "discover", "-s", str(tests), "-v"])


# ------------------------------------------------------------ menu tương tác
def _menu_cache() -> int:
    for hit in (0.0, 0.5, 0.7):
        cmd_run(_ns(out=f"out-cache{int(hit*100)}", cache_hit=hit, quiet=True))
    cmd_compare(_ns(a="out-cache0", b=f"out-cache{int(C.CACHE_HIT*100)}"))
    return 0


def _menu_team() -> int:
    from . import ui as _ui
    try:
        t = input(_ui.c("  Nhập yêu cầu: ", "bold")).strip()
    except (EOFError, KeyboardInterrupt):
        return 0
    if not t:
        _ui.note("Bỏ qua.", "warn")
        return 0
    print()
    _ui.note("Chạy thử trước: không gọi model, không tốn tiền.", "info")
    return cmd_team(_ns(task=t, dry_run=True))


def _menu_run(argv: list[str]):
    def go() -> int:
        args = build_parser().parse_args(argv)
        return args.func(args)
    return go


def _menu_task(name: str):
    def go() -> int:
        try:
            task = input(ui.c("  câu việc  ", "bold")).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not task:
            return 0
        args = build_parser().parse_args([name, task])
        return args.func(args)
    return go


MENU_PRIMARY = [
    ("1", "frog giao", _menu_task("giao")),
    ("2", "frog team", _menu_task("team")),
    ("3", "frog agent", _menu_task("agent")),
    ("4", "frog keys", _menu_run(["keys"])),
    ("5", "frog doctor", _menu_run(["doctor"])),
]

MENU = MENU_PRIMARY


def _ns(**kw):
    class N:
        pass
    n = N()
    n.out = kw.get("out", DEFAULT_RUN)
    n.run = kw.get("run", DEFAULT_RUN)
    n.cache_hit = kw.get("cache_hit", C.CACHE_HIT)
    n.seed = kw.get("seed", C.SEED)
    n.n = kw.get("n", 0)
    n.labels = kw.get("labels")
    n.quiet = kw.get("quiet", False)
    n.json = kw.get("json", False)
    n.top = kw.get("top", 0)
    n.file = kw.get("file")
    n.session = kw.get("session")
    n.limit = kw.get("limit", 0)
    n.action = kw.get("action")
    n.a = kw.get("a")
    n.b = kw.get("b")
    n.id = kw.get("id")
    # đội agent
    n.task = kw.get("task")
    n.surface = kw.get("surface", "read_only")
    n.labels = kw.get("labels", "internal")
    n.records = kw.get("records", 50)
    n.dollars = kw.get("dollars", 0.0)
    n.reversibility = kw.get("reversibility", "C1")
    n.output_type = kw.get("output_type", "free_string")
    n.provider = kw.get("provider")
    n.model = kw.get("model")
    n.base_url = kw.get("base_url")
    n.max_tokens = kw.get("max_tokens", 4096)
    n.dry_run = kw.get("dry_run", False)
    n.approve = kw.get("approve", False)
    # agent / chat
    n.cwd = kw.get("cwd", ".")
    n.mode = kw.get("mode", "default")
    n.no_stream = kw.get("no_stream", False)
    n.protocol = kw.get("protocol", "auto")
    n.max_turns = kw.get("max_turns", 0)
    n.max_budget_usd = kw.get("max_budget_usd")
    n.workers = kw.get("workers", 1)
    n.sub_depth = kw.get("sub_depth", 0)
    n.yes = kw.get("yes", False)
    n.session_id = kw.get("session_id")
    n.resume = kw.get("resume")
    n.team = kw.get("team", False)
    # thống kê
    n.run = kw.get("run", DEFAULT_RUN)
    n.metric = kw.get("metric", "cost")
    n.dump = kw.get("dump")
    n.classifier = kw.get("classifier", "keyword")
    n.api_key = kw.get("api_key")
    n.no_cache = kw.get("no_cache", False)
    return n


def _stats_pick() -> int:
    """Menu nhỏ để chọn chỉ số lớn cho màn thống kê."""
    opts = ["cost", "tasks", "audit", "vc", "latency"]
    print()
    for i, o in enumerate(opts, 1):
        print(f"  {ui.c(str(i), 'accent', 'bold')}. {o}")
    try:
        k = input(ui.c("  chọn  ", "bold")).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return 0
    if k.isdigit() and 1 <= int(k) <= len(opts):
        return cmd_stats(_ns(run=DEFAULT_RUN, metric=opts[int(k) - 1]))
    ui.note("Không có mục đó.", "warn")
    return 0


def _print_menu(entries, indent="  ") -> None:
    for k, label, _ in entries:
        print(f"{indent}{ui.c(k, 'accent', 'bold')}  {label}")


def _menu_header() -> None:
    print()
    ui.masthead([
        ui.c("frog", "bright", "bold"),
        ui.c("Chọn một việc, gõ số rồi Enter.", "dim"),
        ui.c("q để thoát", "faint"),
    ])
    print()


def interactive() -> int:
    """Menu mặc định: giao, team, agent, keys, doctor."""
    while True:
        _menu_header()
        _print_menu(MENU_PRIMARY)
        print(f"  {ui.c('q', 'accent', 'bold')}  thoát")
        try:
            ch = input(ui.c("\n  chọn  ", "bold")).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if ch in ("q", "quit", "exit", ""):
            return 0
        hit = next((f for k, _, f in MENU_PRIMARY if k == ch), None)
        if not hit:
            ui.note("Không có mục đó.", "warn")
            continue
        _safe_run(hit)


def _safe_run(fn) -> None:
    try:
        fn()
    except SystemExit as e:
        if e.code:
            ui.note(f"lệnh thoát với mã {e.code}", "warn")
    except Exception as e:                          # noqa: BLE001
        ui.note(f"lỗi: {type(e).__name__}: {e}", "bad")


def _pick_model() -> str:
    """Chọn model mặc định theo khoá đang có — để gõ `frog` là chạy được ngay."""
    from .keys import resolve
    if resolve("openrouter")[0]:
        return C.OPENROUTER_MODEL
    if resolve("anthropic")[0]:
        return C.ROLE_MODEL["worker"]          # sonnet-5.5
    if resolve("openai")[0]:
        return "gpt-5.6-sol"
    if resolve("xai")[0]:
        return "grok-4.7"
    return C.ROLE_MODEL["worker"]


def _open() -> int:
    """Gõ `frog` trần -> mở thẳng phiên làm việc (kiểu `claude` / `openclaw`).

    Lần đầu chưa có khoá API: chạy cài đặt ngắn rồi vào phiên luôn.
    """
    from .keys import prompt_setup, resolve
    have = any(resolve(p)[0] for p in ("openrouter", "anthropic", "openai", "xai"))
    if not have:
        print()
        ui.masthead([
            ui.c("frog", "bright", "bold"),
            ui.c("Cần một khoá API để bắt đầu.", "dim"),
            ui.c("Enter để bỏ qua nhà cung cấp nào không dùng.", "faint"),
        ])
        print()
        prompt_setup()
        have = any(resolve(p)[0] for p in ("openrouter", "anthropic", "openai", "xai"))
        if not have:
            ui.note("Chưa có khoá. Mở menu để chọn việc khác.", "warn")
            return interactive()
    from .repl import repl
    return repl(_ns(model=_pick_model()))


def _cmd_menu(a) -> int:
    return interactive()


_BENCH_CMDS = ("run", "report", "labels", "stats", "tui", "eval", "compare", "task")


def _cmd_bench(a) -> int:
    """Lệnh phụ. Cùng hàm với lệnh gốc, chỉ thêm dòng nhận diện."""
    print("công cụ benchmark nội bộ")
    rest = [part for part in (getattr(a, "bench_args", None) or []) if part != "--"]
    if not rest:
        print("Lệnh phụ: " + ", ".join(_BENCH_CMDS))
        return 0
    if rest[0] not in _BENCH_CMDS:
        print("Lệnh phụ: " + ", ".join(_BENCH_CMDS))
        return 2
    inner = build_parser().parse_args(rest)
    return inner.func(inner)


def _cmd_logs(a) -> int:
    from .activity import cmd_logs
    return cmd_logs(a)


def _cmd_dash(a) -> int:
    from .activity import cmd_dash
    return cmd_dash(a)


def _cmd_ingest(a) -> int:
    from .ingest import ingest_dir
    return ingest_dir(Path(a.trace_dir))


def _cmd_eval(a) -> int:
    from .bench import run_adversarial, run_eval
    if getattr(a, "suite", None) == "adversarial":
        return run_adversarial()
    return run_eval()


def _cmd_keys(a) -> int:
    from .keys import cmd_keys
    return cmd_keys(a)


def _cmd_export(a) -> int:
    from .activity import cmd_export
    return cmd_export(a)


# ------------------------------------------------------------------ parser
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="frog",
        description="Frog — harness đội nhóm agent (nền R0 shadow): giao việc, xem log, đo lường.",
        epilog="Gõ frog không kèm gì để vào phiên. Lệnh frog install đặt nó vào PATH.",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=f"frog {VERSION}")
    p.add_argument("--no-color", action="store_true", help="tắt màu")
    sub = p.add_subparsers(dest="cmd")

    r = sub.add_parser("run", help="chạy shadow và xuất trace + số liệu")
    r.add_argument("--out", default=DEFAULT_RUN, help="thư mục kết quả (mặc định: out)")
    r.add_argument("--cache-hit", type=float, default=C.CACHE_HIT)
    r.add_argument("--seed", type=int, default=C.SEED)
    r.add_argument("--n", type=int, default=0, help="chỉ chạy n tác vụ đầu")
    r.add_argument("--labels", default=None, help="phiếu nhãn NGƯỜI đã điền")
    r.add_argument("--quiet", action="store_true")
    r.add_argument("--json", action="store_true", help="in số liệu thô thay vì bảng")
    r.add_argument("--classifier", default="keyword", choices=["keyword", "llm"],
                   help="bộ phân loại T1b: keyword (miễn phí) · llm (cần API key)")
    r.add_argument("--provider", default=None, choices=["openrouter", "anthropic", "openai", "xai", "tavily", "brave", "serper"],
                   help="chỉ dùng khi --classifier llm")
    r.add_argument("--model", default=None, help="model cho classifier (mặc định theo vai)")
    r.add_argument("--api-key", dest="api_key", default=None,
                   help="khoá API; bỏ trống thì đọc biến môi trường")
    r.add_argument("--api-key-env", dest="api_key_env", default=None,
                   help="tên biến môi trường chứa khóa")
    r.add_argument("--base-url", dest="base_url", default=None,
                   help="đổi endpoint (dùng cho server giả khi kiểm thử)")
    r.add_argument("--no-cache", dest="no_cache", action="store_true",
                   help="không dùng cache kết quả classifier")
    r.set_defaults(func=cmd_run)

    rp = sub.add_parser("report", help="xem kết quả dạng bảng")
    rp.add_argument("--run", default=DEFAULT_RUN)
    rp.add_argument("--top", type=int, default=0, help="kèm n tác vụ tốn kém nhất")
    rp.add_argument("--json", action="store_true")
    rp.set_defaults(func=cmd_report)

    lb = sub.add_parser("labels", help="phiếu gán nhãn")
    lbs = lb.add_subparsers(dest="sub", required=True)
    le = lbs.add_parser("export", help="sinh phiếu (KHÔNG chứa đáp án)")
    le.add_argument("--out", default=f"{DEFAULT_RUN}/labels.csv")
    le.add_argument("--n", type=int, default=0)
    le.set_defaults(func=cmd_labels_export)
    ls = lbs.add_parser("status", help="xem đã điền bao nhiêu")
    ls.add_argument("--file", default=f"{DEFAULT_RUN}/labels.csv")
    ls.set_defaults(func=cmd_labels_status)
    lc = lbs.add_parser("check", help="kiểm tra phiếu hợp lệ")
    lc.add_argument("--file", default=f"{DEFAULT_RUN}/labels.csv")
    lc.set_defaults(func=cmd_labels_check)
    lt = lbs.add_parser("triage", help="danh sách ngắn nên gán nhãn trước")
    lt.add_argument("--out", default=f"{DEFAULT_RUN}/labels-triage.csv")
    lt.set_defaults(func=cmd_labels_triage)

    cp = sub.add_parser("compare", help="so hai lần chạy")
    cp.add_argument("--a", required=True)
    cp.add_argument("--b", required=True)
    cp.set_defaults(func=cmd_compare)

    tk = sub.add_parser("task", help="xem chi tiết một tác vụ trong trace")
    tk.add_argument("id")
    tk.add_argument("--run", default=DEFAULT_RUN)
    tk.set_defaults(func=cmd_task)

    tm = sub.add_parser("team", help="giao một task cho đội agent (GỌI MODEL THẬT)")
    tm.add_argument("task", nargs="?", default=None, help="yêu cầu, để trong dấu ngoặc kép")
    tm.add_argument("--resume", default=None, help="tiếp run từ checkpoint, không tính lại tiền đã chi")
    tm.add_argument("--surface", default="read_only",
                    choices=["read_only", "write_sandbox", "write_external", "egress_new"])
    tm.add_argument("--labels", default="internal",
                    help="nhãn dữ liệu cách nhau dấu phẩy (I3: do NGƯỜI khai, không do model)")
    tm.add_argument("--records", type=int, default=50)
    tm.add_argument("--dollars", type=float, default=0.0)
    tm.add_argument("--reversibility", default="C1", choices=["C1", "C2", "C3"])
    tm.add_argument("--output-type", dest="output_type", default="free_string",
                    choices=["free_string", "enum", "number", "bool", "id"])
    tm.add_argument("--provider", default=None, choices=["openrouter", "anthropic", "openai", "xai", "tavily", "brave", "serper"])
    tm.add_argument("--model", default=None, help="ép một model cho mọi vai")
    tm.add_argument("--base-url", dest="base_url", default=None)
    tm.add_argument("--max-tokens", dest="max_tokens", type=int, default=4096)
    tm.add_argument("--dry-run", dest="dry_run", action="store_true",
                    help="chỉ in kế hoạch phân vai, KHÔNG gọi model")
    tm.add_argument("--intake", choices=["on", "off"], default=None,
                    help="tuyến brief; mặc định bật khi làn từ 1")
    tm.add_argument("--clarify-max", dest="clarify_max", type=int, default=3,
                    help="trần vòng hỏi làm rõ brief")
    tm.add_argument("--brief", default=None, help="brief JSON đã duyệt, bỏ tầng hỏi")
    tm.add_argument("--require-evidence", dest="require_evidence", action="store_true",
                    help="không giao khi tiêu chí nghiệm thu chưa có bằng chứng")
    tm.add_argument("--approve", action="store_true", help="duyệt cổng người trước khi ghi")
    tm.add_argument("--price-in", dest="price_in", default=None,
                    help="giá USD mỗi triệu token, dạng IN,OUT")
    tm.add_argument("--oracle", choices=["on", "off"], default=None,
                    help="cổng oracle ở làn 2; mặc định on trừ bề mặt read_only")
    tm.add_argument("--workers", type=int, default=1,
                    help="số worker song song ở làn 2 (mặc định 1)")
    tm.add_argument("--sub-depth", dest="sub_depth", type=int, default=0,
                    help="số cấp đội con lồng nhau (0 = tắt; làn 2 mới mở được)")
    tm.add_argument("--out", default=None, help="thư mục Executor ghi kết quả")
    tm.set_defaults(func=cmd_team)

    from .handoff import cmd_giao
    gx = sub.add_parser("giao", help="phiếu từ câu nói thường, rồi bảng bàn giao")
    gx.add_argument("task", nargs="?", default=None, help="yêu cầu bằng lời")
    gx.add_argument("--run", default=None, help="chạy run đã lưu")
    gx.add_argument("--grant", action="append", default=[],
                    help="cấp đúng một lệnh; duyệt phiếu không cấp lệnh")
    gx.add_argument("--brief", default=None, help="brief JSON đã có, bỏ intake")
    gx.add_argument("--intake-model", dest="intake_model", default=None,
                    help="model chỉ cho intake; worker giữ --model")
    gx.add_argument("--approve-brief", dest="approve_brief", action="store_true",
                    help="duyệt phiếu đã xem, không cấp lệnh")
    gx.add_argument("--check-only", dest="check_only", action="store_true",
                    help="chỉ kiểm file có sẵn, không chạy worker và không bàn giao")
    gx.add_argument("--confirm", default=None, help="id tiêu chí người dùng tự xác nhận")
    gx.add_argument("--artifact", default=None, help="file gắn với xác nhận")
    gx.add_argument("--retry", action="store_true",
                    help="attempt mới trên cùng sổ cái, chỉ khi run đã kết thúc")
    gx.add_argument("--change", default=None, help="câu yêu cầu mới, không tiếp run cũ")
    gx.add_argument("--previous", default=None, help="id run cũ khi tạo run mới")
    gx.add_argument("--cwd", default=".")
    gx.add_argument("--provider", default=None,
                    choices=["openrouter", "anthropic", "openai", "xai", "tavily", "brave", "serper"])
    gx.add_argument("--model", default=None)
    gx.add_argument("--base-url", dest="base_url", default=None)
    gx.add_argument("--max-tokens", dest="max_tokens", type=int, default=4096)
    gx.add_argument("--price-in", dest="price_in", default=None,
                    help="giá USD mỗi triệu token, dạng IN,OUT")
    gx.add_argument("--autonomy", choices=["watch", "walk-away", "direct"], default=None,
                    help="nấc tự chủ; mặc định watch, code quyết, không phải model")
    gx.add_argument("--accept", nargs="?", const="*", default=None,
                    help="với `giao box`: duyệt một run hoặc cả lô")
    gx.add_argument("--pull", default=None, help="với `giao box`: lôi một run ra xem lý do")
    gx.set_defaults(func=cmd_giao)

    from .intake import cmd_brief
    br = sub.add_parser("brief", help="kiểm tra hoặc chép brief JSON")
    bsub = br.add_subparsers(dest="brief_cmd", required=True)
    bv = bsub.add_parser("validate", help="kiểm schema và in hash")
    bv.add_argument("path")
    bv.set_defaults(func=cmd_brief)
    for name in ("save", "load"):
        bp = bsub.add_parser(name, help="chép brief đã đúng schema")
        bp.add_argument("src")
        bp.add_argument("dest")
        bp.set_defaults(func=cmd_brief)

    # ---- agent CLI kiểu phiên làm việc ----
    def _agent_args(sp, positional):
        sp.add_argument("--cwd", default=".", help="thư mục gốc cho công cụ")
        sp.add_argument("--mode", default="default", choices=["plan", "default", "acceptEdits", "bypass"])
        sp.add_argument("--model", default=None)
        sp.add_argument("--provider", default=None, choices=["openrouter", "anthropic", "openai", "xai", "tavily", "brave", "serper"])
        sp.add_argument("--base-url", dest="base_url", default=None)
        sp.add_argument("--max-tokens", dest="max_tokens", type=int, default=4096)
        sp.add_argument("--no-stream", dest="no_stream", action="store_true")
        sp.add_argument("--protocol", default="auto", choices=["auto", "native", "text"],
                        help="auto (mặc định) · native (native tool-calling) · text (giao thức văn bản)")
        sp.add_argument("--max-turns", dest="max_turns", type=int, default=0,
                        help="trần vòng gọi công cụ (0 = mặc định 25)")
        sp.add_argument("--price-in", dest="price_in", default=None,
                        help="giá USD mỗi triệu token, dạng IN,OUT")
        sp.add_argument("--max-budget-usd", dest="max_budget_usd", type=float, default=None,
                        help="dừng ngay khi chi phí lượt vượt mức này (USD)")
        if positional:
            sp.add_argument("task", help="yêu cầu, trong dấu ngoặc kép")
        sp.set_defaults(**{})

    ag = sub.add_parser("agent", help="một lượt headless, in envelope JSON (giống openclaw agent exec)")
    _agent_args(ag, positional=True)
    ag.add_argument("--json", action="store_true", help="envelope JSON ra stdout")
    ag.add_argument("--yes", action="store_true", help="tự duyệt mọi cổng (CẨN THẬN)")
    ag.add_argument("--surface", default="read_only",
                    choices=["read_only", "write_sandbox", "write_external", "egress_new"])
    ag.add_argument("--labels", default="internal",
                    help="nhãn dữ liệu cách nhau dấu phẩy")
    ag.add_argument("--session-id", dest="session_id", default=None)
    ag.set_defaults(func=cmd_agent)

    ch = sub.add_parser("chat", help="mở phiên tương tác (REPL)")
    _agent_args(ch, positional=False)
    ch.add_argument("task", nargs="?", default=None, help="nếu có: chạy một lượt rồi thoát")
    ch.add_argument("--team", action="store_true", help="định tuyến qua làn + đội nhiều vai")
    ch.add_argument("--resume", default=None, help="mở lại phiên đã lưu")
    ch.set_defaults(func=lambda a: __import__("frog.repl", fromlist=["repl"]).repl(a))

    pn = sub.add_parser("panel", help="hội đồng phản biện đa agent soi một thiết kế đo")
    pn.add_argument("question", help="câu hỏi cho hội đồng")
    pn.add_argument("--file", default=None, help="tệp cần soi")
    pn.add_argument("--rounds", type=int, default=2)
    pn.add_argument("--offline", action="store_true", help="không gọi model, tính trực tiếp")
    pn.add_argument("--provider", default=None, choices=["openrouter", "anthropic", "openai", "xai", "tavily", "brave", "serper"])
    pn.add_argument("--model", default=None)
    pn.add_argument("--base-url", dest="base_url", default=None)
    pn.add_argument("--out", default=None, help="ghi báo cáo markdown")
    pn.set_defaults(func=lambda a: __import__("frog.panel", fromlist=["cmd_panel"]).cmd_panel(a))

    sx = sub.add_parser("stats", help="bảng điều khiển số đo của một lần chạy")
    sx.add_argument("--run", default=DEFAULT_RUN, help="thư mục lần chạy")
    sx.add_argument("--metric", default="cost",
                    choices=["cost", "tasks", "audit", "vc", "latency"],
                    help="chỉ số lớn hiển thị")
    sx.set_defaults(func=cmd_stats)

    ig = sub.add_parser("ingest", help="nạp trace team vào 16 chỉ số, ghi nguồn real")
    ig.add_argument("trace_dir", help="thư mục có trace.json của team hoặc xích hash")
    ig.set_defaults(func=_cmd_ingest)

    tu = sub.add_parser("tui", help="TUI toàn màn hình (curses, không thêm phụ thuộc)")
    tu.add_argument("--run", default=DEFAULT_RUN, help="thư mục lần chạy")
    tu.add_argument("--dump", nargs="?", const="tổng quan", default=None,
                    choices=["tổng quan", "tác vụ", "làn", "nhãn", "trợ giúp"],
                    help="in một khung ra văn bản thay vì mở TUI")
    tu.set_defaults(func=cmd_tui)

    dcp = sub.add_parser("detect-compare",
                         help="so bộ dò từ khoá với model đọc nội dung (cần key)")
    dcp.add_argument("--n", type=int, default=40, help="số tác vụ, lấy mẫu PHÂN TẦNG (mặc định 40)")
    dcp.add_argument("--api-key", dest="api_key", default=None, help="khoá; mặc định đọc biến môi trường")
    dcp.add_argument("--provider", default=None, choices=["openrouter", "anthropic", "openai", "xai", "tavily", "brave", "serper"])
    dcp.add_argument("--model", default=None)
    dcp.add_argument("--base-url", dest="base_url", default=None)
    dcp.add_argument("--out", default=None, help="ghi báo cáo JSON")
    dcp.set_defaults(func=cmd_detect_compare)

    dc = sub.add_parser("doctor", help="kiểm tra môi trường")
    dc.add_argument("--out", default="out", help="thư mục thử ghi")
    dc.set_defaults(func=cmd_doctor)

    st = sub.add_parser("selftest", help="kiểm tra bất biến")
    st.set_defaults(func=cmd_selftest)

    vf = sub.add_parser("verify", help="kiểm xích hash của một thư mục đã ghi")
    vf.add_argument("dir", help="thư mục có trace.jsonl và manifest.json")
    vf.set_defaults(func=cmd_verify)

    ev = sub.add_parser("eval", help="chấm vài việc local: qua/fail, vòng, tiền")
    ev.add_argument("--suite", default=None, choices=["adversarial"],
                    help="adversarial: 50 case viết tay, in precision/recall theo nhóm")
    ev.set_defaults(func=_cmd_eval)

    lg = sub.add_parser("logs", help="xem log các phiên agent")
    lg.add_argument("session", nargs="?", default=None, help="id phiên để xem chi tiết")
    lg.add_argument("--limit", type=int, default=0, help="chỉ hiện n phiên gần nhất")
    lg.set_defaults(func=_cmd_logs)

    dsh = sub.add_parser("dash", help="bảng điều khiển agent (kiểu opencode)")
    dsh.set_defaults(func=_cmd_dash)

    ky = sub.add_parser("keys", help="cài khoá API cho từng nhà cung cấp")
    kys = ky.add_subparsers(dest="action")
    kys.add_parser("status", help="xem trạng thái khoá").set_defaults(func=_cmd_keys)
    kset = kys.add_parser("set", help="nhập khoá (hỏi từng nhà cung cấp)")
    kset.add_argument("--provider", default=None, choices=["openrouter", "anthropic", "openai", "xai", "tavily", "brave", "serper"])
    kset.set_defaults(func=_cmd_keys)
    kcl = kys.add_parser("clear", help="xoá một khoá")
    kcl.add_argument("--provider", required=True, choices=["openrouter", "anthropic", "openai", "xai", "tavily", "brave", "serper"])
    kcl.set_defaults(func=_cmd_keys)
    kys.add_parser("path", help="in đường dẫn tệp khoá").set_defaults(func=_cmd_keys)
    ky.set_defaults(func=_cmd_keys)

    ex = sub.add_parser("export", help="tải dữ liệu chi tiết ra file để mở xem")
    ex.add_argument("--what", default="all", choices=["all", "sessions", "lab"])
    ex.add_argument("--format", default="md", choices=["md", "json", "csv"])
    ex.add_argument("--run", default=DEFAULT_RUN, help="thư mục lần chạy cho phần lab")
    ex.add_argument("--out", default=None, help="tên tệp (mặc định: r0-shadow-export-<ngày>.md)")
    ex.set_defaults(func=_cmd_export)

    mn = sub.add_parser("menu", help="mở menu giao, team, agent, keys, doctor")
    mn.set_defaults(func=_cmd_menu)

    bn = sub.add_parser("bench", help="công cụ benchmark nội bộ")
    bn.add_argument("bench_args", nargs=argparse.REMAINDER)
    bn.set_defaults(func=_cmd_bench)

    ins = sub.add_parser("install",
                         help="đặt lệnh frog vào PATH — gõ frog ở terminal nào cũng vào phiên")
    ins.set_defaults(func=_cmd_install)
    return p


def _cmd_install(a) -> int:
    from .install_path import install
    info = install()
    print()
    ui.masthead([
        ui.c("frog", "bright", "bold") + ui.c("  đã cài xong", "dim"),
        ui.c(str(info["shim"]), "text"),
    ])
    print()
    if info.get("path_updated"):
        ui.note("Đã thêm vào PATH. Mở một terminal mới rồi gõ frog.", "ok")
    elif info.get("on_path"):
        ui.note("PATH đã có sẵn. Mở một terminal mới rồi gõ frog.", "ok")
    else:
        ui.note("Chưa thêm được vào PATH.", "warn")
    return 0


def note_argv_key(args) -> list[dict]:
    """Cảnh báo khi khóa đi qua argv. Trace không chứa giá trị khóa."""
    trace: list[dict] = []
    env_name = getattr(args, "api_key_env", None)
    if env_name:
        args.api_key = os.environ.get(env_name) or getattr(args, "api_key", None)
    if getattr(args, "api_key", None):
        print("Cảnh báo: khóa trên argv có thể lọt lịch sử shell. Dùng --api-key-env.")
        trace.append({"kind": "argv_key_warning"})
    args.argv_trace = trace
    return trace


_SHIM_UNTIL = "2027-04-16"
_shim_said: set[str] = set()


def _shim_warn(kind: str, text: str) -> None:
    if kind in _shim_said:
        return
    _shim_said.add(kind)
    print(text, file=sys.stderr)


def deprecated_mira(argv=None) -> int:
    """Cửa vào của lệnh mira. Một cảnh báo, rồi gọi frog."""
    _shim_warn("mira", f"mira sẽ bị gỡ sau {_SHIM_UNTIL}. Hãy gọi frog.")
    return main(argv)


def deprecated_main(argv=None) -> int:
    """Cửa vào của lệnh r0 và r0-shadow. Một cảnh báo, rồi gọi frog."""
    _shim_warn("legacy", f"r0 và r0-shadow sẽ bị gỡ sau {_SHIM_UNTIL}. Hãy gọi frog.")
    return main(argv)


def main(argv=None) -> int:
    from .keys import migrate_user_home
    migrate_user_home()
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--no-color" in argv:
        ui.set_color(False)
        argv = [a for a in argv if a != "--no-color"]
    if not argv:
        if sys.stdin.isatty() and sys.stdout.isatty():
            return _open()
        build_parser().print_help()
        return 0
    args = build_parser().parse_args(argv)
    note_argv_key(args)
    if not getattr(args, "cmd", None):
        build_parser().print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
