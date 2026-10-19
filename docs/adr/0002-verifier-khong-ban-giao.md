# ADR: bàn giao chỉ dựa trên verifier là cấm

Ba việc đo được ngày 2026-10-19. Không suy diễn thêm.

## Giữ chỗ ngân sách không atomic

CI ubuntu-latest / 3.9 tại `6c9f5c2` fail `test_luong_thu_hai_khong_goi_khi_het_cho`: hai worker cùng gọi model, `_Slow.calls` là 2. Không phải lỗi annotation hay thứ tự import của Python 3.9. `_call` kiểm trần rồi thả khóa, `begin_request` mới chạy sau đó. Máy chậm để cả hai luồng qua cửa trước khi có chỗ giữ. Test `test_hai_luong_khong_vuot_truoc_khi_giu_cho` ngủ 0.3 giây trong `begin_request` và đòi vẫn chỉ một lần gọi. Sửa: giữ chỗ nằm trong cùng khóa với phép kiểm.

## Đợt G1b

Intake không còn bắt model viết validator. Code gắn validator khi suy được. Runner lưu stdout từng task. Đợt 12 task: `stopped=finished`, 48 HTTP, ước lượng $0.015626, `uncertain_usd` 0. `completed_correct` = 2 (V03, V05). `false_complete` = 1. V09 được promote theo nhãn verifier, file là `BAN NHAP`, phép kiểm đòi `BAN CUOI`. G2 thu hồi: `verifier_delivery` trả false.

## Deliverable thiếu validator không được promote

Walk-away và direct chỉ promote khi mọi tiêu chí kiểm được đã có validator và validator đó pass. Deliverable không có validator thì phase `awaiting_confirmation`, không ghi ra cây nguồn. PASS của verifier không đổi quy tắc này. Phản chứng là brief V09: deliverable là câu chữ, hai tiêu chí không có validator, verifier trả PASS, worker ghi `BAN NHAP`. Run không promote, `label.txt` không xuất hiện ở cây nguồn.

Ngày: 2026-10-19.
