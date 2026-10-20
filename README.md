# Frog

Harness giao việc cho đội agent. Bản **0.9.0**.

`mira`, `r0` và `r0-shadow` vẫn gọi được, in cảnh báo, và sẽ bị bỏ trong v1.0.0.

## Quickstart

Cần Python 3.9 trở lên. Không thêm thư viện.

```bash
python -m pip install -e .
python -m frog doctor
```

Trên Windows, nếu `pip.exe` bị chặn thì dùng đúng `python -m pip` như trên. Sau khi cài trong venv, kích hoạt venv rồi gõ `frog`, hoặc luôn dùng `python -m frog …` để không lẫn bản cũ trên PATH.

Cần ít nhất một khóa: `ANTHROPIC_API_KEY` hoặc `OPENAI_API_KEY` (xem `frog keys`). Intake mặc định dùng model Anthropic; chỉ có OpenAI thì phải chỉ model:

```bash
frog keys
frog giao --provider openai --model gpt-5.6-sol --intake-model gpt-5.6-sol "đọc note.txt và tóm tắt một câu"
```

`giao` lần đầu chỉ in phiếu. Chuỗi đã chạy thật:

```bash
frog giao --run <id> --approve-brief
frog giao --run <id> --provider openai --model gpt-5.6-sol
```

Năm lệnh làm việc:

```bash
frog giao "sửa hàm và để lại phép kiểm"
frog team "soạn báo cáo từ file trong thư mục"
frog agent "đọc README và tóm tắt"
frog keys
frog doctor
```

Gõ `frog` không kèm gì để vào phiên (cần terminal tương tác). Chưa có khóa thì `frog menu` hiện đúng năm lệnh trên.

`frog bench` in dòng `công cụ benchmark nội bộ`. Đó là shadow 320 tác vụ, phiếu gán nhãn, chấm nhãn và thống kê. Không nằm trong menu mặc định.

## Kết quả đo lường

Chỉ tiêu chốt là cặp `completed_correct` > 0 và `false_complete` = 0. Cặp này chưa đạt. Chưa đóng băng 1.0.0.

Tổng chi là ước lượng sổ của đợt đó. Đợt có baseline B thì cộng A và B. G3 còn cộng lượt gọi lại lý do.

| Đợt | model | tổng chi | completed_correct | false_complete |
| --- | --- | --- | --- | --- |
| W5 | gpt-5.6-luna | $0.001213 | — | — |
| F3 | gpt-5.6-luna | $0.002601 | — | — |
| D3 | gpt-5.6-luna | $0.019703 | — | — |
| FIX-V | gpt-5.6-luna | $0.022812 | 0 | 0 |
| G3 | gpt-5.6-luna | $0.036389 | 0 | 0 |
| G1b | gpt-5.6-luna | $0.015626 | 2 | 1 |
| X3 | gpt-5.6-luna | $0.011378 | 0 | 0 |
| X4 | gpt-5.6-luna | $0.000286 | 0 | 0 |
| F-2 | gpt-5.6-luna | $0.019379 | 0 | 1 |
| FINAL | gpt-5.6-luna | $0.021082 | 0 | 1 |
| CRIT | gpt-5.6-luna | $0.015603 | 0 | 0 |
| TIER-1 | gpt-5.6-sol + gpt-5.6-luna | $0.038587 | 0 | 0 |
| FINAL-2 | gpt-5.6-sol + gpt-5.6-luna | $0.153721 | 2 | 1 |

Mọi số đo là ước tính sổ cái trên model OpenAI thật từ ngày 2026-10-14, không phải hóa đơn. T-REAL của bộ overnight cũ là `not_evaluated` — xem [docs/history/](docs/history/).
