# Báo cáo đêm 2026-10-13

## 1. Mốc

- SHA đầu vào: `bb587009da2b4d90edc6eeb0384114e5e83ba797`.
- Nhánh: `agent/overnight-rd-2026-10-13`. Worktree `C:\Users\phamv\Downloads\mira-overnight`.
- SHA cuối cùng đã có CI xanh ở thời điểm viết báo cáo này: `e232212` (Q4).
- Ba file markdown kế hoạch chưa commit ở checkout gốc không được đụng.
- Pull request: chưa tạo. `gh` chưa đăng nhập. Link: https://github.com/wuongg/mira-harness/compare/main...agent/overnight-rd-2026-10-13?expand=1

## 2. Hàng đợi

| Mục | Trạng thái | SHA | CI |
| --- | --- | --- | --- |
| Q1 | đạt | `5dc8b76` | https://github.com/wuongg/mira-harness/actions/runs/38430189312 success |
| Q2 | đạt | `21e7dd6` | https://github.com/wuongg/mira-harness/actions/runs/38430530807 success |
| Q3 | đạt | `6b8eb79` | https://github.com/wuongg/mira-harness/actions/runs/38430813856 success |
| Q4 | đạt | `e232212` | https://github.com/wuongg/mira-harness/actions/runs/38431738409 success, 11 job |
| Q5 | đạt | `8dd0118` | https://github.com/wuongg/mira-harness/actions/runs/38432585723 success |
| Q6 | đạt | `935c57d` | https://github.com/wuongg/mira-harness/actions/runs/38433405697 success |
| Q7 | đạt trên máy, CI của commit này là lần chạy sau khi push | commit này | chưa có URL lúc viết |
| Q8 | chưa làm | | |

Q2 có thêm một run success trùng SHA: https://github.com/wuongg/mira-harness/actions/runs/38430528319

## 3. Q1 — bằng chứng

Trước: tiêu chí `proven` nếu câu nằm trong `evidence` của verifier, hoặc mọi file có đuôi được nêu đều nằm trong diff staging. Đó là bản `c8461bb`.

Sau: chỉ lệnh bắt đầu bằng `check:` do harness tự chạy (`shell=False`, env đã bỏ key, timeout 30s, cwd là staging nếu có) và thoát 0 mới là `proven`. Thoát khác 0 là `failed`. Không có lệnh, lệnh rỗng, hết giờ hoặc không chạy được là `unproven`. `failed` cũng chặn giao. Cổng chỉ chạy khi `--require-evidence` và brief có tiêu chí.

Lệnh: `py -3 -m unittest discover -s tests -p "test_obligations.py" -v`

Selftest trước commit Q1: `Ran 441 tests`, `OK (skipped=2)`.

## 4. Q2 — hợp đồng

`contract_diff` so goal, deliverables, acceptance_criteria, constraints. Resume có brief mới mà hash khác checkpoint thì thoát 2, câu `yêu cầu đã đổi — không tiếp tục kế hoạch cũ`, không gọi model, không ghi đè brief cũ. Đổi mỗi câu hỏi cũng bị chặn vì hash. Checkpoint giữ `contract.version`, `hash`, `parent`.

Lệnh: `py -3 -m unittest discover -s tests -p "test_contract.py" -v`

Selftest trước commit Q2: `Ran 444 tests`, `OK (skipped=2)`.

## 5. Q3 — cờ sống qua resume

`require_evidence` nằm trong checkpoint. Resume không truyền cờ không tắt cổng đã bật. Checkpoint cũ thiếu khóa được đọc là tắt. Brief thiếu thì không crash, cổng không chạy.

Lệnh đi qua `cmd_team`: `py -3 -m unittest discover -s tests -p "test_resume_policy.py" -v`

Selftest trước commit Q3: `Ran 447 tests`, `OK (skipped=2)`.

## 6. Q4 — luồng

`tests/test_flow.py`, provider giả, không mạng:

- Intake trả brief, rồi `cmd_team` với `--brief` và `--require-evidence`: check thoát 0 thì in `proven:` và ghi `out`.
- Cắt sau worker rồi resume: chỉ gọi verifier, không gọi lại worker.
- Brief đổi deliverable: thoát 2, brief trong checkpoint giữ nguyên, không gọi provider.
- Provider ném lỗi: thoát 3, không có câu đã ghi executor, checkpoint `status=error`, `total_usd=0`.

`--brief` khi intake tắt vẫn được nạp. Trước Q4, brief chỉ được đọc khi intake bật.

Entry point và resource package không đổi, nên không cài từ artifact.

Selftest trước commit Q4: `Ran 451 tests`, `OK (skipped=2)`.

## 7. Q5 — tập đánh giá tách

29 tình huống trong `eval/overnight/scenarios.jsonl`. Hash đóng băng `4f0423d7d76741f587b3ea18a089cdbab2bde0a161b87208bb91344ce79db6e5` trong `scenarios.sha256`. Runner từ chối chấm nếu hash lệch.

Baseline là hàm bằng chứng chép từ `git show c8461bb:mira/obligations.py`, không phải process của cây cũ. Cùng file đáp án.

Lệnh: `py -3 tools/overnight_eval.py`

Kết quả: `scenarios 29`, `baseline_false_deliver 4`, `baseline_false_block 4`, `current_mismatch 0`.

Bàn giao sai của baseline (coi là proven dù đáp án không phải proven): E01 chép câu, E02 file đổi đúng tên, E11 câu nằm trong trích dẫn dài hơn, E15 file `report.md` sau khi cắt khoảng trắng.

Chặn sai của baseline (không proven dù check thoát 0): E03, E09, E13, E14.

Giới hạn còn lại, không phải mismatch của bản hiện tại:

- C07 câu hỏi và C08 giả định không làm `contract_diff` invalidates, nhưng hash khác nên resume vẫn thoát 2.
- C09 khoảng trắng: diff sau khi cắt không hủy, hash thô vẫn khác.
- E16 đường dẫn `C:\...` không được quote: `shlex` posix nuốt `\`, check thành `unproven`. Lệnh phải được quote kiểu `shlex.join`.
- R02/R03 dùng provider giả. Không phải điểm model thật.

Selftest cùng lúc: `Ran 451 tests`, `OK (skipped=2)`. Mira không đổi ở Q5 nên số test không tăng.

## 7b. Q6 — kiểm vận hành

Đã chạy lại `test_retry.py` (4) và `test_key_leak.py` (6). Retry 429 rồi 200 chỉ charge một lần. 400 không thử lại. 503 đủ 3 lần thì không charge.

Checkpoint: file `.json.tmp` đứt không đè bản đã `os.replace`. JSON cụt làm `resume_team` thoát 2, câu `checkpoint hỏng`, không traceback.

Trần: hai đội con, giá $1/lần, trần $3. Trước sửa, planner và hai đội con làm đầy $3 rồi hai verifier cha vẫn chạy, tổng $5. Sửa: hết trần (`>=`) thì không mở pha sau. Sau sửa tổng `<= 3` và không có verifier cha. Lệnh trong cùng pha song song vẫn có thể cùng vượt nếu trần chưa đầy lúc pha đó bắt đầu. Chưa sửa chỗ đó vì không biết giá của lần gọi trước khi model trả về, và khóa cả lần gọi sẽ bỏ song song.

Khóa `sk-test-EXPOSE-0123456789` không có trong dict kết quả và không có trong `checkpoint.json`. Process con vẫn theo test key-leak đã có.

Selftest: `Ran 455 tests`, `OK (skipped=2)`.

## 7c. Q7 — lệnh trong tài liệu

Đã chạy `py -3 -m mira team "soan bao cao tong ket quy" --dry-run`. Thoát 0, in kế hoạch, không gọi model.

Hai lệnh chạy thật trong README được chạy lại sau khi xóa `*_API_KEY` khỏi môi trường, thêm `--intake off` để không hỏi stdin. Cả hai thoát 3. Dòng trạng thái là `bị chặn`. Dòng lý do là `thiếu key cho anthropic — đặt ANTHROPIC_API_KEY`. Không chỉ có chữ withheld.

Tiêu chí trên CLI: `đã kiểm`, `chưa kiểm` (kèm “Thêm tiền tố check: rồi chạy lại.”), `bị chặn` (kèm “Sửa cho lệnh thoát 0 rồi chạy lại.”). Trạng thái giao được là `đã làm`.

Selftest: `Ran 456 tests`, `OK (skipped=2)`.

## 8. Phương án đã loại

- Critic thêm một lần gọi model: không có ngân sách API.
- Chạy nhiều phương án sandbox rồi chấm bằng provider giả: không có thước độc lập.
- Để lời model thành luật: đã loại từ đầu phiên.
- Coi trích dẫn hoặc file đổi là proof: đã bỏ ở Q1 vì chính là bàn giao sai trong Q5.
- Sửa đáp án Q5 sau khi runner đỏ: lần đỏ đầu là lệnh check chưa quote và checkpoint resume thiếu field log. Sửa runner, không sửa dòng đáp án cũ. E16 được thêm rồi hash lại trước lần chấm cuối.

## 9. Chưa đủ bằng chứng

- Chưa chạy model trả phí. Số 4 và 4 là đếm fixture, không phải chất lượng model.
- Chưa so Mira với Codex, Aider, Claude Code trên cùng nhiệm vụ.
- Baseline Q5 không được chạy bằng checkout `c8461bb` riêng. Hàm được chép từ blob đó.
- Ngắt giữa chừng ở Q4 là ghi lại snapshot `next_index == 1`, không phải kill process.
- `--require-evidence` vẫn tắt mặc định.

## 10. Cần quyết định

- Đăng nhập `gh` để mở PR. Không merge, không push `main`.
- Có bật `--require-evidence` mặc định khi đã có brief hay không.
- Ngân sách API nếu muốn đo trên model thật.
