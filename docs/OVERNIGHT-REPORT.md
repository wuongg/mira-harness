# Báo cáo đêm 2026-10-13

## 0. Vòng kiểm chứng — kế hoạch ngắn

Nhánh `agent/trust-limits-2026-10-14`, tách từ `7f732a9`, không tách từ `main` cục bộ `bb58700`. Không merge vào `main`.

Câu cũ nói `mira/obligations.py` không có trên `main` là lỗi thời. `origin/main` hiện tại là `81dbbcd` (merge PR overnight) và đã có `mira/obligations.py` với `judge_obligations`.

Link so sánh cũ của nhánh overnight không còn là nhánh làm việc: https://github.com/wuongg/mira-harness/compare/main...agent/overnight-rd-2026-10-13?expand=1

Link nhánh này: https://github.com/wuongg/mira-harness/compare/main...agent/trust-limits-2026-10-14?expand=1

`gh` vẫn chưa đăng nhập, nên chưa mở pull request.

Thứ tự: R1 quyền chạy check, R2 tiêu chí gắn phép kiểm và artifact, R3 đặt trước ngân sách song song, R4 phục hồi bằng tiến trình thật, R5 đo giá trị đầu-cuối trên tập tách khỏi fixture sửa code. Không thêm agent.

| Mục | Trạng thái | SHA | CI |
| --- | --- | --- | --- |
| R1 | đạt | `9dfe1c8` | https://github.com/wuongg/mira-harness/actions/runs/38488932153 success |
| R2 | đạt | `296e187` | https://github.com/wuongg/mira-harness/actions/runs/38489405825 success |
| R3 | đạt | `74b7154` | https://github.com/wuongg/mira-harness/actions/runs/38489760877 success |
| R4 | đạt | `8780d42` | https://github.com/wuongg/mira-harness/actions/runs/38490734366 success |
| R5 | đạt | `863c27b` | https://github.com/wuongg/mira-harness/actions/runs/38491474015 success |
| S1 | đạt | `cb37bb0` | https://github.com/wuongg/mira-harness/actions/runs/38508067848 success |
| S2 | đạt | `61300af` | https://github.com/wuongg/mira-harness/actions/runs/38508501239 success |
| S3 | đạt | `92ef473` | https://github.com/wuongg/mira-harness/actions/runs/38509001523 success |
| S4 | đạt | `e965c49` | https://github.com/wuongg/mira-harness/actions/runs/38509232763 success |
| V1 | đạt | `f1e9537` | https://github.com/wuongg/mira-harness/actions/runs/38509821752 success |
| V2 | CI đỏ một job Windows | `cbc4f7f` | https://github.com/wuongg/mira-harness/actions/runs/38510168826 failure |
| UX | đạt | `4f6ec72` | https://github.com/wuongg/mira-harness/actions/runs/38510764742 success |
| H1 | đạt | `b4bbd75` | https://github.com/wuongg/mira-harness/actions/runs/38511813897 success |
| H2 | đạt | `f0b3db1` | https://github.com/wuongg/mira-harness/actions/runs/38512453126 success |
| H3 | đạt trên máy; CI sau khi push | | |

### R1

`check:` không còn gọi `subprocess.run` riêng. Lệnh chỉ chạy khi `criteria_origin` là `user` (file `--brief` do người đưa) và đi qua `Session.run_shell`: xin phép, chặn path ngoài gốc, env đã bỏ key, timeout 30s, đầu ra cắt 8000 ký tự. Brief do intake/model tạo ra để trạng thái `pending` và không gọi subprocess. Duyệt câu brief trên màn hình không phải cấp quyền shell. Bản sao của `run_shell` không phải sandbox.

Lệnh: `py -3 -m unittest discover -s tests -p "test_check_grant.py" -v`

Selftest: `Ran 462 tests`, `OK (skipped=2)`.

Tập đóng băng `tools/overnight_eval.py` lệch 1 dòng, không sửa đáp án: E13 có đường dẫn tuyệt đối của Python nằm ở đối số, `run_shell` chặn trước khi chạy, trạng thái `blocked` thay vì `proven`. Marker vẫn không được tạo.

### R2

Mỗi tiêu chí có `criterion_id` (id khai báo, hoặc 16 ký tự sha256 của câu). Phép kiểm ghi `criterion_id`, `kind`, `proves`, `check_passed` và `criterion_verified` riêng. `check:` thoát 0 chỉ là `checked`. Xác minh khi `proves` đúng bằng câu tiêu chí và artifact có hash khớp, `run_id` đúng, file còn trong gốc. File thiếu, hash lệch, hoặc run khác thì không nhận. Tiêu chí không có lệnh là `needs_confirmation`.

Không coi file đổi là xác minh. Không đọc nghĩa của file: nếu người dùng khai `proves` trùng câu tiêu chí trong khi nội dung file sai, harness không phát hiện. Đó là giới hạn.

Lệnh: `py -3 -m unittest discover -s tests -p "test_criterion_bind.py" -v`

Selftest: `Ran 469 tests`, `OK (skipped=2)`.

Tập đóng băng vẫn không sửa. Các dòng kỳ vọng `proven` cho lệnh thoát 0 sẽ lệch vì trạng thái mới là `checked`.

### R3

Trước mỗi lần gọi model, sổ cái giữ chỗ `estimate_hold`: đầu vào khoảng 4 ký tự một token, đầu ra bằng `max_tokens`. Đây là trần, không phải tokenizer của hãng và không phải hóa đơn. `committed` gồm tiền đã chi, chỗ đang giữ và khoản không chắc. Không đủ chỗ thì không gọi, trạng thái `stopped_budget`. Sau gọi thành công thì trả chỗ và ghi usage thật. `ProviderError` sau khi request đã gửi thì cộng khoản không chắc, không coi là 0 đồng. Chỗ giữ về 0 khi xong.

Lệnh: `py -3 -m unittest discover -s tests -p "test_budget_hold.py" -v`

Selftest: `Ran 471 tests`, `OK (skipped=2)`.

### R4

Năm lần thử đều khởi chạy `mira team` trong subprocess và ngắt bằng `TerminateProcess`. Provider là HTTP giả trên `127.0.0.1`, không gọi API trả phí.

Sau worker, checkpoint đã có `next_index` từ 1. Resume không tăng số lần gọi worker và sổ cái còn một dòng worker. Lúc ghi checkpoint, tiến trình dừng sau file `.json.tmp` và trước `os.replace` khi `MIRA_PAUSE=checkpoint`. Kill thì không còn `checkpoint.json`. Resume thoát 2, không gọi thêm worker, không bàn giao. Trước bàn giao, `MIRA_PAUSE=handoff` dừng trước `_executor_write`. Resume đi vào `_deliver`, ghi một `result.md`, không gọi lại worker. Đổi brief thì thoát 2 và không ghi đè brief đã lưu. Đổi một byte trong staging đã có `staging_hash` thì thoát 2 với `artifact đã đổi` và không bàn giao.

`MIRA_PAUSE` chỉ ngủ khi biến đó được đặt. Mặc định không chờ. Điểm dừng này để giết tiến trình thật, không thay cho snapshot trong cùng process.

Khoản đang giữ trong lúc gọi model không nằm trên đĩa. Ngắt giữa call thì mất chỗ giữ và không ghi khoản không chắc. Chưa chứng minh phục hồi khoản đó.

Lệnh: `py -3 -m unittest discover -s tests -p "test_crash_resume.py" -v`

Selftest: `Ran 476 tests`, `OK (skipped=2)`.

### R5

Tập `eval/trust/tasks.jsonl`, không dùng fixture của test sửa mã và không dùng `eval/overnight`. Worktree so sánh `C:\Users\phamv\Downloads\mira-baseline` tại `7f732a9`. Provider HTTP cục bộ. Con số này không phải hiệu quả của model thật.

| id | việc đo | cây hiện tại | `7f732a9` |
| --- | --- | --- | --- |
| T-NOOP | bàn giao sai khi lệnh chỉ thoát 0 | không bàn giao, mã 3 | bàn giao, mã 0 |
| T-OPEN | chặn sai khi không có tiêu chí | có bàn giao, mã 0 | có bàn giao, mã 0 |
| T-MODEL | chạy check do model đề xuất | `chờ cấp quyền`, không chạy | chạy lệnh, thoát 2 |
| T-CAP | vượt trần khi hai worker | 1 worker, $2.00, trần $2.46 | 2 worker, $3.00, trần $2.46 |
| T-KILL | gọi lại worker sau resume của run đã xong | 1 rồi 1 | 1 rồi 1 |
| T-WRONG | file sai nhưng `proves` trùng câu | vẫn `verified` | cây gốc không có khóa artifact |

T-KILL resume một run đã chạy xong. Điểm ngắt tiến trình nằm ở R4, không nằm ở dòng này.

Ước lượng giữ chỗ vẫn là 4 ký tự một token và `max_tokens`, không phải tokenizer của hãng. T-WRONG là giới hạn còn lại: harness không đọc nghĩa của file.

Tập đóng băng `eval/overnight` không được sửa. E13 vẫn lệch vì đường dẫn tuyệt đối bị chặn. Các dòng kỳ vọng `proven` cho lệnh thoát 0 lệch vì trạng thái hiện là `checked`.

Lệnh: `py -3 tools/trust_eval.py --current-only` và `py -3 tools/trust_eval.py --baseline C:\Users\phamv\Downloads\mira-baseline`

Selftest: `Ran 477 tests`, `OK (skipped=2)`.

Commit ghi URL này là `763d3b3`. CI: https://github.com/wuongg/mira-harness/actions/runs/38491621204 success.

### S1

Tiêu chí object dùng schema `1`, khóa `id`, `text`, và tùy chọn `cmd`, `proves`, `artifact`. Chuỗi cũ vẫn là schema 0. `validate_criteria` là luật chung của intake, đọc brief, obligations. `contract_diff` giữ nguyên object, không rút thành chuỗi rồi bỏ. Chưa có liên kết tiêu chí sang từng bước, nên đổi tiêu chí hủy cả run (`scope` = `run`). ID trống hoặc trùng thì brief bị từ chối trước khi chạy.

Ví dụ nạp từ CLI, `--intake off --brief` file này, `--require-evidence`. Lệnh đi tới bước kiểm và ghi `criterion_id` `crit-exit` trong `out/withheld.json`:

```json
{"schema":1,"id":"crit-exit","text":"lenh thoat 0 la buoc kiem","cmd":"python -c \"raise SystemExit(0)\"","proves":"","artifact":""}
```

Lệnh: `py -3 -m unittest discover -s tests -p "test_criteria_schema.py" -v`

Selftest: `Ran 483 tests`, `OK (skipped=2)`.

### S2

`command_passed` là mã thoát. `artifact_integrity` là hash đúng run. `criterion_verified` chỉ khi validator chạy đúng. Câu `proves` trùng tiêu chí được giữ ở `claim`, không biến thành bằng chứng.

Validator schema 1: `contains` (chuỗi bắt buộc/cấm), `json_keys` (JSON và khóa), `shape` (đuôi file), `behavior` (lệnh đã cấp quyền, đúng mã thoát và một chuỗi đầu ra). Mỗi dòng ghi `proves` và `does_not_prove`. Không có validator thì `needs_confirmation` hoặc `unverified`.

T-WRONG: file `return 4`, claim trùng câu, hash khớp. Kết quả `unverified`, không còn `verified`.

Lệnh: `py -3 -m unittest discover -s tests -p "test_validators.py" -v`

Selftest: `Ran 490 tests`, `OK (skipped=2)`.

### S3

Mỗi request có `id` và trạng thái `reserved`, `dispatched`, `settled` hoặc `uncertain`. Checkpoint ghi `dispatched` trước `prov.call`. Kill giữa call rồi resume vẫn thấy request đó ở `uncertain` và `uncertain_usd`; không xóa và không coi là chưa gửi. Usage thật lớn hơn ước lượng thì vẫn ghi đủ và đặt `exceeded`.

Ước lượng là heuristic 4 ký tự/token và `max_tokens`. Không phải tokenizer và không phải trần trên. Trần làn không được tuyên bố là tuyệt đối khi usage vượt ước lượng.

Cùng `tracked_call` cho `_call`, intake, prompt writer, và worker sửa file qua `_priced_call`. Đội con đi qua `_call`. Đường stream của chat không ghi request này.

Lệnh: `py -3 -m unittest discover -s tests -p "test_request_ledger.py" -v`

Selftest: `Ran 495 tests`, `OK (skipped=2)`.

### S4

`tools/trust_eval.py` ghi mỗi dòng là `pass`, `fail` hoặc `not_evaluated`. `remaining` không còn được tính là đạt. `T-REAL` là `not_evaluated`: không có API trả phí được duyệt, nên không có số liệu model thật.

Không thêm file resource. Schema nằm trong `mira/obligations.py`, đã là module của package.

| id | kết quả |
| --- | --- |
| T-NOOP | pass, không bàn giao |
| T-OPEN | pass, có bàn giao |
| T-MODEL | pass, không chạy lệnh của model |
| T-CAP | pass, 1 worker, $2.00, trần $2.46 |
| T-KILL | pass, resume run đã xong không gọi lại worker |
| T-WRONG | pass, không verified |
| T-OBJECT | pass, brief object tới bước kiểm |
| T-DUP | pass, id trùng bị từ chối |
| T-ARTIFACT | pass, file `return 4` không verified |
| T-CHANGE | pass, đổi object thì không tiếp tục |
| T-INTERRUPT | pass, kill giữa request còn khoản uncertain |
| T-REAL | not_evaluated |

Lệnh: `py -3 tools/trust_eval.py --current-only`

Selftest: `Ran 495 tests`, `OK (skipped=2)`.

### V1

`json_keys` với `expect: array` áp `required` và `forbidden` cho từng phần tử. Phần tử không phải object thì thất bại. Mảng rỗng thất bại, trừ khi người dùng đặt `allow_empty: true`. `[{}]` với `required: ["invoice_id"]` không còn `verified`.

Lệnh: `py -3 -m unittest discover -s tests -p "test_validators.py" -k array`

Selftest: `Ran 502 tests`, `OK (skipped=2)`.

### V2

`behavior` chỉ so `expects_stdout` với stdout thật. Chuỗi nằm ở stderr, ở dòng `[mã thoát 0]`, hoặc ở câu hiển thị của harness không làm check đạt. `run_shell` vẫn trả chuỗi hiển thị cũ. `run_shell_result` trả `exit_code`, `stdout`, `stderr`, `timed_out`, `truncated` và trạng thái quyền. Timeout hoặc output bị cắt mà không thấy chuỗi đã khai thì trạng thái là `unverified`.

Lệnh: `py -3 -m unittest discover -s tests -p "test_validators.py"`

Selftest: `Ran 508 tests`, `OK (skipped=2)`.

CI `cbc4f7f`: https://github.com/wuongg/mira-harness/actions/runs/38510168826 failure. Job `unittest (windows-latest / 3.12)` lỗi `PermissionError` khi đọc `checkpoint.json` trong `test_doi_artifact_sau_kill_khong_ban_giao`. Vòng chờ của test đó giờ thử lại khi file đang bị khóa, cùng cách nó đã thử lại khi JSON còn dở. Các job unittest còn lại và quality-gate đều success.

### UX

Lệnh `mira giao` nhận câu nói thường, gọi intake sẵn có, rồi in mục tiêu, deliverable, ràng buộc và từng tiêu chí là tự động hay cần người xác nhận. Dòng lệnh cần cấp quyền được in riêng. Duyệt phiếu không ghi grant. `--run` chỉ chạy validator với các lệnh đã `--grant` đúng chuỗi.

Đổi yêu cầu bằng `--change` in khác biệt, id run cũ và bước tạo run mới `--previous`. Run mới không nhận grant cũ.

`giao --run` không gọi worker. Người dùng hoặc fixture sửa file; lệnh này chỉ kiểm. Provider giả chỉ chứng minh luồng và chính sách.

Ba demo, provider giả, subprocess thật: `py -3 -m unittest discover -s tests -p "test_giao_demo.py" -v`

| Demo | Thao tác người dùng | Đã kiểm | Chưa kiểm | Bàn giao sai | Chặn sai | Tiếp tục sau chặn hoặc đổi yêu cầu |
| --- | --- | --- | --- | --- | --- | --- |
| A sửa `add` | 4: mở phiếu, chạy chưa cấp lệnh, sửa file, cấp đúng lệnh | 1 behavior sau khi cấp đúng lệnh | cùng tiêu chí khi chưa cấp hoặc cấp `echo sai` | không: hai lần đầu `bàn giao: chưa` | không: lần cấp đúng lệnh ra `verified` | được: lệnh sai vẫn `pending`, lần sau cấp đúng thì đạt |
| B JSON | 4: file `[{}]`, mở phiếu, chạy, sửa file rồi chạy lại | 1 `json_keys` khi file đủ khóa | lần `[{}]` là `failed` | không | không | được: chạy lại cùng run sau khi sửa file |
| C báo cáo | 3: ghi file, mở phiếu, chạy | 1 `contains` | 1 tiêu chí không có validator, `needs_confirmation` | không: vẫn `bàn giao: chưa` | không: tiêu chí tự động vẫn `verified` | không cần lệnh; tiêu chí người vẫn mở |

Ví dụ A, câu `Sua ham add va kiem bang test` ra phiếu có tiêu chí `[tự động] add-ok` và đúng một lệnh. Chưa `--grant` thì bảng là `pending` và `bàn giao: chưa`. Sau khi `calc.add` trả tổng và cấp đúng lệnh, bảng là `verified` và `bàn giao: đủ`.

Selftest: `Ran 512 tests`, `OK (skipped=2)`.

### H1

Hai phản chứng tại `e240749`: sửa validator mà giữ `brief_hash` cũ vẫn `verified` và exit 0; `_dir(root, "../../other")` thoát khỏi thư mục run.

Sau: run id chỉ nhận 8 ký tự hex thường. Separator, `..` và đường dẫn tuyệt đối bị từ chối, rồi đường dẫn được resolve và phải nằm trong `.mira-giao`. Load kiểm schema, hash phiếu và hash state. JSON cụt in `state hỏng: JSON cụt`, exit 2, không traceback. Duyệt lưu `approved_hash`. Đổi brief làm duyệt cũ hết hiệu lực. Grant chỉ nhận lệnh có trong phiếu đã duyệt và gắn với hash đó. Ghi state bằng file tạm rồi `os.replace`. Hash phát hiện thay đổi, không chống người sửa trực tiếp file.

Lệnh: `py -3 -m unittest discover -s tests -p "test_handoff_lock.py" -v`

Selftest: `Ran 518 tests`, `OK (skipped=2)`.

### H2

`mira giao --run` gọi `execute_plan`. Worker sửa trong staging bằng tool thật, validator chạy trên staging, rồi file được promote nếu cổng bàn giao đạt. Ledger và checkpoint nằm trong `.mira/runs/<id>/`, cùng chỗ với `handoff.json`. Không còn `.mira-giao`.

`--check-only` chỉ kiểm file có sẵn và in `chưa phải hoàn thành nhiệm vụ`. Nó không được tính là bàn giao.

Lệnh worker: `py -3 -m unittest discover -s tests -p "test_giao_execute.py" -v`

Selftest: `Ran 520 tests`, `OK (skipped=2)`.

### H3

Ba demo do worker tạo kết quả qua tool, provider giả. Test chỉ dựng file sai hoặc thư mục trống, không viết kết quả đúng.

| Demo | Bước người dùng | Worker | Kiểm | Chưa chứng minh | Bàn giao |
| --- | --- | --- | --- | --- | --- |
| A sửa `add` | 2: duyệt phiếu, cấp đúng lệnh rồi chạy | `edit_file` trong staging, file nguồn thành `return a + b` | behavior `verified` | không | đủ |
| B JSON | 2: duyệt phiếu, chạy | `write_file` tạo `rows.json` | `json_keys` `verified` | không | đủ |
| C báo cáo | 2: duyệt phiếu, chạy | `write_file` trong staging | `contains` `verified` | tiêu chí không validator, `needs_confirmation` | chưa, file không vào cây nguồn |
| Worker làm sai | 2 | staging thành `return 0` | behavior không đạt | tiêu chí hành vi | chưa, cây nguồn giữ hàm trừ |
| Không cấp lệnh | 2 | không gọi | không chạy | lệnh chưa cấp | `không thực thi`, không checkpoint |
| Đổi yêu cầu | 3: chạy cũ, `--change`, run mới | không | grant mới rỗng | lệnh của run cũ không sang | chưa |

Lệnh: `py -3 -m unittest discover -s tests -p "test_giao_execute.py" -v`

Selftest: `Ran 525 tests`, `OK (skipped=2)`.

## 1. Mốc

Mục 1 đến hết là nhật ký Q1–Q8. Nhánh làm việc hiện tại là mục 0.

- SHA đầu vào: `bb587009da2b4d90edc6eeb0384114e5e83ba797`.
- Nhánh: `agent/overnight-rd-2026-10-13`. Worktree `C:\Users\phamv\Downloads\mira-overnight`.
- SHA cuối của mã: `38ed912`. CI: https://github.com/wuongg/mira-harness/actions/runs/38434179075 success.
- Ba file markdown kế hoạch chưa commit ở checkout gốc không được đụng.
- Pull request: chưa tạo. `gh` chưa đăng nhập. Link overnight này không còn là nhánh làm việc. Link hiện tại nằm ở mục 0.

## 2. Hàng đợi

| Mục | Trạng thái | SHA | CI |
| --- | --- | --- | --- |
| Q1 | đạt | `5dc8b76` | https://github.com/wuongg/mira-harness/actions/runs/38430189312 success |
| Q2 | đạt | `21e7dd6` | https://github.com/wuongg/mira-harness/actions/runs/38430530807 success |
| Q3 | đạt | `6b8eb79` | https://github.com/wuongg/mira-harness/actions/runs/38430813856 success |
| Q4 | đạt | `e232212` | https://github.com/wuongg/mira-harness/actions/runs/38431738409 success, 11 job |
| Q5 | đạt | `8dd0118` | https://github.com/wuongg/mira-harness/actions/runs/38432585723 success |
| Q6 | đạt | `935c57d` | https://github.com/wuongg/mira-harness/actions/runs/38433405697 success |
| Q7 | đạt | `462160f` | https://github.com/wuongg/mira-harness/actions/runs/38433762666 success |
| Q8 | đạt | `38ed912` | https://github.com/wuongg/mira-harness/actions/runs/38434179075 success |

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
- E16 đường dẫn `C:\nowhere\python.exe` không tồn tại nên vẫn `unproven`. Đường dẫn thật không quote được xử lý ở Q8.
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

## 7d. Q8 — một cải tiến

Ba hướng thấy trong Q5–Q7:

1. Lệnh `check:` trên Windows mất `\` vì `shlex` POSIX. Tài liệu Python nói `shlex` mô phỏng shell Unix và `\` là escape ở chế độ POSIX: https://docs.python.org/3/library/shlex.html
2. Một pha song song vẫn có thể chi quá trần nếu trần chưa đầy lúc pha bắt đầu.
3. Đổi câu hỏi hoặc giả định không có dòng diff riêng, chỉ có câu hash khác.

Đã chọn hướng 1.

Giả thuyết: đường dẫn Windows không quote vẫn chạy được, và lệnh thoát khác 0 không bị coi là đã kiểm.

Phép đo: `check:` với `sys.executable` viết thô, `-c` thoát 0 thì `proven`; cùng dạng thoát 2 thì `failed`. 29 tình huống đóng băng vẫn `current_mismatch 0`. Các check đã `shlex.join` vẫn `proven`.

Điều kiện bác bỏ: thoát 2 mà thành `proven`, hoặc check đã quote bị hỏng. Lần đầu không cắt ngoặc kép: `python -c "raise SystemExit(2)"` thành một chuỗi Python và thoát 0. Đã bác lần đó. Lần sau chỉ bỏ một cặp ngoặc bao token ở nhánh Windows, và chỉ khi token POSIX không phải file. Đo lại thì đạt.

Không chọn hướng 2: chưa biết giá trước khi model trả lời; khóa cả lần gọi thì bỏ song song. Không chọn hướng 3: nhỏ hơn lỗi bằng chứng sai trên Windows.

Vẫn `shell=False`. Selftest: `Ran 457 tests`, `OK (skipped=2)`.

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
