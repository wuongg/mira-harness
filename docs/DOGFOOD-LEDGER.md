# Dogfood ledger — trải nghiệm người dùng lần đầu

Môi trường P1 (2026-10-20): `C:\Users\phamv\Downloads\dogfood-frog-p1`  
Môi trường xác nhận P2: `C:\Users\phamv\Downloads\dogfood-frog-p2`  
venv mới mỗi vòng; `HOME`/`USERPROFILE` tách; repo `mira-install`.

## 1. Vết đã phát hiện

| thời điểm | bước | chuyện gì xảy ra | vì sao ngứa | đề xuất sửa | mức |
| --- | --- | --- | --- | --- | --- |
| 08:58 | Cài `pip install -e .` trong venv | `pip.exe` bị Application Control chặn (~6.5s) | README không nói cách Windows | `python -m pip install -e .` | P0 |
| 08:58 | Gõ `frog` sau cài | PATH trúng `~\.local\bin\frog.cmd` cũ | Không nói activate / `python -m frog` | Quickstart ghi rõ | P0 |
| 08:59 | `frog doctor` | OK ~0.5–1.2s; non-TTY không vào phiên | README hứa «gõ frog vào phiên» | Ghi cần TTY | P1 |
| 09:00 | `frog giao` + ANTHROPIC hỏng | 401 thô, exit 8, 2.7s | Không chỉ cách gỡ | Bọc thông báo khóa | P0 |
| 09:00 | Chỉ OPENAI, `frog giao "…"` | `thiếu key cho intake`, 0.3s | Có OpenAI mà không chạy | Gợi ý `--provider/--model/--intake-model` | P0 |
| 09:01 | `--intake off` trên giao | lặng lẽ thành `--intake-model off` → `model off chưa có giá` | Đổi nghĩa cờ | `allow_abbrev=False` trên subparser | P0 |
| 09:01 | OpenAI chain đủ cờ | phiếu sau **7.1s**; Quickstart như đã xong | Thiếu chuỗi duyệt/chạy | README + «Bước tiếp» có `--approve-brief` | P0 |
| 09:02 | `--run` trước duyệt | `chưa duyệt phiếu` không lệnh | Đoán cờ | In lệnh duyệt | P0 |
| 09:02 | confirm / box accept | vẫn `awaiting_confirmation`; `duyệt lô: 0` | Không thấy đường bàn giao | Còn tồn (vòng đời giao) | P1 |
| 09:03 | `frog agent` + gpt-5.6-sol | JSON `reasoning_effort`, 1.2s | Không hiểu | Thông báo tiếng Việt + gợi ý | P1 |
| 09:03 | `frog giaoo` | dump argparse | Không gợi ý | Did-you-mean | P1 |
| 09:04 | `--change` thiếu positional | `thiếu yêu cầu` | Help mơ hồ | Còn tồn | P2 |
| 09:05 | Kill giữa chừng | Không hướng resume | Còn tồn | P1 |

## 2. Vết đã sửa + bằng chứng chạy lại

### [UX-1] P0 — xác nhận trên `dogfood-frog-p2`

| vết | lệnh thật | kết quả |
| --- | --- | --- |
| cài Windows | `python -m pip install -e .` trong venv mới | exit 0, **10.4s** |
| thiếu Anthropic, có OpenAI | `python -m frog giao "đọc note.txt"` | exit 8, **0.3s**, in đủ gợi ý `--provider openai --model gpt-5.6-sol --intake-model gpt-5.6-sol` |
| `--intake off` không còn đổi model | `… giao --provider openai --model gpt-5.6-sol --intake off "x"` | exit 2, `unrecognized arguments: --intake` (không còn `model off`) |
| phiếu có bước duyệt | `… --intake-model gpt-5.6-sol "…"` | exit 0, **6.4s**, dòng `Bước tiếp: … --approve-brief` |
| `--run` chưa duyệt | `… --run 526b0f2a7d93` | exit 8, **0.3s**, kèm `Duyệt: … --approve-brief` |
| README | Quickstart khớp chuỗi trên | đã cập nhật |

### [UX-2] P1 — xác nhận cục bộ

| vết | bằng chứng |
| --- | --- |
| `giaoo` | `frog: không có lệnh 'giaoo'. Gần nhất: giao.` |
| agent reasoning_effort | in gợi ý `--protocol text` / model khác trước khi in chi tiết |
| dòng nhập dài (phiên trước) | `test_lineedit` 14 OK — rewind theo bề ngang |
| SSE empty turn (phiên trước) | `decode_completion` trong `test_open` |

## 3. Vết còn tồn + lý do

| vết | mức | lý do chưa sửa vòng này |
| --- | --- | --- |
| `giao box --accept` với `awaiting_confirmation` in `duyệt lô: 0` | P1 | Đụng vòng đời bàn giao / xác nhận; tránh lẫn logic cổng vào UX thuần |
| `--change` vẫn cần positional task | P2 | Thẩm mỹ help; không chặn 5 phút nếu đọc lỗi |
| Kill giữa chừng không in resume | P1 | Cần bắt tín hiệu trên mọi cổng vào; để vòng sau |
| Bare `frog giao` với chỉ OpenAI vẫn fail (có hint) | P0 đã thành hint | Không tự đổi model mặc định (tránh đổi hành vi vai) |

Vòng 2 dogfood trên p2: **không phát hiện P0 mới**. Các P1 còn lại ghi ở mục 3. Dừng vòng theo P3 (không còn P0/P1 *mới* bắt buộc cho Quickstart 5 phút nếu làm theo README đã sửa).

## CI

- `bc3f204` — 11/11 xanh: https://github.com/wuongg/mira-harness/actions/runs/39357393019
- `53ccf94` — 10/11 (windows 3.10 flaky `test_doi_artifact_sau_kill` / PermissionError replace checkpoint); retry replace trên Windows.
