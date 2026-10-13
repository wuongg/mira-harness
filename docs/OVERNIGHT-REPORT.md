# Báo cáo đêm 2026-10-13

## 1. Mốc

- SHA đầu vào local: `bb587009da2b4d90edc6eeb0384114e5e83ba797` trên `main`, ahead origin 4 commit. Origin lúc bắt đầu là `4a30cfd`.
- Nhánh làm việc: `agent/overnight-rd-2026-10-13`. Worktree `C:\Users\phamv\Downloads\mira-overnight`. Ba file markdown kế hoạch chưa commit ở checkout gốc được để nguyên, không đưa vào commit.
- SHA mã đã kiểm CI: `c8461bb8a27f2ec9ca1c423fc91c7f999a8ae3b2`.
- CI SHA đó: https://github.com/wuongg/mira-harness/actions/runs/38427243145 — `conclusion: success`. 11 job của workflow: 8 unittest (ubuntu và windows, Python 3.9–3.12), shadow, quality-gate, commit-lint. Không có job đỏ.
- Commit báo cáo này nằm sau SHA trên. CI của commit báo cáo là lần chạy kế tiếp trên cùng nhánh.
- Pull request: chưa tạo được. `gh auth status` báo chưa đăng nhập. Không lấy credential để gọi API. Link mở PR: https://github.com/wuongg/mira-harness/compare/main...agent/overnight-rd-2026-10-13?expand=1

## 2. Trạng thái

- Nền Windows CI: hoàn thành từ trước phiên này. Run `4a30cfd` đã success (https://github.com/wuongg/mira-harness/actions/runs/38422866084). Không sửa lại bản vá path 8.3.
- Bốn commit P3 chưa có trên origin/main được đẩy trong nhánh này, không push `main`.
- Hợp đồng brief và sổ tiêu chí: hoàn thành trên provider giả.
- PR: bị chặn vì `gh` chưa đăng nhập.

## 3. Vấn đề đã chọn

Người dùng đổi ý giữa chừng, và đội vẫn có thể báo xong khi verifier chỉ nói PASS.

Mira trước thay đổi: brief đã có schema (`mira/intake.py`, khóa `acceptance_criteria` và `constraints`). Resume đọc checkpoint và chạy tiếp. Trạng thái `ok` khi verifier PASS và các cổng diff/lệnh đã có. Brief không bị so với lần chạy trước. PASS với `evidence: []` vẫn giao nếu không có brief, và cả khi có brief.

Nguồn đã đọc:

- OpenAI Codex, plan mode và goal: https://developers.openai.com/codex/learn/best-practices và https://developers.openai.com/cookbook/examples/codex/using_goals_in_codex — tài liệu nói completion phải đối chiếu evidence, không phải niềm tin của model. Đây là hướng thiết kế, chưa đo Codex trên cùng nhiệm vụ với Mira.
- Aider, architect và ask: https://aider.chat/docs/usage/modes.html — architect đề xuất rồi editor sửa file. Tài liệu không mô tả sổ nghĩa vụ từng tiêu chí. Chưa đối chiếu hành vi thật.
- Claude Code plan mode: các bài thứ cấp (không phải trang docs.anthropic.com mình đã mở) mô tả plan mode đọc code và không sửa file cho đến khi người duyệt. Không kết luận Anthropic không có sổ bằng chứng.

Khoảng trống làm được trong Mira mà không gọi API trả phí: so hai brief bằng code, và chỉ giao khi từng tiêu chí có trích dẫn hoặc file nêu trong tiêu chí thực sự đổi.

## 4. Ý tưởng đã loại

- Critic thích ứng: Mira đã có verifier và oracle. Thêm call sẽ tốn ngân sách model. Phiên này không được gọi API trả phí, nên không đo được chất lượng critic.
- Thử vài phương án trong sandbox: nhân số lần chạy, không có thước chất lượng độc lập khi provider là giả.
- Bài học thất bại thành chính sách: lời model không được thành luật. Repo đã có case đối kháng cố định. Không thêm vòng học trong đêm.
- Hai ý trên và critic đều thất bại phép thử “chứng minh bằng provider giả mà không đổi ngân sách hoặc không bịa điểm chất lượng”.

## 5. Cách dùng

Hợp đồng. Brief là JSON đúng schema intake. `mira team --resume <id> --brief <file>` từ chối, thoát 2, câu `yêu cầu đã đổi — không tiếp tục kế hoạch cũ`, khi goal, tiêu chí hoặc constraints đổi. Không gọi model. Cùng nội dung thì không hủy.

Sổ tiêu chí, tắt mặc định để lần chạy cũ không đổi nghĩa. Bật bằng `mira team --require-evidence` khi đã có brief. Mỗi tiêu chí:

- `proven` nếu `verdict_parsed.evidence` chứa đúng câu tiêu chí, hoặc mọi file có đuôi được nêu trong tiêu chí nằm trong `staging_evidence.changed`.
- `unproven` thì trạng thái thành `withheld`, lý do `còn tiêu chí chưa có bằng chứng`.

`result.md` có mục tiêu chí khi sổ được tính. Làn, nhãn và cổng người không đọc từ brief.

Ví dụ đo, provider giả, không mạng:

```
py -3 -m unittest discover -s tests -p "test_contract.py" -v
py -3 -m unittest discover -s tests -p "test_obligations.py" -v
```

## 6. So sánh

Cùng plan làn 1, cùng provider giả, cùng giá khai báo, không brief: verifier PASS, `evidence` rỗng, trạng thái `ok`.

Cùng plan, có brief một tiêu chí, `--require-evidence` (trong test là `plan.require_evidence = True`), verifier không trích tiêu chí và không có file đổi: trạng thái `withheld`, tiêu chí `unproven`.

Cùng cờ, file `app.py` trong tiêu chí được ghi khác trong staging: tiêu chí `proven`, trạng thái `ok`.

Resume với brief đổi tiêu chí: 0 lần gọi provider.

Giới hạn phép đo: đây là đếm trạng thái trên fixture, không phải điểm chất lượng model thật. Chi phí model của hai nhánh bằng nhau vì cổng chạy sau khi đội đã gọi. Không có số liệu can thiệp của người dùng thật.

## 7. Kiểm tra

- Selftest worktree, `py -3` (máy này không có `python3`): `Ran 438 tests`, `OK (skipped=2)`, thoát 0, trước commit `c8461bb`.
- CI `c8461bb`: URL ở mục 1, success, gồm bốn ô Windows.

## 8. Phản biện còn mở

- Khớp tiêu chí bằng chuỗi con. Tiêu chí ngắn có thể nằm tình cờ trong một trích dẫn khác.
- Constraints chỉ làm hỏng kế hoạch cũ khi đổi văn bản. Không có kiểm “việc làm có vi phạm ràng buộc không”.
- Cổng bằng chứng tắt mặc định. Người không truyền cờ vẫn nhận PASS như trước.
- File được nêu nhưng diff chỉ cần file đó khác byte. Không đọc nội dung có đúng yêu cầu hay không.

## 9. Chưa đủ bằng chứng để gọi là tốt hơn

Chưa chạy model thật. Chưa so Mira với Codex, Aider hay Claude Code trên cùng bộ nhiệm vụ. Chưa đo số lần người dùng phải sửa kết quả. Điểm quality-gate đối kháng không phải thước của hai tính năng này.

## 10. Cần quyết định

- Đăng nhập `gh` rồi tạo PR từ nhánh `agent/overnight-rd-2026-10-13` vào `main`, hoặc bảo mình tạo khi đã có token.
- Có bật `--require-evidence` mặc định cho lần chạy có brief hay không. Mặc định hiện tắt vì bật sẽ đổi các test intake đang chờ thoát 0.
- Ngân sách API nếu muốn đo hai tính năng trên model thật.
