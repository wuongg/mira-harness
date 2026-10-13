# Changelog

## Unreleased

- Worker sửa trong staging và chỉ promote sau verifier cùng cổng người.
- Hai người khác tên khi `dual_approval`. `--approve` không thay hai người.
- Verifier chỉ nhận đúng `PASS` hoặc `FAIL`.
- Oracle bật bằng cờ. Tắt thì trace ghi `disabled`.
- Model chưa có giá bị chặn trước request. Có thể khai `--price-in`.
- selftest không cần thư mục `out`. Một nguồn `__version__`.
- Khóa không đi vào argv, log, hay môi trường của shell con.
- Thêm LICENSE MIT, dọn file rác ở gốc, CI chạy Python 3.9 đến 3.12.
