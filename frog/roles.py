"""Danh mục vai cho đơn làm web và luật tuyển theo cỡ đơn.

Intake đề xuất sơ đồ nhân sự. Code giữ phần còn lại:
  - tên vai phải có trong danh mục, hoặc là vai ngoài danh mục có đủ loại và việc;
  - quyền tool lấy từ danh mục, đề xuất quyền ghi của intake bị bỏ;
  - cỡ đơn cuối là cỡ lớn hơn giữa intake và code đọc từ câu đơn, code không hạ cỡ;
  - vai bắt buộc theo cỡ đơn được thêm, khách không bỏ được;
  - đơn web ít nhất 4 vai và phải có vai review.
Làn, cổng người và trần vẫn do build_plan quyết (I5). Ghi vẫn chỉ qua Executor (I1).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

SIZES = ("nho", "vua", "lon")
SIZE_LABEL = {"nho": "nhỏ", "vua": "vừa", "lon": "lớn"}
KINDS = ("manage", "make", "review", "handoff")
KIND_LABEL = {"manage": "quản lý", "make": "làm", "review": "kiểm", "handoff": "bàn giao"}
# Ánh xạ vào kiến trúc cũ: reviewer là verifier, người làm là worker.
SLOT = {"manage": "planner", "make": "worker", "review": "verifier", "handoff": "worker"}
READ_ONLY = ("read_file", "list_dir", "grep", "glob")
WEB_MIN_ROLES = 4
FALLBACK_ROLES = ("planner", "worker", "verifier")

VERDICT_PROTOCOL = (
    "Trả đúng một object JSON, không chữ nào khác, với các khóa verdict, reasons, evidence, "
    "confidence. verdict chỉ là PASS hoặc FAIL. PASS chỉ khi mọi mục trong checklist đạt. "
    "reasons là danh sách lý do theo từng mục, không rỗng. evidence trích chỗ trong sản phẩm. "
    "confidence là số từ 0 đến 1."
)
PROPOSE_ONLY = ("Bạn chỉ đề xuất. File chỉ được ghi bởi Executor sau khi khách duyệt cổng. "
                "Không tự cấp quyền ghi, không bỏ qua bước kiểm.")
FILE_BLOCKS = ("Mỗi file nằm trong một khối code mở bằng ba dấu huyền, tên ngôn ngữ và đường dẫn "
               "tương đối, ví dụ ```html site/index.html```.")


@dataclass(frozen=True)
class RoleSpec:
    name: str
    group: str
    kind: str
    title: str
    duty: str
    system_prompt: str
    allowed_tools: tuple = READ_ONLY
    cap_usd: float = 0.25
    backend: bool = False


def _spec(name, group, kind, title, duty, body, *, cap=0.25, backend=False) -> RoleSpec:
    head = f"Mã vai: {name}\nBạn là {title} trong một công ty làm web. "
    tail = VERDICT_PROTOCOL if kind == "review" else PROPOSE_ONLY
    return RoleSpec(name, group, kind, title, duty, head + body + "\n" + tail,
                    cap_usd=cap, backend=backend)


POOL: dict[str, RoleSpec] = {s.name: s for s in (
    _spec("product_manager", "Quản lý", "manage", "product manager",
          "phạm vi và tiêu chí nghiệm thu",
          "Chốt phạm vi trang: trong phạm vi, ngoài phạm vi, đối tượng xem, ngôn ngữ. "
          "Viết tiêu chí nghiệm thu đánh số; mỗi tiêu chí nói ai kiểm và kiểm bằng cách nào. "
          "Ghi rủi ro phạm vi và câu hỏi còn mở. Không viết code.", cap=0.15),
    _spec("project_coordinator", "Quản lý", "manage", "điều phối dự án",
          "tiến độ và phụ thuộc giữa vai",
          "Lập thứ tự việc giữa các vai, chỉ ra phụ thuộc, việc nào làm song song, "
          "mốc bàn giao và ai chặn ai. Trả bảng phân công ngắn.", cap=0.15),
    _spec("ux_designer", "Thiết kế", "make", "UX designer",
          "bố cục, luồng người dùng, responsive",
          "Vẽ bố cục bằng chữ: các khối trang theo thứ tự (header, giới thiệu, tính năng, "
          "lời kêu gọi, footer), luồng đọc của người xem, điểm ngắt màn hình di động và máy tính, "
          "thứ tự ưu tiên nội dung trên màn hình nhỏ. Không viết code."),
    _spec("ui_designer", "Thiết kế", "make", "UI designer",
          "màu thương hiệu, typography, component",
          "Đưa bảng màu bằng mã hex kèm tỉ lệ tương phản chữ trên nền (tối thiểu 4.5:1), "
          "font và cỡ chữ cho tiêu đề và thân bài, component chính (nút, thẻ, liên kết) "
          "và trạng thái hover, focus."),
    _spec("content_writer", "Thiết kế", "make", "content writer",
          "văn phong và thông điệp trang",
          "Viết thông điệp chính một câu, tiêu đề từng khối, đoạn giới thiệu, lời kêu gọi hành động. "
          "Giọng văn theo đối tượng xem. Không hứa tính năng sản phẩm không có."),
    _spec("brand_designer", "Thiết kế", "make", "brand designer",
          "nhận diện và mood board",
          "Đề xuất nhận diện: khẩu hiệu, cách viết tên, mood board bằng từ khóa hình ảnh, "
          "logo chữ có thể dựng bằng CSS. Không cần file ảnh."),
    _spec("frontend_engineer", "Kỹ thuật", "make", "frontend engineer",
          "HTML, CSS, JS",
          "Viết trang hoàn chỉnh bằng HTML, CSS và JS cần thiết theo bố cục, nội dung và màu "
          "của các vai trước. Có meta viewport, ảnh có alt, form có label, không thư viện ngoài "
          "khi không cần. " + FILE_BLOCKS, cap=0.35),
    _spec("backend_api_engineer", "Kỹ thuật", "make", "backend API engineer",
          "API nhận và trả dữ liệu",
          "Đặc tả API: endpoint, method, dữ liệu vào ra, mã lỗi, kiểm dữ liệu vào phía server, "
          "giới hạn tần suất, nơi lưu. Viết code server khi đơn cần. " + FILE_BLOCKS,
          cap=0.35, backend=True),
    _spec("backend_db_engineer", "Kỹ thuật", "make", "backend database engineer",
          "cơ sở dữ liệu và vòng đời dữ liệu",
          "Thiết kế lược đồ dữ liệu: bảng, cột, khóa, chỉ mục; dữ liệu giữ bao lâu, xóa theo yêu cầu "
          "người dùng ra sao, sao lưu thế nào.", backend=True),
    _spec("auth_engineer", "Kỹ thuật", "make", "auth engineer",
          "đăng nhập và phân quyền",
          "Thiết kế đăng nhập, phiên, băm mật khẩu, phân quyền, khôi phục tài khoản, "
          "chống dò mật khẩu.", backend=True),
    _spec("integration_engineer", "Kỹ thuật", "make", "integration engineer",
          "gọi dịch vụ ngoài",
          "Chọn và nối dịch vụ ngoài (gửi email, nhận tin, thanh toán): khóa API nằm ở server, "
          "xử lý lỗi và hết giờ, không gửi dữ liệu thừa ra ngoài.", backend=True),
    _spec("devops_engineer", "Kỹ thuật", "make", "devops engineer",
          "triển khai, CI/CD, hosting",
          "Chọn nơi host (tĩnh hay có server), cách triển khai, HTTPS, tên miền, bước build "
          "trong CI, chi phí duy trì hằng tháng."),
    _spec("perf_engineer", "Kỹ thuật", "make", "performance engineer",
          "tốc độ tải",
          "Đặt ngân sách tải (KB cho HTML, CSS, JS, ảnh), tối ưu ảnh, lazy-load, cache, "
          "cách đo bằng Lighthouse và ngưỡng đạt."),
    _spec("qa_reviewer", "Chất lượng", "review", "QA reviewer",
          "kiểm chức năng trước giao",
          "Kiểm sản phẩm theo checklist: (1) mọi tiêu chí nghiệm thu của product manager có bằng "
          "chứng trong sản phẩm; (2) trang mở được, HTML đóng thẻ đúng; (3) liên kết và nút có đích; "
          "(4) hiển thị được trên di động (meta viewport, bố cục co giãn); (5) không còn chữ giữ "
          "chỗ như lorem ipsum hay TODO; (6) nội dung đúng đơn của khách.", cap=0.15),
    _spec("security_reviewer", "Chất lượng", "review", "security reviewer",
          "bảo mật và dữ liệu form",
          "Kiểm theo checklist form và dữ liệu: (1) form có kiểm dữ liệu phía server, không chỉ "
          "phía trình duyệt; (2) dữ liệu form gửi đi đâu, ai đọc, giữ bao lâu, người dùng có được "
          "báo; (3) chỉ chạy qua HTTPS; (4) chống spam và bot; (5) khóa API không nằm ở frontend; "
          "(6) chống XSS và injection khi hiển thị lại dữ liệu; (7) email đã lưu có cách hủy đăng ký. "
          "Trang không có form thì ghi rõ từng mục không áp dụng.", cap=0.15),
    _spec("a11y_reviewer", "Chất lượng", "review", "accessibility reviewer",
          "khả năng truy cập",
          "Kiểm theo checklist WCAG 2.1 AA: tương phản chữ, alt cho ảnh, label cho form, thứ tự tab, "
          "focus nhìn thấy được, thuộc tính lang của trang, tiêu đề phân cấp đúng.", cap=0.15),
    _spec("content_reviewer", "Chất lượng", "review", "content reviewer",
          "rà văn bản",
          "Kiểm theo checklist văn bản: chính tả, xưng hô nhất quán, không hứa tính năng không có, "
          "giọng hợp đối tượng, tiêu đề ngắn rõ.", cap=0.15),
    _spec("handoff_editor", "Bàn giao", "handoff", "biên tập bàn giao",
          "tổng hợp sản phẩm và hướng dẫn bàn giao",
          "Tổng hợp gói bàn giao: danh sách file và mỗi file để làm gì, cách mở xem trang, cách sửa "
          "nội dung, việc còn lại, vai nào đã kiểm gì và kết quả.", cap=0.15),
    _spec("tech_writer", "Bàn giao", "handoff", "tech writer",
          "tài liệu sử dụng",
          "Viết tài liệu dùng: cài, chạy, cập nhật nội dung, câu hỏi thường gặp.", cap=0.15),
)}

# Thứ tự chạy: quản lý, thiết kế, kỹ thuật, kiểm, bàn giao.
ORDER = tuple(POOL)

REQUIRED = {
    "nho": ("product_manager", "ux_designer", "frontend_engineer", "qa_reviewer", "handoff_editor"),
}
REQUIRED["vua"] = REQUIRED["nho"] + ("backend_api_engineer", "security_reviewer")
REQUIRED["lon"] = REQUIRED["vua"] + ("backend_db_engineer", "project_coordinator")
# Tuyển theo mặc định, trừ khi intake ghi lý do không tuyển.
EXPECTED = {
    "nho": (),
    "vua": ("devops_engineer", "content_writer", "integration_engineer"),
    "lon": ("devops_engineer", "content_writer", "integration_engineer",
            "a11y_reviewer", "perf_engineer"),
}
RULE_REASON = {
    "nho": "đơn nhỏ vẫn cần người chốt phạm vi, thiết kế, làm, kiểm và giao",
    "vua": "đơn vừa có dữ liệu người dùng: cần backend nhận lưu và người kiểm bảo mật form",
    "lon": "đơn lớn: dữ liệu và lưu lượng cần người lo cơ sở dữ liệu và điều phối nhiều vai",
}
SIGNAL_REQUIRED = {"auth": ("auth_engineer",), "payment": ("integration_engineer",)}
SIGNAL_REASON = {
    "auth_engineer": "câu đơn có đăng nhập hoặc tài khoản",
    "integration_engineer": "câu đơn có thanh toán qua dịch vụ ngoài",
}


def required_for(size: str, found: list[str]) -> tuple:
    extra = tuple(name for sig in found for name in SIGNAL_REQUIRED.get(sig, ()))
    return REQUIRED[size] + tuple(n for n in extra if n not in REQUIRED[size])


DEFAULT_SKIP = {
    "nho": "đơn nhỏ: trang tĩnh, không lưu dữ liệu người dùng",
    "vua": "đơn vừa chưa cần vai này",
    "lon": "đơn lớn chưa cần vai này",
}

_SIGNALS = {
    "web": r"\bweb\b|website|trang web|trang chủ|trang giới thiệu|landing|homepage|\bhtml\b|\bsite\b",
    "form": r"\bform\b|biểu mẫu|đăng ký|liên hệ|nhận tin|newsletter|subscribe",
    "store": r"\blưu\b|cơ sở dữ liệu|database|danh sách email|lưu trữ",
    "cms": r"\bcms\b|quản trị nội dung|\bblog\b|bài viết|trang quản trị|\badmin\b",
    "integration": r"tích hợp|gửi email|mailchimp|api ngoài|dịch vụ ngoài",
    "pages": r"nhiều trang|\b(?:[2-9]|\d{2,})\s*trang\b",
    "auth": r"đăng nhập|\blogin\b|tài khoản|mật khẩu|phân quyền",
    "payment": r"thanh toán|payment|giỏ hàng|checkout|stripe|vnpay|momo",
    "sensitive": r"nhạy cảm|y tế|sức khỏe|căn cước|cccd|thẻ tín dụng",
    "traffic": r"lưu lượng cao|nhiều người dùng|hàng triệu|high traffic",
}


def signals_of(text: str) -> list[str]:
    low = (text or "").lower()
    return [name for name, pattern in _SIGNALS.items() if re.search(pattern, low)]


def is_web_order(text: str) -> bool:
    return "web" in signals_of(text)


def infer_size(text: str) -> tuple[str, list[str]]:
    """Cỡ đơn code đọc được từ câu đơn. Đây là sàn: intake nâng được, không hạ được."""
    found = signals_of(text)
    if {"auth", "payment", "sensitive", "traffic"} & set(found):
        return "lon", found
    if ({"form", "store"} <= set(found)) or ({"cms", "integration", "pages"} & set(found)):
        return "vua", found
    return "nho", found


def _bigger(a: str, b: str) -> str:
    return a if SIZES.index(a) >= SIZES.index(b) else b


_NAME = re.compile(r"^[a-z][a-z0-9_]{2,40}$")


def _extra_spec(item: dict) -> RoleSpec | None:
    """Vai ngoài danh mục: đủ tên, loại, việc. Quyền vẫn chỉ đọc."""
    name = str(item.get("role") or item.get("name") or "")
    kind = str(item.get("kind") or "")
    task = str(item.get("task") or "").strip()
    if not _NAME.match(name) or kind not in KINDS or not task or name in POOL:
        return None
    title = str(item.get("title") or name.replace("_", " ")).strip()[:60]
    body = f"Việc của bạn: {task}. Làm như người làm nghề {title} thật, nêu giả định và chỗ thiếu."
    return _spec(name, "Ngoài danh mục", kind, title, task, body)


def spec_of(staffing: dict | None, role: str) -> RoleSpec | None:
    if role in POOL:
        return POOL[role]
    for item in (staffing or {}).get("hired") or []:
        if item.get("role") == role and item.get("origin_kind") == "extra":
            return _extra_spec(item)
    return None


def _row(spec: RoleSpec, *, task: str, reason: str, origin: str) -> dict:
    return {"role": spec.name, "kind": spec.kind, "group": spec.group, "title": spec.title,
            "task": task or spec.duty, "reason": reason, "origin": origin,
            "tools": list(spec.allowed_tools), "cap_usd": spec.cap_usd}


def settle(order: str, proposal, *, hire=(), drop=()) -> dict:
    """Đề xuất của intake qua luật của code. Trả sơ đồ cuối để khách duyệt."""
    notes: list[str] = []
    errors: list[str] = []
    web = is_web_order(order)
    code_size, found = infer_size(order)
    hire = [h.strip() for h in hire if h and h.strip()]
    drop = [d.strip() for d in drop if d and d.strip()]

    usable = isinstance(proposal, dict) and isinstance(proposal.get("hired"), list) \
        and any(isinstance(item, dict) for item in proposal.get("hired"))
    if not usable and not hire:
        why = "intake không trả sơ đồ" if not proposal else "sơ đồ của intake hỏng"
        out = {"version": 1, "web": web, "fallback": True, "fallback_reason": why,
               "size": {"intake": None, "code": code_size, "final": code_size, "signals": found},
               "backend": {"needed": False, "reason": "fallback không quyết backend", "roles": [],
                           "origin": "code"},
               "hired": [{"role": r, "kind": {"planner": "manage", "worker": "make",
                                              "verifier": "review"}[r],
                          "group": "fallback", "title": r, "task": "", "reason": why,
                          "origin": "fallback", "tools": list(READ_ONLY), "cap_usd": 0.25}
                         for r in FALLBACK_ROLES],
               "considered": [], "notes": [f"fallback 3 vai cũ: {why}"], "errors": []}
        if web:
            need = ",".join(REQUIRED[code_size])
            out["errors"].append(
                f"đơn web cần ít nhất {WEB_MIN_ROLES} vai, sơ đồ đang là fallback 3 vai. "
                f"Thêm vai bằng --hire {need}")
        return out

    proposal = proposal if isinstance(proposal, dict) else {}
    claimed = str(proposal.get("size") or "").strip().lower()
    claimed = {"nhỏ": "nho", "vừa": "vua", "lớn": "lon"}.get(claimed, claimed)
    intake_size = claimed if claimed in SIZES else None
    final = _bigger(intake_size or "nho", code_size)
    if intake_size and final != intake_size:
        notes.append(f"code nâng cỡ đơn từ {SIZE_LABEL[intake_size]} lên {SIZE_LABEL[final]} "
                     f"vì câu đơn có: {', '.join(found)}")

    hired: dict[str, dict] = {}
    considered: dict[str, dict] = {}
    for item in proposal.get("hired") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("role") or "").strip()
        asked_tools = item.get("allowed_tools") or item.get("tools") or []
        if isinstance(asked_tools, list) and any(str(t) not in READ_ONLY for t in asked_tools):
            notes.append(f"bỏ quyền {', '.join(str(t) for t in asked_tools)} intake đề xuất cho "
                         f"{name}: quyền lấy từ danh mục")
        spec = POOL.get(name)
        if spec is None:
            spec = _extra_spec(item)
            if spec is None:
                considered[name or "?"] = {"role": name or "?", "origin": "code",
                                           "reason": "không có trong danh mục và thiếu loại hoặc việc"}
                continue
            row = _row(spec, task=str(item.get("task") or ""), reason=str(item.get("reason") or ""),
                       origin="intake")
            row["origin_kind"] = "extra"
            hired[name] = row
            continue
        hired[name] = _row(spec, task=str(item.get("task") or ""),
                           reason=str(item.get("reason") or "").strip() or "intake chọn",
                           origin="intake")
    for item in proposal.get("considered") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("role") or "").strip()
        reason = str(item.get("reason") or "").strip()
        if name in POOL and name not in hired and reason:
            considered[name] = {"role": name, "reason": reason, "origin": "intake"}

    for name in required_for(final, found):
        if name not in hired:
            reason = (SIGNAL_REASON[name] if name in SIGNAL_REASON and name not in REQUIRED[final]
                      else RULE_REASON[final])
            hired[name] = _row(POOL[name], task="", reason=f"bắt buộc: {reason}",
                               origin="luật cỡ đơn")
            considered.pop(name, None)
    for name in EXPECTED[final]:
        if name not in hired and name not in considered:
            hired[name] = _row(POOL[name], task="", reason=f"mặc định của đơn {SIZE_LABEL[final]}",
                               origin="luật cỡ đơn")

    for name in hire:
        spec = POOL.get(name)
        if spec is None:
            errors.append(f"không có vai {name} trong danh mục")
            continue
        hired[name] = _row(spec, task="", reason="khách thêm", origin="khách")
        considered.pop(name, None)
    for name in drop:
        if name in required_for(final, found):
            errors.append(f"không bỏ được {name}: bắt buộc với đơn {SIZE_LABEL[final]}")
            continue
        if name in hired:
            hired.pop(name)
            considered[name] = {"role": name, "reason": "khách bỏ", "origin": "khách"}

    for name in ORDER:
        if name not in hired and name not in considered:
            considered[name] = {"role": name, "reason": DEFAULT_SKIP[final], "origin": "code"}

    rows = [hired[n] for n in ORDER if n in hired] + \
           [row for n, row in hired.items() if n not in POOL]
    backend_roles = [row["role"] for row in rows if POOL.get(row["role"]) and POOL[row["role"]].backend]
    said = proposal.get("backend") if isinstance(proposal.get("backend"), dict) else {}
    if backend_roles:
        reason = str(said.get("reason") or "").strip() if said.get("needed") else ""
        backend = {"needed": True, "roles": backend_roles,
                   "reason": reason or RULE_REASON[final],
                   "origin": "intake" if said.get("needed") else "luật cỡ đơn"}
    else:
        backend = {"needed": False, "roles": [],
                   "reason": str(said.get("reason") or "").strip() or DEFAULT_SKIP[final],
                   "origin": "intake" if said else "code"}
    out = {"version": 1, "web": web, "fallback": False, "fallback_reason": "",
           "size": {"intake": intake_size, "code": code_size, "final": final, "signals": found},
           "backend": backend, "hired": rows,
           "considered": [considered[n] for n in ORDER if n in considered] +
                         [row for n, row in considered.items() if n not in POOL],
           "notes": notes, "errors": errors}
    errors.extend(validate_settled(out, strict=False))
    return out


_SETTLED_KEYS = {"version", "web", "fallback", "fallback_reason", "size", "backend",
                 "hired", "considered", "notes", "errors"}


def validate_settled(st, *, strict: bool = True) -> list[str]:
    """Sơ đồ đã duyệt. Khóa lạ, vai lạ, quyền ghi, ít vai, thiếu vai kiểm đều là lỗi."""
    if not isinstance(st, dict):
        return ["sơ đồ nhân sự không phải object"]
    bad = []
    if strict and set(st) - _SETTLED_KEYS:
        bad.append("sơ đồ nhân sự có khóa lạ: " + ", ".join(sorted(set(st) - _SETTLED_KEYS)))
    hired = st.get("hired")
    if not isinstance(hired, list) or not all(isinstance(r, dict) for r in hired):
        return bad + ["sơ đồ nhân sự thiếu danh sách vai đã tuyển"]
    if st.get("fallback"):
        names = [r.get("role") for r in hired]
        if names != list(FALLBACK_ROLES):
            bad.append("fallback phải đúng 3 vai cũ")
        if st.get("web"):
            bad.append(f"đơn web cần ít nhất {WEB_MIN_ROLES} vai, fallback chỉ có 3")
        return bad
    for row in hired:
        name = row.get("role")
        spec = POOL.get(name) or (_extra_spec(row) if row.get("origin_kind") == "extra" else None)
        if spec is None:
            bad.append(f"vai {name} không có trong danh mục")
            continue
        if row.get("kind") != spec.kind:
            bad.append(f"vai {name} sai loại")
        if any(tool not in READ_ONLY for tool in row.get("tools") or []):
            bad.append(f"vai {name} có quyền ghi; ghi chỉ qua Executor")
    if st.get("web") and len(hired) < WEB_MIN_ROLES:
        bad.append(f"đơn web cần ít nhất {WEB_MIN_ROLES} vai, sơ đồ có {len(hired)}")
    if st.get("web") and not any(r.get("kind") == "review" for r in hired):
        bad.append("đơn web phải có vai kiểm")
    return bad


def run_order(st: dict) -> list[str]:
    """Thứ tự chạy: quản lý, làm, kiểm, bàn giao. Giữ thứ tự danh mục trong từng loại."""
    rows = [r for r in (st or {}).get("hired") or [] if isinstance(r, dict)]
    return [r["role"] for kind in KINDS for r in rows if r.get("kind") == kind]


def staffing_prompt() -> str:
    """Phần nhúng vào intake của frog team: danh mục vai, luật cỡ đơn, khuôn trả về."""
    lines = ["DANH MỤC VAI (tuyển từ đây; cần vai ngoài danh mục thì ghi kind và task):"]
    for spec in POOL.values():
        lines.append(f"- {spec.name} ({spec.group}, {KIND_LABEL[spec.kind]}): {spec.duty}")
    lines += [
        "LUẬT TUYỂN THEO CỠ ĐƠN (tham khảo):",
        "- nho: trang tĩnh ít trang, không lưu dữ liệu người dùng; khoảng 5-7 vai; cân nhắc "
        "content_writer, security_reviewer (form gửi dữ liệu đi đâu?), devops_engineer.",
        "- vua: nhiều trang, form lưu dữ liệu, CMS, tích hợp ngoài; thêm backend_api_engineer, "
        "security_reviewer (bắt buộc), devops_engineer, content_writer, integration_engineer.",
        "- lon: đăng nhập, thanh toán, dữ liệu nhạy cảm, lưu lượng cao; thêm auth_engineer, "
        "backend_db_engineer, a11y_reviewer, perf_engineer, project_coordinator.",
        f"- đơn web nào cũng ít nhất {WEB_MIN_ROLES} vai: có người thiết kế, người làm, người kiểm, "
        "người giao.",
        "Thêm khóa staffing vào object JSON: {\"size\": \"nho|vua|lon\", \"web\": true|false, "
        "\"backend\": {\"needed\": true|false, \"reason\": \"...\", \"roles\": [\"...\"]}, "
        "\"hired\": [{\"role\": \"...\", \"task\": \"việc cụ thể trong đơn này\", \"reason\": \"...\"}], "
        "\"considered\": [{\"role\": \"...\", \"reason\": \"vì sao không tuyển\"}]}.",
        "Không ghi quyền tool, làn, cổng hay trần: code quyết những thứ đó.",
        "Đơn thiếu đối tượng xem, ngôn ngữ, thiết bị hay nội dung chính thì hỏi trong questions.",
    ]
    return "\n".join(lines)
