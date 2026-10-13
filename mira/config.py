"""Hằng số cấu hình R0 shadow.

Mọi ngưỡng ở đây là GIÁ TRỊ KHỞI TẠO từ SPEC v1.0, chưa được kiểm chứng.
R0 shadow chỉ ĐO, không hành động — nên các ngưỡng này không gây hậu quả.
Đánh dấu `TBD-R0` = sẽ được thay bằng số thật sau khi có nhãn người.
"""

SEED = 20261011

# ---------------------------------------------------------------- quy mô mẫu
N_TASKS = 320          # 8 tầng × 40
TASKS_PER_WEEK = 250   # giả định thông lượng để quy đổi giờ audit

# ------------------------------------------------------------------- làn
LANE_NAMES = {0: "làn 0 · 1 agent + checkpoint",
              1: "làn 1 · 1 worker + 1 verifier",
              2: "làn 2 · planner + coordinator + N worker + N verifier + oracle + holdout + critic"}

# --------------------------------------------------- sàn rủi ro theo QUYỀN
# Nâng vì QUYỀN: KHÔNG BAO GIỜ hạ.
RIGHTS_FLOOR = {
    "read_only": 1,
    "write_sandbox": 1,
    "write_external": 2,
    "egress_new": 3,
}

# ---------------------------------------------- sàn rủi ro theo NỘI DUNG
CONTENT_FLOOR = 2      # có nội dung không tin trong ngữ cảnh chính
FLOOR_MAX = 3

# Bốn điều kiện hạ sàn vì NỘI DUNG (cả bốn phải đúng)
NARROW_OUTPUT_TYPES = {"enum", "number", "bool", "id"}   # KHÔNG có free_string
LOWERING_PROBATION = {"required_clean": 200, "step_down": [0.50, 0.25, 0.10]}

# ------------------------------------------------------------ cổng người
# bậc theo từng trục quy mô
GATE_SCALE = {"records": [(10, 1), (1000, 2)],   # <=10 -> b1 ; <=1000 -> b2 ; hơn -> b3
              "dollars": [(50, 1), (1000, 2)]}
GATE_MINUTES = {1: 3.0, 2: 8.0, 3: 25.0}         # phút/người cho mỗi tầng

# ------------------------------------------------------------------ ngân sách
BUDGET = {
    #            trần dùng  | dự phòng kiểm (worker KHÔNG được đụng)
    0: {"cap": 0.99, "reserve": 0.48},
    1: {"cap": 0.85, "reserve": 0.66},
    2: {"cap": 2.46, "reserve": 1.52},
}
SESSION_CAP = 20.0
DAY_CAP = 60.0

# Model không có trong bảng vẫn bị chặn. Hằng số này không phải một bậc giá.
UNKNOWN_PRICE = {"in": 5.00, "out": 15.00, "cache_write": 6.25, "cache_read": 0.50}

# Trần đưa vào prompt. Phần dài hơn thì agent tự đọc lại.
MEMORY_PROMPT_CHARS = 2_000
TOOL_RESULT_CHARS = 8_000

# ---------------------------------------------------------------- giá model
# USD / 1M token. Nạp từ mira/prices.toml. Không giữ dict thứ hai.
def _shipped_prices() -> dict:
    from pathlib import Path
    from .prices import load_prices_file
    return load_prices_file(Path(__file__).with_name("prices.toml"))


PRICES = _shipped_prices()
VENDOR = {"opus-5.5": "anthropic", "sonnet-5.5": "anthropic", "haiku-5.5": "anthropic",
          "gpt-6-astra": "openai", "gpt-6-luna": "openai", "gpt-5.6-sol": "openai",
          "grok-4.7": "xai"}

# Vai -> model.  Ràng buộc độc lập: verifier KHÁC hãng với worker;
# oracle KHÁC hãng với cả worker lẫn verifier.
ROLE_MODEL = {
    "planner":     "opus-5.5",
    "coordinator": "opus-5.5",
    "worker":      "sonnet-5.5",     # anthropic
    "verifier":    "gpt-6-luna",     # openai
    "oracle":      "grok-4.7",       # xai
    "critic":      "gpt-5.6-sol",
    "classifier":  "gpt-6-luna",     # model THẬT, rẻ (trước là "jev-system-one" — không gọi được)
}

# Model phiên `mira` khi có khoá OpenRouter. Đổi trong phiên bằng /model.
OPENROUTER_MODEL = "anthropic/claude-sonnet-4.5"

LANE_MAX = 2   # chỉ có 3 làn. Sàn = 3 KHÔNG tạo làn mới; nó đẩy cổng người
               # lên tầng cao nhất + bắt buộc 2 người duyệt (xem human_gate).

# ---------------------------------------------------------------- đội con
# Đội con KHÔNG được cấp trần mới. Nó chỉ được chia một PHẦN trần CÒN LẠI của cha,
# và sổ cái dùng chung nên trần của cha vẫn là cổng chặn cuối (I8).
#   share     — phần trần còn lại cấp cho MỘT đội con (0,50 = một nửa)
#   max_depth — số cấp lồng tối đa (1 = worker mở đội con, 2 = đội con lại mở tiếp)
#   max_runs  — trần cứng số đội con trong CẢ cây, chặn bùng nổ
SUBAGENT = {"share": 0.50, "max_depth": 3, "max_runs": 12}


# Mô hình dùng lượng token (input, output) theo VAI cho mỗi làn.
# Đây là GIẢ ĐỊNH có thể thay bằng số đo thật; R0 đo hệ quả của giả định này.
USAGE = {
    0: {"worker":   (35_000, 3_000), "verifier": (18_000,   800)},
    1: {"worker":   (55_000, 6_000), "verifier": (25_000, 1_000)},
    2: {"planner":  (15_000, 2_000), "coordinator": (60_000, 8_000),
        "worker":   (45_000, 4_000), "verifier": (25_000, 1_000),
        "oracle":   (30_000, 1_500), "critic": (25_000, 1_500)},
}
USAGE_SCALE_MAX = 2.0     # hệ số phóng theo quy mô tác vụ, trần 2×

# Bộ phân loại T1b: 1 request gộp nhiều câu hỏi. Chi phí tính theo GIÁ THẬT của
# model ở ROLE_MODEL["classifier"] — không có hằng số giá riêng treo lơ lửng.
CLASSIFIER_TOKENS = 1_200

# ---------------------------------------------------------------- cache
CACHE_HIT = 0.90       # giả định SPEC; R0 đo độ nhạy quanh giá trị này

# ---------------------------------------------------------------- D1–D4
D1_WINDOW_FILL = 0.80          # > 80% cửa sổ -> nén
D1_WINDOW_TOKENS = 200_000     # cửa sổ giả định
D2_TOKENS_PER_DELTA = 25_000   # token / mỗi lượt tiến
D3_MAX_TOOL_CALLS = 150
D3_MAX_DEPTH = 3
D4_MIN_CRITERIA_LOCKED = 1     # số tiêu chí tối thiểu phải khoá TRƯỚC khi worker chạy

# ------------------------------------------------- ước lượng vòng trước (đối chiếu)
PRIOR_LANE_COST = {"lane0_short": 0.29, "lane0_deep": 1.11, "lane1": 1.22, "lane2": 6.14}
