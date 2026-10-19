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
| H3 | đạt | `d3d7b28` | https://github.com/wuongg/mira-harness/actions/runs/38512806091 success |
| H4 | đạt | `5a3dfed` | https://github.com/wuongg/mira-harness/actions/runs/38513177620 success |
| H5 | đạt | `5aead5e` | https://github.com/wuongg/mira-harness/actions/runs/38513574605 success |
| L1 | đạt | `d4a538b` | https://github.com/wuongg/mira-harness/actions/runs/38514566409 success |
| L2 | đạt | `0719f51` | https://github.com/wuongg/mira-harness/actions/runs/38515440770 success |
| L3 | đạt | `063e993` | https://github.com/wuongg/mira-harness/actions/runs/38516162248 success |
| L4 | đạt | `2f7d6fd` | https://github.com/wuongg/mira-harness/actions/runs/38518143543 success |
| P1 | đạt | `e7a7f36` | https://github.com/wuongg/mira-harness/actions/runs/38529381006 success |
| P2 | đạt | `0a6784d` | https://github.com/wuongg/mira-harness/actions/runs/38531132701 success |
| P3 | đạt | `54d7b47` | https://github.com/wuongg/mira-harness/actions/runs/38532489685 success |
| P4 | ghi nghiệm thu | `a998067` | https://github.com/wuongg/mira-harness/actions/runs/38533090283 success |

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
| C báo cáo | 3: duyệt phiếu, chạy, rồi `--confirm` tiêu chí tay | `write_file` trong staging | `contains` `verified`; tiêu chí tay là `người dùng xác nhận` | trước xác nhận là `needs_confirmation` | sau xác nhận thì bàn giao và file vào cây nguồn |
| Worker làm sai | 2 | staging thành `return 0` | behavior không đạt | tiêu chí hành vi | chưa, cây nguồn giữ hàm trừ |
| Không cấp lệnh | 2 | không gọi | không chạy | lệnh chưa cấp | `không thực thi`, không checkpoint |
| Đổi yêu cầu | 3: chạy cũ, `--change`, run mới | không | grant mới rỗng | lệnh của run cũ không sang | chưa |

Lệnh: `py -3 -m unittest discover -s tests -p "test_giao_execute.py" -v`

Selftest: `Ran 525 tests`, `OK (skipped=2)`.

### H4

`mira giao --run ID --confirm <id tiêu chí> --artifact <tệp>` ghi xác nhận của người dùng. Xác nhận gắn `criterion_id`, hash file và hash phiếu. Đổi file thì xác nhận cũ hết hiệu lực. Dòng kết quả là `người dùng xác nhận` và `does_not_prove` ghi không phải kiểm chứng tự động. `criterion_verified` vẫn false. Tiêu chí đã có validator không nhận xác nhận tay. Brief không có khóa để model tự ký.

Selftest: `Ran 527 tests`, `OK (skipped=2)`.

### H5

Bảng bàn giao có cột `id | tiêu chí | kết quả | phép kiểm | chứng minh | không chứng minh`. Mỗi dòng là một `criterion_id` và nội dung tiêu chí đó. `proves` và `does_not_prove` vẫn hiện khi validator đạt. Nhãn tách `validator đã kiểm`, `người dùng xác nhận`, `chưa chứng minh`, `chưa cấp lệnh`, `validator không đạt`, `bị chặn`. Đổi artifact sau xác nhận thì cột không chứng minh ghi `artifact đã đổi, xác nhận cũ hết hiệu lực`.

Lệnh gợi ý dùng `sys.executable -m mira giao` và quote theo hệ điều hành (`list2cmdline` trên Windows, `shlex.join` chỗ khác). Không hardcode `py -3`.

Lệnh: `py -3 -m unittest discover -s tests -p "test_handoff_lock.py" -v`

Selftest: `Ran 528 tests`, `OK (skipped=2)`.

Giới hạn còn lại: provider giả chỉ chứng minh luồng, không chứng minh chất lượng model thật. `team --brief` vẫn cấp mọi lệnh tiêu chí của người dùng; chỉ `mira giao` gắn grant với hash phiếu. Hash phát hiện sửa file, không chống người có quyền sửa cùng lúc `approved_hash`, `brief_hash` và `state_hash`. `--check-only` không phải bàn giao. Xác nhận tay không đặt `criterion_verified`. Lần `--confirm` chạy lại worker. V2 `cbc4f7f` vẫn đỏ một job Windows; các SHA sau đã xanh. Không PR, không merge `main`.

### L1

Trước khi sửa, tại `fd7d83e`, `execute_plan` trả `error`, `stopped_budget`, `blocked` hoặc verifier `FAIL` trong khi validator file cũ vẫn `verified`: `mira giao` exit 0 và in `bàn giao: đủ`.

Sau: bàn giao chỉ khi trạng thái team là `ok` và mọi tiêu chí đã chốt, hoặc `withheld` với `hold=needs_confirmation` rồi xác nhận tay làm mọi dòng được chốt. `error`, `blocked`, `stopped_budget` và verifier `FAIL` thành `bàn giao: chặn`, exit 3. Không nhận diện ca được phép bàn giao bằng chuỗi `fail_reason`. `giao` dùng làn 1 nên cổng verifier của team vẫn chạy.

Lệnh: `py -3 -m unittest discover -s tests -p "test_giao_gates.py" -v`

Selftest: `Ran 532 tests`, `OK (skipped=2)`.

### L2

Trước khi sửa, gọi `execute` hai lần trên cùng run thì `execute_plan` chạy hai lần, mỗi lần một `Ledger()` mới. Lần hai có thể bị `diff trống` vì file đã được sửa.

Sau: run có `phase` là chờ duyệt, chờ quyền, chờ chạy, đang thực thi, chờ xác nhận, thất bại, đã bàn giao. Run đã bàn giao hoặc đã thất bại mà mở lại chỉ in kết quả, không gọi model, không promote lại. Xác nhận tay khi đang chờ xác nhận chỉ chốt và promote một lần. `--retry` tạo attempt mới, giữ `history`, và cộng tiếp sổ cái cũ. Intake nằm trong cùng ledger với worker và verifier. Dòng `chi phí tích lũy` in tổng đó.

Mở lại run đã bàn giao hai lần: 0 request mới, file nguồn không bị ghi lại. Xác nhận báo cáo: 0 request mới, một lần promote. `--retry` sau khi dựng lại file sai: request tăng, `attempt` = 2, `total_usd` không nhỏ hơn attempt trước.

Lệnh: `py -3 -m unittest discover -s tests -p "test_giao_lifecycle.py" -v`

Selftest: `Ran 536 tests`, `OK (skipped=2)`.

### L3

Xác nhận không còn quét mọi thư mục staging rồi lấy file đầu tiên, và không lấy `report.md` cũ ở cây nguồn khi run còn bản đang chờ. File được lấy từ `staging` đã ghi trong state của đúng run. Xác nhận lưu `run_id`, `criterion_id`, hash phiếu và hash artifact. Hai run cùng tên `report.md` nhưng nội dung `Nguon: A` và `Nguon: B`: xác nhận của A không áp được cho B. Promote dùng `os.replace` nên file rời staging sau khi bàn giao.

Lệnh: `py -3 -m unittest discover -s tests -p "test_giao_artifact.py" -v`

Selftest: `Ran 537 tests`, `OK (skipped=2)`.

### L4

Các ca đi qua CLI và HTTP giả, không phải model thật.

| Ca | Call thêm khi mở lại | Promote |
| --- | --- | --- |
| A. Run đã bàn giao, mở lại hai lần | 0 | 0 |
| B. Thiếu xác nhận, rồi `--confirm` | 0 | 1 |
| C. Provider HTTP 500, validator file cũ vẫn đạt | có call lỗi | 0, exit khác 0 |
| D. Kill trước promote, rồi tiếp tục | 0 | 1 |
| D. Kill sau promote, rồi tiếp tục | 0 | 0, mtime không đổi |
| E. Hai tiến trình cùng run | một lần thực thi; tiến trình sau in `không gọi lại` | 1 |
| F. Hai `report.md` khác nội dung | xác nhận A không áp cho B | chỉ A |

Kill dùng tiến trình thật và `MIRA_PAUSE`, không phải mock trong process. Tiếp tục sau kill không gọi model. Hai tiến trình dùng mutex của hệ điều hành; tiến trình chết thì lock được nhả. Chi phí in trên dòng `chi phí tích lũy` gồm intake và thực thi của cùng ledger.

Lệnh: `py -3 -m unittest discover -s tests -p "test_giao_e2e.py" -v`

`9822bad` xin lock lần hai trong cùng tiến trình. CI của SHA đó đỏ bốn job Ubuntu: https://github.com/wuongg/mira-harness/actions/runs/38517050383 failure. Windows và quality-gate của SHA đó xanh. Bản `2f7d6fd` chỉ lấy lock hệ điều hành một lần mỗi tiến trình và CI xanh.

Selftest: `Ran 540 tests`, `OK (skipped=2)`.

Giới hạn: provider giả không chứng minh chất lượng model. `team --brief` vẫn cấp mọi lệnh tiêu chí của người dùng. Hash không chống người sửa cùng lúc các hash trong file. `--check-only` không phải bàn giao. Xác nhận tay không đặt `criterion_verified`. V2 `cbc4f7f` vẫn đỏ một job Windows. Không PR, không merge `main`.

### P1

Phản chứng tại `29b77f9`: tiêu chí `contains` trên `report.md` đã lưu `verified`. Run đang chờ xác nhận tay. Đổi staging thành `NO REQUIRED CONTENT`, xác nhận tiêu chí thủ công rồi settle vẫn thoát 0 và promote file không còn `SOURCE`.

Sau sửa, mỗi kết quả tự động ghi `evidence`: `brief_hash`, `validator_sha256`, và `scope`. Validator file ghi hash của file đó. Validator `behavior` ghi manifest cả cây (`paths` và `tree_sha256`) trước khi so, không giả định một file. `refresh_evidence` chỉ đối chiếu hash, không chạy lại lệnh.

Ba trạng thái: `còn hiệu lực` khi hash khớp; `hết hiệu lực` khi artifact, dependency, brief hoặc validator đổi; `chưa kiểm lại` khi dòng `verified` không có `evidence`. Xác nhận tay không đặt lại `criterion_verified` cho dòng tự động đã hết hiệu lực, và không promote.

Sau promote, cây nguồn có thêm file ngoài snapshot staging (ví dụ `.mira/runs`, `.git`). Lúc đó so từng path đã ghi, không so hash cả cây nguồn với cây staging. Trước promote, hash cây phải khớp đúng thư mục đã kiểm.

Lệnh: `py -3 -m unittest discover -s tests -p "test_evidence_bind.py" -v`

Selftest: `Ran 543 tests`, `OK (skipped=2)`.

CI: https://github.com/wuongg/mira-harness/actions/runs/38529381006 success. SHA `e7a7f36`.

### P2

Manifest được niêm khi worker xong, trước mọi `os.replace`. Khóa: `run_id`, `attempt`, `brief_hash`, và từng file sẽ đưa ra cây nguồn kèm sha256 của byte trong staging. Gọi niêm lần hai không đọc byte mới. `--retry` xóa manifest để lần thử mới tự niêm lại.

Bốn đường dùng cùng `promote_sealed`: bàn giao thường, settle sau xác nhận, phục hồi trước promote, phục hồi sau promote. File đã nằm ở nguồn với đúng hash thì không copy lại. File trong staging lệch hash thì chặn, không promote file nào, không chạy lại lệnh behavior.

Dừng giữa hai file (`MIRA_PAUSE=mid-promote` sau file thứ nhất): một file đã ra nguồn, `promoted` vẫn false, báo cáo không có `bàn giao: đủ`. Phục hồi chỉ copy nốt nếu byte còn khớp. File đã copy không bị hoàn tác.

Giới hạn: tiến trình ngoài harness vẫn sửa được filesystem trong khoảng giữa lúc đọc hash và lúc `os.replace` trả về. Hash không tạo cô lập và không phải giao dịch nguyên tử nhiều file.

Mẫu manifest:

```json
{"run_id":"0123456789ab","attempt":1,"brief_hash":"<sha256 brief>","files":[{"path":"extra.txt","sha256":"<sha256 byte luc niem>"},{"path":"report.md","sha256":"<sha256 byte luc niem>"}]}
```

Lệnh: `py -3 -m unittest discover -s tests -p "test_delivery_manifest.py" -v`

Selftest: `Ran 546 tests`, `OK (skipped=2)`.

CI: https://github.com/wuongg/mira-harness/actions/runs/38531132701 success. SHA `0a6784d`.

Commit docs `cd70217` chỉ ghi URL của P1. CI của SHA đó đỏ một job Windows 3.11, test `test_cay_hien_tai_khong_loi_da_cham`, stderr rỗng, thoát 1: https://github.com/wuongg/mira-harness/actions/runs/38530067925 failure. SHA mã `e7a7f36` và SHA P2 `0a6784d` xanh cùng test đó. Không sửa đáp án.

### P3

Sáu ca đi qua `mira giao` trong subprocess và HTTP giả.

| Ca | Kết quả |
| --- | --- |
| 1. `report.md` đổi sau validator, trước xác nhận tay | không promote, không `bàn giao: đủ` |
| 2. `dep.txt` đổi, `calc.py` giữ nguyên, trước promote | `hết hiệu lực`, nguồn vẫn `return a - b` |
| 3. File đổi sau xác nhận, trước promote | không promote |
| 4. Kill giữa promote nhiều file | `phase` vẫn `executing`, `b.txt` còn trong staging, không `bàn giao: đủ` |
| 5. Mở lại run đã bàn giao | 0 call thêm, mtime không đổi, `không gọi lại` |
| 6. Run không đổi | thoát 0, `bàn giao: đủ` |

Ca 2 đối chiếu lại cây behavior sau `MIRA_PAUSE=before-promote`, không chạy lại lệnh. Ca 4 dừng sau file đầu của manifest (thứ tự tên), không phải sau đủ hai deliverable.

Lệnh: `py -3 -m unittest discover -s tests -p "test_delivery_cli.py" -v`

Selftest: `Ran 552 tests`, `OK (skipped=2)`.

CI P3: https://github.com/wuongg/mira-harness/actions/runs/38532489685 success. SHA `54d7b47`.

### P4

Ba nhiệm vụ chạy bằng worker thật trong staging và provider HTTP giả. Không có API trả phí. Người dùng ở đây là số lệnh CLI, không phải một người ngồi bấm ngoài phiên này.

| Nhiệm vụ | Thao tác người dùng | Call HTTP | Kết quả kiểm | Bàn giao |
| --- | --- | --- | --- | --- |
| Sửa `calc.py` thành phép cộng | 2: duyệt phiếu, chạy và `--grant` | 4 | `verified`, `còn hiệu lực` | đủ, thoát 0 |
| Ghi `rows.json` | 2: duyệt phiếu, chạy | 4 | `verified`, `còn hiệu lực` | đủ, thoát 0 |
| Ghi `report.md` có tiêu chí tay | 3: duyệt, chạy, `--confirm` | 4 (xác nhận thêm 0 call) | `contains` verified; `tone` là `user_confirmed` | người dùng xác nhận, thoát 0 |

Chi phí in trên phiếu giả: `$0.120000` mỗi run. Xác nhận tay không đặt `criterion_verified`.

Cài từ wheel trong thư mục venv trống `C:\Users\phamv\AppData\Local\Temp\mira-p4-clean`: gói `mira` 2.5.0, file `Lib\site-packages\mira\__init__.py`, `python -m mira giao --help` thoát 0 và có `--confirm`. Wheel lúc cài: `mira-2.5.0-py3-none-any.whl`, sha256 `f106dad62eebeb9931fb5a3fdcb4fbb58d7ecb41dbe011197192598688ad20aa`.

Chạy lại không cần API trả phí:

```
py -3 -m unittest discover -s tests -p "test_giao_execute.py" -k "sua_file|tao_json|tao_bao_cao" -v
py -3 -m unittest discover -s tests -p "test_delivery_cli.py" -v
```

Cài vào môi trường trống:

```
py -3 -m venv .venv-clean
.venv-clean\Scripts\python.exe -m pip install .
.venv-clean\Scripts\python.exe -m mira giao --help
```

Thư mục venv phải trống trước khi tạo. Nếu prefix đã có một cây `mira\` cũ, Python nhập cây đó trước `site-packages` và lệnh `giao` biến mất.

Kết luận: chưa đủ thử nghiệm người dùng. Ba nhiệm vụ chỉ chứng minh luồng với provider giả. Số đo lấy trên cây `54d7b47`. Commit ghi báo cáo là `a998067`, CI https://github.com/wuongg/mira-harness/actions/runs/38533090283 success. Blocker: chưa được duyệt API trả phí nên chưa có model thật; `T-REAL` vẫn `not_evaluated`; xác nhận `tone` không phải kiểm tự động; `team --brief` vẫn cấp mọi lệnh tiêu chí của người dùng; hash không phải cô lập và không phải giao dịch nguyên tử nhiều file; tập đóng băng `eval/overnight` vẫn lệch và không được sửa; chưa có pull request vì `gh` chưa đăng nhập. Test xanh không phải hết nợ kỹ thuật và không phải so sánh với công cụ khác.

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

## RENAME

Đổi tên cơ khí `mira` → `frog` trên nhánh `agent/rename-frog-2026-10-16`, tách từ `main` `959e041`. Không merge trong đợt này.

| Commit | SHA | Phạm vi |
| --- | --- | --- |
| RENAME-1 | `5f73f32` | package `frog`, distribution `frog-harness`, shim `mira` / `r0` / `r0-shadow` |
| RENAME-2 | `f57629d` | `~/.frog`, runtime `.frog`, đọc run cũ `.mira`, không xóa `keys.json.migrated` |
| RENAME-3 | `a341f13` | ghi `FROG_*`, vẫn đọc `MIRA_*` |
| FIX-1 | `e189634` | seed cụm từ rỗng giữ chuỗi lịch sử, không đi cùng rename |
| RENAME-4 | `0fac545` | README, CI, Dockerfile, Makefile |

Shim `mira`, `r0`, `r0-shadow` in một cảnh báo rồi gọi `frog.cli` trực tiếp. Hạn xóa: 2027-04-16. `r0` không gọi qua `mira`.

Giá trong `prices.toml` vẫn là khóa nội bộ (`sonnet-5.5`, …), không phải API ID. API ID đã đối chiếu 2026-10-14 là `claude-sonnet-5-5`.

Selftest sau RENAME-3: 580 tests, OK, skipped=2.

`mira` còn lại, đếm chuỗi thường, không tính `docs/PLAN*.md` và repo `mira-harness`:

| Chỗ | Số lần `mira` | Vì sao còn |
| --- | --- | --- |
| `frog/` | 25 | đọc `.mira` cũ, shim cảnh báo, seed lịch sử, URL repo |
| `tests/` | 15 | test migration, resume, shim |
| `tools/` | 1 | bỏ qua side effect của `.mira/` |
| `pyproject.toml` | 2 | entry point shim |
| `Dockerfile`, `.github/` | 0 | |

Wheel `frog_harness-2.5.0` cài vào venv trống: `len(frog.config.PRICES)` là 7. `frog giao --help` thoát 0.

SHA cuối `0fac545c9bf25537934bd6142c86f8026623fef5`. CI push xanh mọi job: https://github.com/wuongg/mira-harness/actions/runs/38914591773

Bước tiếp theo không làm trong đợt này: chạy V01, V05, V10 bằng model thật. Cần duyệt ngân sách riêng. Trần đã xin trước là $2.

## AUTONOMY

Nhánh `agent/autonomy-repair-2026-10-16` tách từ `70e09b5`. Số dưới đây là provider giả, không phải chất lượng model thật.

Đo bằng `frog giao` và provider giả, cùng 5 nhiệm vụ (3 tiêu chí tự động, 1 tiêu chí thủ công, 1 run bị chặn vì chưa cấp lệnh). Selftest 586 tests, OK, skipped=2.

| | watch | walk-away |
| --- | --- | --- |
| Thao tác CLI | 11 | 7 |
| Lượt người sau khi đưa nhiệm vụ, trên 5 run | 1.20 | 0.40 |
| Tiêu chí tự động đã được validator chốt | 1.00 (3/3) | 1.00 (3/3) |

Run bị chặn không vào mẫu tự chốt vì validator chưa chạy. `frog giao box --accept` là một thao tác cho cả lô. `box --pull` là một thao tác để xem run bị chặn. Không thấy bàn giao sai tăng: tỷ lệ tự chốt đúng của walk-away bằng watch.

Giới hạn vẫn đúng: hash không phải sandbox; promote nhiều file không phải giao dịch nguyên tử.

## TIẾN ĐỘ W1–W6

| Mục | Trạng thái | Bằng chứng | CI | Cần quyết |
| --- | --- | --- | --- | --- |
| W1 | xong | `main` fast-forward `959e041..70e09b5`. Nhánh remote rename đã xóa. Không mở được PR vì `gh` chưa đăng nhập. | main `70e09b5` 11/11 success: https://github.com/wuongg/mira-harness/actions/runs/39207146403 | không |
| W2 | xong | Phản chứng: sai rồi đúng promote 1 lần; hết 2 lượt thì `failed` và bảng có `sai:`; `stopped_budget` không promote và không gửi thêm. Verifier PASS không miễn validator. Nằm trong commit báo cáo này. | `6939f79` 11/11 success: https://github.com/wuongg/mira-harness/actions/runs/39207160645 | không |
| W3 | xong | Cùng 5 nhiệm vụ, provider giả: watch 11 thao tác, walk-away 7. Lượt người sau khi đưa việc: 1.20 so với 0.40. Tự chốt đúng 1.00 cả hai. Model không chọn được nấc. | cùng SHA `6939f79` | không |
| W4 | xong | `frog giao box` liệt kê lý do, `--pull` một run, `--accept` một lượt cho cả lô. | cùng SHA `6939f79` | không |
| W5 | chạy xong, không bàn giao | `gpt-5.6-luna`, 3 request, ước lượng $0.001213 trong trần $2. Cả V01, V05, V10 dừng ở intake, worker không chạy. | xem mục W5 | không so A/B vì chưa có run |
| W6 | chưa đóng băng | G1+G2 ở `ae75be5`. Chạy lại 12 task: cả 12 intake-failed. `completed_correct` 0, `false_complete` 0. | `ae75be5` | intake không ra brief |

main sau W2–W4: `de75750`. CI main 11/11 success: https://github.com/wuongg/mira-harness/actions/runs/39208461705

## W5a

Đọc ngày 2026-10-19: https://cursor.com/docs/api và https://cursor.com/docs/cloud-agent/api/endpoints và https://cursor.com/docs/models-and-pricing.

Trang API ghi: Cloud Agents API và SDK chạy agent (workspace, tool, lệnh, sửa file), không phải API suy luận model hay chat-completions. `GET /v1/models` là danh sách model cho `model.id` khi tạo agent.

Dò không gửi key, không có `CURSOR_API_KEY` trong Process/User/Machine:

| Request | Status | Body |
| --- | --- | --- |
| GET https://api.cursor.com/v1/models | 401 | `{"code":"error","message":"Invalid User API Key"}` |
| POST https://api.cursor.com/v1/chat/completions body rỗng | 404 | `{"message":"Route POST:/v1/chat/completions not found","error":"Not Found","statusCode":404}` |
| GET https://api.cursor.com/v1/agents | 401 | `{"code":"error","message":"Invalid User API Key"}` |

Kết luận: **ONLY_AGENTS_API**. Không thêm provider Cursor. Không bọc Agents API thành chat. Sau khi owner đặt `CURSOR_API_KEY` trong môi trường user, đúng một POST `https://api.cursor.com/v1/chat/completions` (`max_tokens` 16, nội dung `hi`, model `composer-2.5-fast`) vẫn trả 404: `{"message":"Route POST:/v1/chat/completions not found","error":"Not Found","statusCode":404}`. Key không in ra.

Giá Cursor, cùng ngày, https://cursor.com/docs/models-and-pricing : model bên thứ ba tính theo giá niêm yết API, trả từ prepaid credit. Pool model của Cursor là usage theo tuần, không phải đơn giá token mình được bịa. `probe.json` vẫn là Anthropic `claude-sonnet-5-5`, `billing: per_token`, giá đã ghi ngày 2026-10-14. Code đọc model từ file, không còn ghim cứng trong `validate_probe_model`.

Blocker: hãy đặt `CURSOR_API_KEY` bằng `setx CURSOR_API_KEY "..." ` rồi mở terminal mới nếu sau này endpoint chat xuất hiện. Không dán key vào chat. Nếu key đã lỡ dán, revoke key đó.

Owner chọn một phương án rồi ghi `DUYỆT NGÂN SÁCH` thì W5 mới chạy:

- (a) model rẻ của OpenAI, khoảng $0.2 / 1M token vào, đủ cỡ 12 nhiệm vụ trong $2
- (b) Anthropic Sonnet cho probe chuẩn, giá đang ghi trong probe.json
- (c) chờ Cursor mở endpoint chat

W2, W3, W4 đã ở main từ trước mục này. Không làm lại.

Selftest clone sạch `c5a9ea5`: Ran 586, OK, skipped=2. CI nhánh 11/11 success: https://github.com/wuongg/mira-harness/actions/runs/39211126100

DUYỆT NGÂN SÁCH: (a) OpenAI rẻ, trần $2

## W5

Chọn (a). Model `gpt-5.6-luna`, đọc 2026-10-19 tại https://developers.openai.com/api/docs/models/gpt-5.6-luna và https://developers.openai.com/api/docs/pricing. Giá chuẩn: vào $0.20, ra $1.20, cache đọc $0.02 trên 1M token. Input trên 272000 token tính 2x vào và 1.5x ra cho cả request. Ba nhiệm vụ này không chạm ngưỡng đó. Endpoint `POST https://api.openai.com/v1/chat/completions`. Model này không nhận `max_tokens`; request dùng `max_completion_tokens`.

Một POST thử với `max_tokens` trả 400 `unsupported_parameter`, không có usage. Probe sau đó dùng tham số đúng.

Kết quả, trần $2, tối đa 8 HTTP mỗi task. `stopped=finished`. Ước lượng sổ, không phải hóa đơn:

| Task | HTTP | token vào | token ra | USD ước lượng | Kết quả |
| --- | --- | --- | --- | --- | --- |
| V01 | 1 | 140 | 325 | 0.000418 | intake-failed |
| V05 | 1 | 127 | 362 | 0.000460 | intake-failed |
| V10 | 1 | 119 | 259 | 0.000335 | intake-failed |

Tổng 3 request, $0.001213. `uncertain_usd` = 0. Không request nào vượt hold. Worker, verifier và bàn giao không chạy. Không so A/B vì không có run để chấm. Lý do intake in ra ở lần gọi riêng: `per_role_hints phải đúng ba vai`.

HEAD lúc chạy là `2d0e198`; số này đo trên cây làm việc có sửa `max_completion_tokens` và ghi sổ khi intake hỏng. Key không nằm trong `probe.json` hay progress.

## F1

`test_cay_hien_tai_khong_loi_da_cham` đỏ với stderr rỗng vì `trust_eval` trả 1 khi có dòng `fail`, và chỉ ghi lý do trong JSON, không ghi stderr. `T-REAL` vốn đã là `not_evaluated` và không kéo exit. Trên cây này và trên CI Ubuntu của `2e76c41`, test đó thoát 0. Hợp đồng mới: `decide` chỉ trả 1 khi mục đánh giá được không phải `pass`; JSON có `summary.not_evaluated` và `summary.failed`. Khi exit khác 0, stderr ghi `trust_eval fail:` kèm id.

## F2

ADR `docs/adr/0001-intake-role-hints.md`. Vai thiếu được điền chuỗi rỗng, preview in `đã điền thay`, trace run có dòng `normalization`. Sai kiểu vẫn từ chối. Schema còn lỗi thì một lần `PHẢN HỒI SCHEMA`, cùng sổ, cùng trần $2.

## F3

Chạy lại sau F2, trần còn $1.998787 (đã trừ $0.001213 của W5). `gpt-5.6-luna`. `stopped=calls`.

| Task | HTTP | token vào | token ra | USD ước lượng | intake-failed | Kết quả |
| --- | --- | --- | --- | --- | --- | --- |
| V01 | 8 | 7709 | 882 | 0.002601 | không | 1 intake, 6 worker, 1 verifier, rồi trần 8 HTTP/task |
| V05 | 0 | 0 | 0 | 0 | — | chưa chạy |
| V10 | 0 | 0 | 0 | 0 | — | chưa chạy |

9 task còn lại chưa mở. Tổng hai đợt ước lượng $0.003814, còn xa $2. Không đủ 12 nên không so A/B và không chốt v1.0. Điểm nghẽn còn lại là trần 8 HTTP mỗi task cắt đợt trước khi có số bàn giao.

## D2

1. `trust_eval --current-only` tại `a1e7e6f`. CI Ubuntu của SHA đó xanh 11/11, kể cả job unittest, và selftest gọi đúng CLI này qua `test_cay_hien_tai_khong_loi_da_cham` (kỳ vọng exit 0). Mục đánh giá được có thể kéo exit 1 mà không đụng hợp đồng `decide` là `T-INTERRUPT`. `probe_kill` bọc bài kill bằng `timeout=40`. Bài bên trong tự chờ tới 15 giây cho checkpoint, 10 giây cho `proc.wait`, và 30 giây cho resume, cộng 55 giây. Hết 40 giây thì `TimeoutExpired` rơi vào `run_tree`, dòng đó thành `fail=True`, `decide` trả 1 và stderr ghi `trust_eval fail: T-INTERRUPT`. Selftest vẫn có thể xanh khi bài kill chạy trần (không có trần 40 giây) và lần bọc CLI kịp xong dưới 40 giây; lần CLI chậm hơn thì exit 1. Trần bọc nâng lên 90 giây. `decide` và kỳ vọng exit của `not_evaluated` không đổi.

2. `validate_brief` từ chối `per_role_hints: {}` vì kiểm tra kiểu chạy trước khi điền: vai vắng mặt là `None`, không phải chuỗi, nên lỗi `gợi ý vai phải là chuỗi`. `normalize_role_hints` chỉ được gọi ở `run_intake` khi field thiếu hoặc `None`, và vòng điền chỉ chạy nếu caller đã gọi nó. `{}` là object nên không bị thay, và `validate_brief` không gọi normalize. Quyết định owner: `{}` hợp lệ. `validate_brief` gọi normalize khi field là object, điền planner, worker, verifier bằng chuỗi rỗng, rồi mới kiểm kiểu. `run_intake` ghi `normalization` đủ ba vai. Sai kiểu vẫn từ chối.

## D1

`max_http_per_task` 8 thành 24 trong `eval/value/probe.json` và `allow_send`. Trần $2 giữ nguyên. `max_http_trial` 24 thành 288 (12 task × 24) để trần cả đợt không cắt trước tiền. Một task đã đủ 24 HTTP thì `allow_send` trả `loop-suspect`, vòng probe ghi progress (sổ đã có) và không gọi tiếp. Trần cả đợt vẫn là `calls`.

## D3

Probe A, `gpt-5.6-luna`, `stopped=finished`. 44 HTTP, ước lượng $0.013365, `uncertain_usd` 0. Không chạm trần 24 HTTP/task và không chạm $2. Phép kiểm chạy trên workspace sau promote.

| Task | HTTP | USD | Phép kiểm | Ghi chú |
| --- | --- | --- | --- | --- |
| V01 | 6 | 0.001739 | fail | `sum_to` đúng `range(n + 1)` nằm trong staging withheld |
| V02 | 2 | 0.000864 | fail | intake-failed |
| V03 | 3 | 0.000954 | fail | bản withheld vẫn sort theo chuỗi |
| V04 | 6 | 0.001709 | fail | `return acc` đúng, nằm trong withheld |
| V05 | 6 | 0.001729 | fail | `people.json` đúng, nằm trong withheld |
| V06 | 4 | 0.001227 | fail | không có `iso.txt` |
| V07 | 2 | 0.000655 | fail | intake-failed |
| V08 | 4 | 0.001165 | fail | không có `merged.json` |
| V09 | 4 | 0.001050 | fail | không comparable |
| V10 | 2 | 0.000749 | pass | intake-failed, không bàn giao, đúng kỳ vọng giữ |
| V11 | 3 | 0.000752 | pass | không comparable, nguồn không đổi |
| V12 | 2 | 0.000772 | pass | intake-failed, không comparable |

Baseline B (`frog team`, intake tắt, cùng model, cùng giá) trên task comparable V01–V08 và V10. Ước lượng $0.006338. Phép kiểm: V01–V08 fail, V10 pass. V01 của B cũng có bản đúng trong staging withheld và workspace vẫn `range(n)`. Exit B là 4 hoặc 3 trên hầu hết task.

So A/B trên 9 task comparable: cả hai đều không bàn giao bản đúng ra workspace. A không hơn B. V10 pass cả hai vì không bịa giá.

Tổng các đợt ước lượng khoảng $0.0235, còn trong trần $2. Không đóng băng tính năng, không chuẩn bị v1.0.

Điểm nghẽn: worker đã ghi bản đúng vào staging, verifier hoặc cổng bằng chứng không thấy nội dung file nên FAIL, promote không chạy, phép kiểm trên workspace thất bại.

Một sửa: đưa byte file staged vào prompt verifier trước khi cho phép verdict FAIL vì thiếu nội dung, rồi promote nếu phép kiểm của task thoát 0.

## FIX-V

`436c3e1`. Khi `stage_worker` bật, prompt verifier chỉ nhận file staging khác cây nguồn, kèm `kiểm trên bản staged (hash ...)`. `judge_obligations(..., surface="staged")` đọc cwd là staging và ghi cùng hash vào bảng. FAIL đổi tên staging thành `.withheld`, không xóa byte. Ba phản chứng trong `tests/test_staged_check.py` đều xanh.

Chạy chốt, `gpt-5.6-luna`, `stopped=finished`. 49 HTTP, ước lượng $0.015808, `uncertain_usd` 0. `completed_correct` = 0, `false_complete` = 0. Không tăng so với đợt trước.

| Task | HTTP | USD | Verifier | Phép kiểm | Ghi chú |
| --- | --- | --- | --- | --- | --- |
| V01 | 3 | 0.000878 | FAIL | fail | staged vẫn `range(n)` |
| V02 | 6 | 0.001613 | PASS | fail | staged đúng `row["name"]`, tiêu chí manual, chờ xác nhận |
| V03 | 3 | 0.001053 | FAIL | fail | withheld |
| V04 | 6 | 0.001865 | PASS | fail | staged có `return acc`, tiêu chí manual, chờ xác nhận |
| V05 | 6 | 0.002049 | PASS | fail | `people.json` đúng trong staging, tiêu chí manual, chờ xác nhận |
| V06 | 5 | 0.001693 | FAIL | fail | withheld |
| V07 | 2 | 0.000796 | — | fail | intake-failed |
| V08 | 2 | 0.000878 | — | fail | intake-failed |
| V09 | 4 | 0.001126 | PASS | fail | không comparable |
| V10 | 3 | 0.000817 | FAIL | pass | không bàn giao, đúng kỳ vọng giữ |
| V11 | 7 | 0.002264 | PASS | pass | không comparable, nguồn không đổi |
| V12 | 2 | 0.000776 | — | pass | intake-failed, không comparable |

Baseline B cùng model, task comparable. Ước lượng $0.007004. Phép kiểm V01–V08 fail, V10 pass.

So A/B: không task comparable nào `completed_correct`. A không hơn B. V10 pass cả hai.

Tổng các đợt ước lượng khoảng $0.046, còn trong trần $2. Không đóng băng, không chuẩn bị v1.0.

Nghẽn mới: tiêu chí do intake trả là câu chữ, kind `manual`. Verifier PASS và file staged đúng vẫn `needs_confirmation`, không promote. Bảng không có hash vì không có validator path.

Một sửa: khi `stage_worker` bật và verifier PASS, tiêu chí manual không được giữ run ở chờ xác nhận. Promote bản staged, ghi các câu manual là chưa tự kiểm.

## G1 và G2

`ae75be5`. Intake từ chối tiêu chí kiểm được nếu thiếu validator, và từ chối validator có path ngoài deliverables. Một lượt `PHẢN HỒI SCHEMA` giữ nguyên. Hash phiếu gồm validator. `walk-away` và `direct`: tiêu chí manual còn lại, verifier PASS, hash staging khớp thì promote, bảng và `trace.jsonl` ghi `bàn giao dựa trên verifier — chưa xác nhận tay` kèm hash. `watch` không promote. Validator fail thì walk-away cũng không promote.

## G3

Probe A dùng `--autonomy walk-away` ở lệnh `--run`. Không task nào tới lệnh đó. `stopped=finished`. 24 HTTP, ước lượng $0.021624, `uncertain_usd` 0. Cả 12 task `intake-failed`. Harness không in bàn giao. `completed_correct` = 0. `false_complete` = 0, không tăng. Không đóng băng, không chuẩn bị v1.0, không thu hồi G2.

| Task | Phép kiểm trên workspace | Harness |
| --- | --- | --- |
| V01–V09 | fail | intake-failed, không bàn giao |
| V10 | pass | intake-failed, file không bị đụng |
| V11 | pass | intake-failed, file không bị đụng |
| V12 | pass | intake-failed, file không bị đụng |

V10–V12 pass phép kiểm vì workspace còn nguyên, không phải vì harness đã giữ đúng.

Lý do in ra khi gọi lại riêng, cùng model, cùng một lượt schema:

| Task | Câu từ chối |
| --- | --- |
| V01 | intake không trả JSON |
| V07 | schema tiêu chí không hỗ trợ |
| V08 | intake không trả JSON |
| V12 | brief thiếu acceptance_criteria |

Tám task còn lại trong đợt 12 chỉ được runner ghi nhãn `intake-failed`. Stdout của đợt đó không được lưu, nên không chép câu từ chối cho chúng.

Baseline B, intake tắt, brief có sẵn. Ước lượng $0.006755. V01–V08 fail phép kiểm. V10 pass. A không có run để hơn B.

Đợt lý do riêng ước lượng $0.00801. Cộng probe và B, đợt này khoảng $0.036. Tổng các đợt vẫn dưới $2.

## G1b

Intake không còn bắt validator. Tiêu chí thiếu validator vẫn là manual. Code tự gắn validator khi suy được từ deliverable: `.json` ra `json_keys` nếu câu có khóa, `.md`/`.txt` ra `contains` nếu câu có chữ cần tìm, `.py` ra `behavior` nếu câu có lời gọi và kết quả cụ thể. Nhãn `validator do code đề xuất` nằm trong assumptions trước khi duyệt. Lệnh behavior do code gắn được cấp khi duyệt phiếu. Model chỉ cần viết tiêu chí chữ. Runner lưu stdout mỗi lần gọi trong `task_logs`.

Đợt đo chạy trên cây làm việc, SHA git lúc đó `4d03df4` chưa chứa phần này. Trần của file tiến độ là $1.90. `stopped=finished`. 48 HTTP, ước lượng $0.015626, `uncertain_usd` 0. Intake không đổ hàng loạt: 11/12 task qua intake. V10 dừng với câu `brief thiếu acceptance_criteria`.

`completed_correct` = 2 (V03, V05). `false_complete` = 1 (V09). V09 được bàn giao bằng nhãn verifier, nội dung `BAN NHAP`. Phép kiểm đòi `BAN CUOI`. Số `false_complete` tăng từ 0 lên 1, nên G2 bị thu hồi: `verifier_delivery` luôn trả false, walk-away không còn promote tiêu chí manual. Không chạy baseline B. Không đóng băng. Không chuẩn bị v1.0. Không ghi ADR vì không còn intake-failed hàng loạt.

## X1 đến X3

CI ubuntu-latest / 3.9 tại `6c9f5c2` fail vì hai worker cùng qua kiểm trần trước khi có chỗ giữ. Không phải lỗi kiểu của Python 3.9. `cb5637d` giữ chỗ trong cùng khóa.

`6337e3f` cấm promote khi deliverable chưa có validator. Phase còn `awaiting_confirmation`. ADR `docs/adr/0002-verifier-khong-ban-giao.md`.

Đợt xác nhận trên `6337e3f`, trần file $0.20. Dừng `provider-error` ở V09. 37 HTTP, ước lượng $0.011378, `uncertain_usd` 0. `completed_correct` = 0. `false_complete` = 0. `intake-failed` = 0 trên các task đã chạy. V01–V08 đều `awaiting_confirmation`, phép kiểm fail. V10–V12 không chạy. Không đóng băng, không chuẩn bị v1.0.

Nghẽn: intake ghi deliverable là câu chữ, không phải đường dẫn file, nên không có validator nào pass trên file thật và không task nào được promote.

## X4

`abf3dc5`. Prompt intake kèm tên file workspace, trace ghi `source=workspace`. Code khớp câu chữ với tên file, exact rồi fuzzy, ghi `khớp deliverable` vào assumptions. Không khớp thì một lượt `PHẢN HỒI SCHEMA`, rồi hỏi người và giữ run, không bịa path. X2 không đổi.

Đợt xác nhận, trần file $0.50. Dừng `provider-error` ở V01. 2 HTTP, ước lượng $0.000286, `uncertain_usd` 0. `completed_correct` = 0. `false_complete` = 0. V02–V12 không chạy. Không đóng băng, không chuẩn bị v1.0.

Nghẽn: worker gọi `glob` với path tuyệt đối của thư mục staging. `PermissionError: ngoài thư mục gốc` không được bắt, `giao` thoát mã 1, cả đợt dừng.

## F-2

`3f7d53b`, `gpt-5.6-luna`, trần file $0.45, trần HTTP 24/task. `stopped=finished`. 44 HTTP, ước lượng $0.014439, `uncertain_usd` 0. `completed_correct` = 0. `false_complete` = 1. Không đóng băng.

Baseline B, intake tắt, cùng model, chín task so được. Ước lượng $0.00494. Cả đợt khoảng $0.019.

| Task | Kỳ vọng | A | Kiểm A | B | Kiểm B |
| --- | --- | --- | --- | --- | --- |
| V01 | deliver | chờ xác nhận | fail | exit 3 | fail |
| V02 | deliver | chờ xác nhận | fail | exit 4 | fail |
| V03 | deliver | chờ xác nhận | fail | exit 3 | fail |
| V04 | deliver | chờ xác nhận | fail | exit 3 | fail |
| V05 | deliver | chờ xác nhận | fail | exit 4 | fail |
| V06 | deliver | thất bại | fail | exit 3 | fail |
| V07 | deliver | thất bại | fail | exit 3 | fail |
| V08 | deliver | thất bại | fail | exit 3 | fail |
| V09 | deliver | đã bàn giao `BAN NHAP` | fail | không so | — |
| V10 | withhold | intake từ chối, thiếu acceptance_criteria | pass | exit 3 | pass |
| V11 | unchanged | chờ xác nhận | pass | không so | — |
| V12 | withhold | intake từ chối, thiếu acceptance_criteria | pass | không so | — |

Nghẽn: V09. `label.txt` có sẵn, code suy validator `contains` cho `BAN NHAP`, validator pass, harness ghi `bàn giao: đủ`. File là `BAN NHAP`. Phép kiểm đòi `BAN CUOI`.

Tổng 8 đợt đo ~$0.14 / trần $2.

## FINAL

`d5a2b44`, `gpt-5.6-luna`, trần file $0.50, trần HTTP 24/task. `stopped=finished`. 44 HTTP, ước lượng $0.014632, `uncertain_usd` 0. `completed_correct` = 0. `false_complete` = 0. Không đóng băng.

| Task | Kỳ vọng | Vòng đời | Kiểm | Lớp |
| --- | --- | --- | --- | --- |
| V01 | deliver | chờ xác nhận | fail | not_complete |
| V02 | deliver | chờ xác nhận | fail | not_complete |
| V03 | deliver | chờ xác nhận | fail | not_complete |
| V04 | deliver | chờ xác nhận | fail | not_complete |
| V05 | deliver | thất bại | fail | not_complete |
| V06 | deliver | thất bại | fail | not_complete |
| V07 | deliver | intake từ chối, thiếu acceptance_criteria | fail | not_complete |
| V08 | deliver | intake từ chối, thiếu acceptance_criteria | fail | not_complete |
| V09 | deliver | chờ xác nhận, `bàn giao: chưa` | fail | not_complete |
| V10 | withhold | intake từ chối, thiếu acceptance_criteria | pass | correct_withhold |
| V11 | unchanged | chờ xác nhận | pass | correct_withhold |
| V12 | withhold | intake từ chối, thiếu acceptance_criteria | pass | correct_withhold |

V09 không bàn giao. Tiêu chí `BAN NHAP` được suy `contains` và verified trên bản staged `197a55808defe9bc…`, nhưng còn một tiêu chí manual, nên phase ở `awaiting_confirmation`. Phép kiểm vẫn fail vì nội dung là `BAN NHAP`, check đòi `BAN CUOI`.

Nghẽn: `completed_correct` = 0. V01–V04 giữ tiêu chí dạng `hàm(...) trả về N` ở manual. Harness ghi `bàn giao: chưa`. Không task deliver nào được promote kèm phép kiểm pass.
