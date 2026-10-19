# ADR: hint vai thiếu không hủy run

Vai cuối do code chọn (I5). `per_role_hints` chỉ là gợi ý.

Khi brief thiếu một vai, hoặc thiếu cả object, intake điền chuỗi rỗng cho vai đó. Preview in `đã điền thay`. Trace của run ghi một dòng `kind=normalization`.

Sai kiểu thì từ chối: `per_role_hints` không phải object, hoặc giá trị không phải chuỗi. Không điền đè lên giá trị sai kiểu.

Schema còn lỗi thì intake gửi đúng một lần `PHẢN HỒI SCHEMA` để model sửa, trên cùng sổ và cùng trần tiền. Hết lượt đó mà vẫn sai thì dừng.

Ngày: 2026-10-19.
