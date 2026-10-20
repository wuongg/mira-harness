# Changelog

## Chưa phát hành

### Added

- Tuyển đội theo đơn: intake **phân tích rồi đề cử** (trong/ngoài danh mục, không trần 4 nghề); mỗi ứng viên **phỏng vấn PASS/FAIL** mới vào sơ đồ. Trần 24 chỉ chống bùng nổ quota. Thiếu khung web thì code bổ sung vai bắt buộc.
- **Failover** model/nhà cung cấp khi lỗi chết/hết hạn mức (429/5xx/402/empty turn/…): thử tối đa 3 chỗ đã có khóa. Tắt bằng `FROG_NO_FAILOVER=1`.
- Provider `9router` (`--provider 9router`, model `cu/...` tự đi 9router). Khóa `NINE_ROUTER_API_KEY`, địa chỉ `NINE_ROUTER_BASE_URL` hoặc `--base-url`, mặc định `http://localhost:20120`.
- Lượt gọi qua 9router ghi sổ `uncertain (subscription quota)`: không $/token, không $0. Trần riêng 40 lượt gói thuê bao mỗi cây run.
- `frog doctor` liệt kê model 9router; `--models` in đủ, `--smoke MODEL` gọi thử một lượt.
- Model id chứa `fable` gắn nhãn `no_zdr` và in cảnh báo khi chọn.
- `frog team` với đơn web tuyển vai từ danh mục 19 vai (`frog/roles.py`) theo cỡ đơn. Intake đề xuất sơ đồ; code nâng cỡ đơn khi câu đơn có form lưu dữ liệu, đăng nhập hay thanh toán, thêm vai bắt buộc, giữ ít nhất 4 vai và một vai kiểm. Sơ đồ có hai phần: đã tuyển và đã cân nhắc không tuyển, kèm quyết định backend. Duyệt brief là duyệt sơ đồ. `--hire` và `--drop` sửa đội trước khi duyệt.
- Vai kiểm trả phán quyết JSON. Một vai kiểm FAIL thì không bàn giao, cả ở làn 0.
- Đi 9router: vai làm dùng `cu/gpt-5.6-sol-high`, vai kiểm dùng `cu/claude-opus-5-thinking-high`.

### Removed

- Cờ `--cursor` của `frog team` và đội "mọi model Cursor là worker".

### Changed

- Phản hồi SSE không kèm usage ghi uncertain thay vì $0. Sự kiện lỗi trong SSE thành lỗi rõ.
- Bỏ biến `FROG_PRICE` dùng chung cho mọi model. Giá vẫn theo `--price-in`, `prices.toml`, `FROG_PRICE_<MODEL>`.
- `frog team` không hỏi cổng ghi khi thiếu `--out`; tách khối ` ```ngôn đường/dẫn ` ra `files/` khi có `--out`; brief in dạng mục; Ctrl+C gợi ý `--resume`; gõ sai lệnh/cờ gợi ý gần nhất.
- `frog doctor` liệt kê nhà cung cấp có khóa; nhắc cổng 20128 khi mặc định 20120 không trả lời.
- Lý do không tuyển vai ngắn, cụ thể theo cỡ đơn; vai luật bảo cân nhắc xếp trước trong phần không tuyển.

## 0.9.0

### Changed

- Menu và mặt mặc định chỉ còn `frog giao`, `frog team`, `frog agent`, `frog keys`, `frog doctor`.
- `frog bench` là công cụ benchmark nội bộ: shadow 320 tác vụ, phiếu gán nhãn, chấm nhãn, thống kê.
- Bộ việc local cũ nằm ở `eval/bench/tasks`. `eval/value` và `eval/adversarial` giữ chỗ.
- shims mira/r0-shadow sẽ bị bỏ trong v1.0.0.

## Unreleased

### Changed

- Package Python là `frog`. Distribution trên PyPI là `frog-harness` vì tên `frog` đã có người chiếm (2026-10-16).
- Lệnh `mira`, `r0` và `r0-shadow` là shim một bậc: in cảnh báo một lần rồi gọi `frog`. Xóa các lệnh này sau 2027-04-16. `r0` không gọi qua `mira`.
- Lần chạy đầu copy `~/.mira/keys.json` hoặc `~/.r0/keys.json` sang `~/.frog/keys.json`, rồi đổi tên bản `keys.json` cũ thành `keys.json.migrated`. Không xóa. `keys.json.migrated` từ `~/.r0` vẫn được nhận.
- Phiên thiếu được copy sang `~/.frog/sessions`. Thư mục phiên cũ được giữ.
- Run nằm ở `.mira/` vẫn được đọc. File mới ghi vào `.frog/`.
- Biến mới là `FROG_*`. `MIRA_*` vẫn được đọc khi tên mới chưa đặt. Tài liệu chỉ ghi `FROG_*`.

- Worker sửa trong staging và chỉ promote sau verifier cùng cổng người.
- Hai người khác tên khi `dual_approval`. `--approve` không thay hai người.
- Verifier chỉ nhận đúng `PASS` hoặc `FAIL`.
- Oracle bật bằng cờ. Tắt thì trace ghi `disabled`.
- Model chưa có giá bị chặn trước request. Có thể khai `--price-in`.
- selftest không cần thư mục `out`. Một nguồn `__version__`.
- Khóa không đi vào argv, log, hay môi trường của shell con.
- Thêm LICENSE MIT, dọn file rác ở gốc, CI chạy Python 3.9 đến 3.12.
