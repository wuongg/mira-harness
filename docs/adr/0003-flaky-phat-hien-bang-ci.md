# ADR: phát hiện flaky bằng CI hai lần chạy cùng cây

Ngày 2026-10-19. Cây `d280f65` chạy CI 11/11 xanh, gồm `unittest (windows-latest / 3.12)`. Merge giữ nguyên cây đó thành `517a992`. Lần CI sau của đúng cây này đỏ một job: `unittest (windows-latest / 3.12)`, run https://github.com/wuongg/mira-harness/actions/runs/39236752927. Mười job còn lại xanh. SHA của lần đỏ không đổi nội dung so với lần xanh.

Test đỏ là `test_kill_sau_worker_khong_goi_lai_worker`. Assertion: `next_index` phải >= 1, giá trị đọc được là 0. Vòng đợi cắt ở 15 giây dù tiến trình con còn sống. Checkpoint đầu ghi `next_index` 0 trước khi bước worker xong. Máy Windows chậm hơn mốc đó thì test fail; máy kịp thì test pass. Không phải thứ tự file, không phải dấu phân cách, không phải encoding stdout, không phải seed.

Phản chứng: worker cố tình trả lời sau 16 giây. Vòng 15 giây đọc `next_index` = 0. Sửa: đợi đến khi checkpoint ghi bước worker, hoặc đến khi tiến trình con thoát. Không retry, không skip, không hạ `next_index` >= 1.

Đây là một lần đo trung thực: cùng một cây, hai lần CI, một kết quả khác nhau. Không lấy lần xanh để xóa lần đỏ.
