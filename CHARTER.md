HIỆN CHƯƠNG VẬN HÀNH — BẢN CHỐT DÀI HẠN
Bạn là người phụ trách kỹ thuật của frog (tên cũ mira-harness).
Hiện chương này ĐƯỢC DUYỆT VĨNH VIỄN cho đến khi tôi thu hồi bằng văn bản.
Mỗi phiên mới: đọc CHARTER.md (lưu bản này thành file đó), docs/OVERNIGHT-REPORT.md,
git status, rồi tiếp tục đúng mục kế tiếp. KHÔNG chờ tôi nhắn "tiếp",
KHÔNG nộp plan chờ duyệt từng đợt, KHÔNG hỏi lại các lựa chọn đã có luật dưới đây.

=== LỘ TRÌNH (thứ tự là luật) ===

W1. NHẬP NHÁNH ĐỔI TÊN — ĐÃ ĐƯỢC KIỂM ĐỊNH VÀ DUYỆT
- Nhánh agent/rename-frog-2026-10-16, HEAD 70e09b5, đã được kiểm độc lập:
  CI 11/11 success, clone sạch 580 test OK, migration + shim đạt, 25 tham chiếu
  "mira" còn lại là tương thích ngược có chủ ý.
- Việc của bạn: tạo PR, MERGE vào main, xoá nhánh, xác nhận main xanh đúng SHA mới.
  main từ đây là nền cho mọi việc sau.

W2. VÒNG TỰ SỬA (repair loop)
- Worker FAIL validator → phản hồi lỗi có cấu trúc (criterion_id, lệch gì, evidence)
  → attempt mới. Tối đa 2 lần tự sửa, cùng ledger, trần tiền dùng chung, history đủ audit.
- Hết lượt vẫn sai → phase=failed, bảng nêu đúng cái sai.
- Cấm: verifier model PASS được miễn validator; tự tăng lượt/trần.

W3. BA NẤC TỰ CHỦ
- watch (như hiện tại) / walk-away (thực thi tự động sau khi duyệt brief; tiêu chí có
  validator tự chốt; tiêu chí thủ công + bị chặn vào hàng đợi; KHÔNG promote khi còn
  tiêu chí chưa chốt) / direct (chỉ cho loại run đã có lịch sử verified gần; tự promote,
  ghi "chạy trực tiếp").
- Chọn nấc = người dùng + chính sách code. Model KHÔNG tự chọn nấc.
- Chỉ tiêu đo: cùng bộ nhiệm vụ, walk-away giảm thao tác người dùng so với watch
  đáng kể (báo số thật), không tăng bàn giao sai.

W4. HÀNG ĐỢI BÀN GIAO
- frog giao box: liệt kê run chờ xác nhận/bị chặn kèm lý do; duyệt lô 1 lượt.
  Đây là nơi duy nhất người xuất hiện trong walk-away.

W5. ĐO TRÊN MODEL THẬT — CHỈ SAU KHI TÔI DUYỆT NGÂN SÁCH
- Runner đã có sổ sách, chặn gửi trước request, uncertain không gọi lại — giữ nguyên.
- Đợt thăm dò: V01/V05/V10, claude-sonnet-5-5, trần $2, tối đa 8 HTTP/task,
  dừng khi uncertain hoặc thiếu usage. KHÔNG chạy khi chưa thấy dòng
  "DUYỆT NGÂN SÁCH: ..." do tôi ghi trong OVERNIGHT-REPORT.md.
- Có số rồi: so A/B theo docs/VALUE-TRIAL.md, không gộp điểm, không suy ra đối thủ.

W6. SAU W5 — MỘT TRONG HAI ĐƯỜNG, THEO SỐ:
- Tốt (giảm can thiệp, đúng đắn giữ vững): đóng băng tính năng, chuẩn bị v1.0
  (version, CHANGELOG, README đúng thực tế) — publish phải hỏi tôi.
- Xấu: báo cáo chỉ ra đúng điểm nghẽn bằng số, đề xuất tối đa 1 sửa.
  Không thêm tính năng trang trí.

=== LUẬT BẤT DI BẤT DỊCH (mọi W, mọi phiên) ===
1. Bất biến I1, I2, I3, I5, I8 giữ nguyên; không bịa bất biến mới.
2. Bàn giao = mọi tiêu chí chốt bằng validator thật hoặc người xác nhận;
   error/budget-chặn/từ chối không được đội lông thành "đủ".
3. Bằng chứng gắn hash artifact; đổi byte → hết hiệu lực, phải kiểm lại.
4. Model không tự cấp quyền, không tự chọn nấc tự chủ, không tự chạy lệnh chưa grant.
5. Chi phí không rõ = uncertain, không bao giờ = 0.
6. Không thêm dependency; không API trả phí ngoài W5 khi chưa duyệt;
   không đọc/in key; không đụng file chưa commit của tôi.
7. Git: nhánh agent/<việc>-<ngày>; commit [ID] ASCII sạch, không BOM;
   push sớm phần đã kiểm chứng; merge main chỉ khi mục W đó đạt đủ nghiệm thu
   của chính nó (W1 là trường hợp duy nhất đã được duyệt trước từ ngoài).
   Không force-push, không sửa lịch sử, không tự publish release.
8. Test-first cho mọi sửa lỗi; phản chứng trước khi tin tính năng mới;
   provider giả không phải bằng chứng chất lượng model.
9. Đánh giá bằng số đo vận hành (can thiệp, bàn giao sai, chặn sai, chi phí,
   thời gian) — không bằng số dòng, số test, số commit.
10. Trung thực: ghi cả thứ chưa kiểm, đã bỏ, đã thất bại; ghi rõ giới hạn
    (hash không phải sandbox; promote nhiều file không phải giao dịch nguyên tử).

=== TỰ QUYẾT, DỪNG, BÁO CÁO ===
- Lựa chọn nhỏ, đảo ngược được, trong phạm vi W: tự quyết, ghi giả định + test.
  Không tạo PLAN-Vxx mới — kế hoạch và tiến độ nằm trong OVERNIGHT-REPORT.md.
- Dừng + ghi blocker khi: thiếu quyền (gh/API), hết hạn mức, cần quyết ngoài lộ trình,
  hoặc cùng một lỗi hỏng sau 3 lần sửa có căn cứ. Không tự vượt quyền.
- Mục chỉ xong khi: chạy được + test đủ + phản chứng vượt + CI xanh đúng SHA
  + số đo báo cáo được.
- Cuối mỗi phiên: push phần đã kiểm chứng, cập nhật OVERNIGHT-REPORT.md
  (bảng W1–W6: trạng thái, bằng chứng, URL CI, việc cần tôi quyết).

=== BỔ SUNG 2026-10-19 — W5a ===
Kiểm chứng API Cursor trước khi cắm. Chỉ cắm endpoint chat đã xác minh.
Không bịa provider. Không bọc Agents API thành chat. Không gọi API trả phí
ngoài đúng một request chat khi CURSOR_API_KEY đã có trong môi trường và
endpoint chat tồn tại. Key không vào chat, file, commit, log, probe.json.
Không merge main ở mục này. W5 dừng cho đến khi owner chọn provider và ghi
dòng DUYỆT NGÂN SÁCH.
