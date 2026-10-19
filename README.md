# Frog

Harness giao việc cho đội agent. Bản **0.9.0**.

`mira`, `r0` và `r0-shadow` vẫn gọi được, in cảnh báo, và sẽ bị bỏ trong v1.0.0.

## Quickstart

Cần Python 3.9 trở lên. Không thêm thư viện.

```bash
pip install -e .
frog doctor
```

Năm lệnh làm việc:

```bash
frog giao "sửa hàm và để lại phép kiểm"
frog team "soạn báo cáo từ file trong thư mục"
frog agent "đọc README và tóm tắt"
frog keys
frog doctor
```

Gõ `frog` không kèm gì để vào phiên. Chưa có khóa thì `frog menu` hiện đúng năm lệnh trên.

`frog bench` in dòng `công cụ benchmark nội bộ`. Đó là shadow 320 tác vụ, phiếu gán nhãn, chấm nhãn và thống kê. Không nằm trong menu mặc định.

## Kết quả đo

Chỉ tiêu chốt là cặp `completed_correct` > 0 và `false_complete` = 0. Cặp này chưa đạt. Chưa đóng băng 1.0.0.

| Đợt | completed_correct | false_complete | Kết |
| --- | --- | --- | --- |
| FINAL | 0 | 1 | V09 bàn giao `BAN NHAP` |
| CRIT | 0 | 0 | mọi task bị chặn |
| TIER-1 | 0 | 0 | dừng sau V05 |
| FINAL-2 | 2 | 1 | V01 và V04 đúng; V09 vẫn bàn giao sai |

Hành trình chi tiết ở [docs/history/](docs/history/).
