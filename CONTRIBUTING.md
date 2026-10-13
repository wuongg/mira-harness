# Cách đóng góp

Mẫu tiêu đề: `[ID] động từ nguyên mẫu và tân ngữ`.
Ví dụ đúng: `[S4] Reject commit subjects that hide a BOM`.
Ví dụ sai: `Add the lint` (không có ID).
Ví dụ sai: `Sửa cổng giá và đổi tên gói` (có dấu, không có ID).

Năm luật:

1. Một tên `mira` cho package, lệnh, `~/.mira/` và `.mira/`. `r0` và `r0-shadow` chỉ là vỏ có cảnh báo, gỡ sau phiên bản kế tiếp.
2. Định danh code bằng tiếng Anh, PEP 8. Hằng số `UPPER_SNAKE`. Cờ CLI `--kebab-case`. Shape là `"edit"`, `"run"`, `"read"`, `"ask"`.
3. Tên file và thư mục là `lower_snake` hoặc kebab, ASCII, không khoảng trắng, không dấu ngoặc. Không commit `out/`, `.mira/`, `*.withheld/`.
4. Tiêu đề commit không quá 72 ký tự ASCII, không BOM, không zero-width. Một commit một mục. Không viết lại lịch sử đã public.
5. Không đổi tên trong lúc sửa logic khác. Commit đổi tên chỉ chứa rename.

Ghi tiêu đề bằng Python `Path.write_text(..., encoding="utf-8")` rồi `git commit -F`. Không dùng `Set-Content -Encoding utf8` vì lệnh đó ghi BOM.
