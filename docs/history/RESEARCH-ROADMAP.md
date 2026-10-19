# Lộ trình nghiên cứu

## Giới hạn bộ eval hiện tại

Đánh giá ngoài đã chỉ validator trong brief V01. `eval/value/tasks/V01/task.json` gắn `contains` với `must_contain` là `range(n + 1)`. Chuỗi đó chính là đáp án cần có trong `sum_to.py`. Validator khớp chữ đáp án. Phép kiểm độc lập `eval/value/checks/V01.py` mới chạy `sum_to(0)`, `sum_to(1)` và `sum_to(3)`.

Việc cần sửa nằm ở bộ eval: đừng để validator của brief trùng nguyên văn đáp án. Đợt này không sửa `eval/`.
