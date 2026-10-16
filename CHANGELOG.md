# Changelog

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
