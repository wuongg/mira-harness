# Plan vòng 2 từ ngày 2 — `docs/PLAN-V3.md`

Nguồn lệnh: `mira-harness_ke-hoach-vong-2.md` (đọc hết, Phần C đọc hai lần) và code trên `main` sau `fa3166f`. Máy này không có `python3`. Mọi lệnh kiểm là `py -3`. Commit bằng Python `Path.write_text(..., encoding="utf-8")` rồi `git commit -F .git/COMMIT_MSG.txt`. Không `Set-Content -Encoding utf8`. Tiêu đề ASCII, không dấu, không BOM, không quá 72 ký tự, khớp `^\[[A-Z0-9-]+\] \S`. Không thêm dependency. Không rewrite lịch sử. Không làm T2, T3, T4, P1-04, P1-06, P2 trở đi trong lát này: người giao việc khóa thứ tự đến P1-03. Các mục đó giữ nguyên trong tài liệu vòng 2, không bị xóa khỏi backlog.

Sau khi duyệt, việc đầu tiên của bước 2 là ghi nguyên văn plan đã duyệt vào [docs/PLAN-V3.md](docs/PLAN-V3.md). File đó đi cùng commit `[TAIL-1]`, không tách ID riêng. Chưa sửa code trước khi plan này được duyệt.

## 0. Bốn sót tên cũ — bằng chứng vừa grep

Lệnh đã chạy trên cây hiện tại, phạm vi `mira/`, `tests/`, `docs/`, đuôi `.py` và `.md`. Đúng bốn chỗ trong mã và test còn chuỗi cấm. `r0/*.py` ngoài shim không còn trong `git ls-files`. Các dòng trong `docs/` là biên bản vòng 1 và 2b, không phải định danh đang chạy.

Bốn chỗ phải hết trong `[TAIL-1]`:

- [mira/mascot_art.py](mira/mascot_art.py) dòng 16: `_PNG = Path(__file__).resolve().parents[1] / "chon_dat_cutout.png"`. File ảnh không có trên đĩa. [tests/test_mascot_art.py](tests/test_mascot_art.py) dòng 11–13 đã `skipTest` khi vắng.
- [tests/test_mascot_art.py](tests/test_mascot_art.py) dòng 7: cùng chuỗi `chon_dat_cutout.png`.
- [tests/test_names.py](tests/test_names.py) dòng 32: `hasattr(team, "HOI_TOOLS")`. Hằng thật đã là `READ_TOOLS` tại [mira/team.py](mira/team.py) dòng 82. Dòng 147 dùng `READ_TOOLS`.
- [tests/test_names.py](tests/test_names.py) dòng 43: `chon_dat_256.txt`. File palette thật là `mira/tui_palette_256.txt`, nạp tại [mira/mascot_art.py](mira/mascot_art.py) dòng 588 `_IDX = Path(__file__).with_name("tui_palette_256.txt")`.

Còn lại sau bốn chỗ đó, cùng regex, chỉ trong `docs/` (biên bản, không sửa trong TAIL-1):

- [docs/PLAN.md](docs/PLAN.md) dòng 11, 27, 40, 222 nhắc tên ảnh và shape `"sua"` như bằng chứng lịch sử.
- [docs/PLAN-2B.md](docs/PLAN-2B.md) nhiều dòng mô tả grep và rename đã làm. S5 đã cho phép file này giữ chữ cũ.
- [docs/README.md](docs/README.md) dòng 4 nhắc `chon_dat.sh`, script vẽ vẫn nằm trong `docs/`.

TAIL-1 không viết lại biên bản. Nếu sửa PLAN.md và PLAN-2B để regex trên `.md` về 0, mất dấu vết đối chiếu. Cổng chặt cho mã đang chạy là: sau commit, `git grep -nE` trên `mira` và `tests` với mẫu `HOI_TOOLS|"sua"|chon_dat` bằng 0. Lệnh người giao gồm cả `docs/` sẽ còn các dòng biên bản ở trên. Báo đúng số đó trong checklist, không gọi là sót runtime.

### TAIL-1 hành vi

- [mira/mascot_art.py](mira/mascot_art.py): đổi `_PNG` thành `MASCOT_PNG = Path(__file__).with_name("mascot_rgba.png")`. Ảnh vẫn không được bịa. `render` khi thiếu file trả `[]` như test `test_missing_file` đang chờ. Không thuật toán vẽ mới.
- [tests/test_mascot_art.py](tests/test_mascot_art.py): import `MASCOT_PNG`. `test_half_block_truecolor` skip khi file vắng. Không còn chuỗi cũ trong file.
- [tests/test_names.py](tests/test_names.py) `test_khong_con_hoi_tools`: `sorted(n for n in dir(team) if n.endswith("_TOOLS"))` bằng `["READ_TOOLS", "WRITE_TOOLS"]`. Không viết tên hằng cũ.
- `test_palette_doi_ten`: mọi `*.txt` trực tiếp trong `mira/` đúng một tên `tui_palette_256.txt`.

Không đụng `human_gate`, `_executor_write`, shape, eval slug.

Ước lượng: 15 dòng sửa, 0 file mới.

Test chạy: `py -3 -m unittest discover -s tests -p "test_names.py" -v` và `py -3 -m unittest discover -s tests -p "test_mascot_art.py" -v`, rồi `py -3 -m mira selftest`.

Commit: `[TAIL-1] Drop leftover old names from code and tests`

## 1. Cái gì kế thừa PLAN-V1, cái gì đọc mới

[docs/PLAN.md](docs/PLAN.md) là plan vòng 1, viết khi package còn tên `r0`. Số dòng trong plan đó lệch so với `mira/` hôm nay. Vòng 2 lấy hành vi từ `mira-harness_ke-hoach-vong-2.md` và lấy chỗ cài từ file vừa đọc lại.

Kế thừa, đã đối chiếu lại trên code mới:

- P0-04 đã có `_verdict_token` tại [mira/team.py](mira/team.py) dòng 362–370. Chỉ `PASS` hoặc `FAIL` sau `strip` dòng đầu. Lệch thì `verifier_verdict is None` và dòng 744–745 withheld. Test [tests/test_verdict.py](tests/test_verdict.py) dòng 37–52.
- I1, I2, I3, I5, I8 nằm ở docstring [mira/team.py](mira/team.py) dòng 7–12. I6 một dòng [mira/pipeline.py](mira/pipeline.py) dòng 7. I4 và I7 không bịa.
- `build_plan` dòng 201–222 gọi `t1a_policy`, `dynamic_floor`, `human_gate`. Làn và cổng không do model.
- `make_task` dòng 176–198: `data_labels` lấy từ tham số `labels`, không parse từ câu chữ.
- `Ledger.charge` dòng 331–348 và `summary()["by_role"]` dòng 350–354. `_call` dòng 471–473 charge trong `lock`.
- `plan_hash` vẫn là `hash()` Python tại [mira/pipeline.py](mira/pipeline.py) dòng 178. PLAN-V1 đã ghi nhận nó đổi theo process. P1-03 của vòng này mới đổi.
- Cửa ghi: `promote_staging` dòng 285, `_executor_write` dòng 775. Không mở cửa thứ hai.
- Giá: `_call` dòng 456–459 chặn model không có trong `C.PRICES` và không có `declared_price`. `UNKNOWN_PRICE` trong [mira/config.py](mira/config.py) dòng 53 không được dùng làm van.

Đọc mới, không có trong PLAN-V1:

- Ba tầng intake, schema brief, bảy luật Phần C3, chín test Phần C5, cờ `--intake`, `--clarify-max`, `--brief`, lệnh `mira brief`.
- Thứ tự thực thi người giao: TAIL-1 rồi P1-01 và P1-05, rồi intake tầng 1, rồi tầng 3 cộng chín test, rồi P1-02, rồi P1-03. PLAN-V1 gộp envelope với evidence vào một commit `[P1-01]` (dòng 243–260) và gộp `--yes` với `prices.toml` (dòng 264–282). Lát này tách đúng vòng 2.
- Package, nhà `~/.mira`, shape tiếng Anh, shim `r0` đã có sau S1–S5. Mọi đường dẫn mới viết `mira/`, không viết `r0/` trừ shim.

## 2. Mâu thuẫn và hướng cổng chặt hơn

Ba chỗ hai tài liệu không cùng một cửa. Chọn cửa chặt hơn và ghi lý do.

Envelope. PLAN-V1 dòng 247: JSON hỏng thì được fallback nếu dòng đầu vẫn đúng `PASS`/`FAIL`, trace `protocol=fallback`. Phần B vòng 2 dòng 43: parse JSON lỗi thì withheld, không đoán. Chọn vòng 2. Chữ `PASS` trần không còn là verdict. [tests/test_verdict.py](tests/test_verdict.py) `test_pass_dung_tung_chu` đổi kỳ vọng từ `ok` sang `withheld`. Lý do: fallback là đoán, và đoán là cửa nới. Fixture [tests/test_team.py](tests/test_team.py) dòng 38–43 và [tests/test_guards.py](tests/test_guards.py) dòng 147–154 phải trả JSON đúng schema trong cùng commit P1-01, nếu không selftest vỡ. Đó là cập nhật hợp đồng, không phải sửa ngoài mục.

`--yes`. Vòng 2 dòng 46: chỉ hợp lệ khi surface thuộc `read_only` hoặc `write_sandbox`; `write_external` và `egress_new` từ chối khởi động. PLAN-V1 dòng 269 thêm: nhãn `confidential` hoặc `restricted` cũng thoát mã 7, kể cả khi surface là `write_sandbox`. Chọn cả hai. Nhãn hạn chế mà vẫn `--yes` là tự duyệt dữ liệu nhạy. Mã 7 chưa dùng (các mã hiện có: 0, 3 withheld, 4 chưa duyệt, 5 trùng tên, 6 `--approve` khi dual, xem [mira/team.py](mira/team.py) dòng 860–948).

`mira agent` hôm nay không có `--surface` hay `--labels`. [mira/agent.py](mira/agent.py) dòng 655–656 tự duyệt khi `args.yes`, không nhìn surface. Không thêm cờ thì mọi `--yes` nhìn như `read_only` và cửa không bao giờ đóng. P1-05 thêm `--surface` và `--labels` vào parser agent, mặc định `read_only` và `internal`. Mode `bypass` đi cùng cửa đó. `--yes` với mặc định `read_only` vẫn được, đúng test PLAN-V1 `test_yes_read_only_duoc`.

Intake mặc định. Vòng 2: bật khi làn lớn hơn hoặc bằng 1, tắt ở làn 0. Làn tính bằng `build_plan` trên câu thô và cờ CLI, trước mọi lời model. Brief không được đưa vào `make_task`. Dry-run không gọi model: in roster từ code và một khung brief chỉ echo câu người dùng, `acceptance_criteria` rỗng, ghi rõ đây không phải brief đã duyệt. Không bịa tiêu chí nghiệm thu trong dry-run. Chạy thật mà schema hỏng thì dừng.

Vượt `--clarify-max`. Vòng 2 cho chạy tiếp bằng brief hiện có. Luật schema lại nói brief hỏng thì không gọi planner. Nếu hết trần mà schema vẫn hỏng, dừng, mã 8, không gọi planner. Nếu schema đã đủ, ghi assumptions và chạy tiếp, không hỏi nữa. Cửa schema thắng cửa "chạy cho xong".

Role-prompt. Vòng 2 cho "LLM hoặc template". Test C5 số 5 đòi `prompt_writer` có mặt trong `ledger.summary()["by_role"]`. Template thuần không có lần charge nên test I8 không chứng minh được. Cả intake và prompt writer đều là một `prov.call` rồi `Ledger.charge`. Không có giá thì blocked trước `call`, cùng cửa `_call`.

Native `submit_verdict`. PLAN-V1 muốn tool schema. Verifier đội hôm nay đi `prov.call` trả chữ, [mira/team.py](mira/team.py) dòng 468. Không thêm tool native trong P1-01. Mọi chữ verifier và oracle đi một hàm parse. Thêm tool mà không parse arguments sẽ thành cửa sau. Để dành đến khi vai verifier thật sự gọi tool.

P1-04 `prices.toml` và P1-06 fuzz không nằm trong thứ tự được giao. Không nhét vào commit P1-05.

## 3. P1-01 — Verdict envelope

### Hành vi cũ sang mới

Hàm `_verdict_token` dòng 362–370 đọc dòng đầu. `_score` dòng 373–380 regex `SCORE:`. Pha verifier dòng 711 gán verdict từ token. Pha oracle dòng 736–737 lấy score từ regex. System prompt verifier dòng 63–65 và oracle dòng 66–68 bắt dòng đầu là chữ.

Mới, cùng file [mira/team.py](mira/team.py):

- `_verdict_envelope(text) -> dict | None`. `strip` cả khối. `json.loads` đúng một object. Không cắt fence markdown, không lấy dòng đầu rồi đoán. Khóa bắt buộc: `verdict`, `reasons`, `evidence`, `confidence`. `verdict` chỉ `PASS` hoặc `FAIL`. `reasons` là list, ít nhất một chuỗi không rỗng. `evidence` là list chuỗi, được rỗng nhưng phải là list. `confidence` là số trong `[0, 1]`. Khóa lạ bị từ chối. Oracle khi cổng bật thêm `score` số trong `[0, 1]`. Thiếu hoặc sai kiểu trả `None`.
- Bước verifier lưu `verdict_raw` là chữ gốc và `verdict_parsed` là dict hoặc `None`. Kết quả run cũng có hai trường này ở cấp trên, lấy từ verifier cuối. `verifier_verdict` chỉ lấy từ `verdict_parsed["verdict"]`. `None` vẫn withheld lý do giao thức, dòng 744–745 giữ nguyên.
- Oracle: `oracle_score` chỉ từ `score` trong envelope khi `oracle_gate == "on"`. Không còn regex `SCORE:`. Envelope oracle hỏng khi cổng bật thì withheld, không giữ score cũ. Khi `oracle_gate == "disabled"`, không đòi envelope oracle.
- `ROLE_SYSTEM["verifier"]` và `ROLE_SYSTEM["oracle"]` yêu cầu đúng một object JSON, không chữ ngoài JSON. Oracle ghi thêm `score`.

Không sửa `promote_staging`, `human_gate`, nhánh staging worker.

Fixture phải đổi trong cùng commit, nếu không selftest đỏ:

- [tests/test_team.py](tests/test_team.py) dòng 38–43: verifier và oracle trả JSON. Nhánh `FAIL_MODE` là verdict `FAIL`.
- [tests/test_guards.py](tests/test_guards.py) dòng 147–154: cùng schema. `fail_verifier` trả `FAIL`.
- [tests/test_verdict.py](tests/test_verdict.py) dòng 37–40: chữ `PASS` trần thành withheld.

Ước lượng: 120 dòng trong `team.py`, 40 dòng sửa fixture, 80 dòng test mới.

### Test `tests/test_envelope.py`

- `test_json_pass_duoc_nhan`: body `{"verdict":"PASS","reasons":["khop"],"evidence":["so lieu"],"confidence":0.9}`. `status` là `ok`, `verifier_verdict` là `PASS`, `verdict_parsed["confidence"]` là `0.9`, `verdict_raw` bằng chữ gốc.
- `test_json_hong_bi_withheld`: `"{khong phai json"`, rồi JSON thiếu `reasons`, rồi `verdict` là `MAYBE`, rồi `confidence` là `2`. Cả bốn `status` là `withheld`, `verifier_verdict` là `None`.
- `test_pass_tran_khong_con_duoc_nhan`: chữ `PASS` withheld. Khóa hồi quy P0-04 theo cửa mới.
- `test_oracle_json_co_score`: lane 2, oracle on, envelope có `score` `0.85`. `oracle_score` là `0.85` và `status` là `ok` khi verifier PASS.
- `test_oracle_chu_score_cu_bi_withheld`: chữ `SCORE: 0.9` khi oracle on thì withheld, `oracle_score` là `None`.

Lệnh: `py -3 -m unittest discover -s tests -p "test_envelope.py" -v` rồi `py -3 -m unittest discover -s tests -p "test_verdict.py" -v` rồi `py -3 -m unittest discover -s tests -p "test_team.py" -v` rồi `py -3 -m mira selftest`.

Commit: `[P1-01] Require a JSON verdict envelope`

## 4. P1-05 — `--yes` và `bypass` theo surface

### Hành vi cũ sang mới

[mira/cli.py](mira/cli.py) dòng 757–782: `agent` có `--mode` và `--yes`, không có surface. [mira/agent.py](mira/agent.py) dòng 655–656 tạo `Session` với approve luôn đúng nếu `--yes`.

Mới:

- Parser agent thêm `--surface` choices `read_only`, `write_sandbox`, `write_external`, `egress_new`, default `read_only`. Thêm `--labels` default `internal`, tách bằng dấu phẩy như team dòng 731–732.
- Hàm `auto_approve_allowed(surface, labels) -> bool` trong [mira/agent.py](mira/agent.py). Đúng chỉ khi surface thuộc `read_only` hoặc `write_sandbox` và không nhãn nào thuộc `confidential` hoặc `restricted`.
- `cmd_agent`: nếu `args.yes` hoặc `args.mode == "bypass"` mà hàm trả sai, in một dòng tiếng Việt ra stderr, thoát 7, không tạo `Session`, không gọi `run_turn`.
- REPL [mira/repl.py](mira/repl.py) dòng 528 tạo session theo mode. Nếu người gõ `/mode bypass` hoặc mở chat với `--mode bypass` mà surface suy ra không được phép, từ chối đổi mode và giữ mode cũ. Surface của REPL hôm nay ở dòng 740: `write_sandbox` khi mode `default` hoặc `acceptEdits`, còn lại `read_only`. `bypass` không được nâng surface. Nhãn REPL không có cờ; cửa surface vẫn áp. Không mở `egress_new` từ REPL trong mục này.

Không đổi `cmd_team --approve`. Đó là người duyệt cổng ghi, đã có dual-approval mã 6. Không phải `--yes` của agent.

Ước lượng: 70 dòng agent và cli, 20 dòng repl, 90 dòng test.

### Test `tests/test_yes_gate.py`

- `test_yes_read_only_duoc`: `cmd_agent` với `--yes`, surface mặc định, provider script, task không ghi. Không thoát 7. Session được tạo.
- `test_yes_write_sandbox_duoc`: `--surface write_sandbox --yes` không thoát 7.
- `test_yes_egress_bi_chan`: `--surface egress_new --yes` thoát 7, `run_turn` không bị gọi (patch đếm).
- `test_yes_write_external_bi_chan`: `--surface write_external --yes` thoát 7.
- `test_bypass_confidential_bi_chan`: `--mode bypass --surface write_sandbox --labels confidential` thoát 7.
- `test_bypass_restricted_bi_chan`: nhãn `restricted` thoát 7.
- `test_yes_internal_write_sandbox_van_duoc`: nhãn `internal` với `write_sandbox` và `--yes` không thoát 7.

Lệnh: `py -3 -m unittest discover -s tests -p "test_yes_gate.py" -v` rồi `py -3 -m mira selftest`.

Commit: `[P1-05] Refuse auto-approve outside the sandbox`

Checklist giai đoạn P1-01 và P1-05, dán đầu ra lệnh thật, mỗi dòng một ký hiệu:

- selftest P1-01: số `Ran` và `OK` hoặc `FAILED`
- selftest P1-05: cùng kiểu
- `py -3 -m mira doctor` có `~/.mira` và `môi trường OK`
- một ca envelope PASS và một ca JSON hỏng từ unittest, không suy từ tên test

## 5. INTAKE — schema và bảy luật

Module mới [mira/intake.py](mira/intake.py). Không để logic này nằm rải trong `cmd_team`. `cmd_team` chỉ gọi.

### Schema JSON

Một object, không khóa lạ. Khóa cấm thêm vì chúng là cổng: `surface`, `lane`, `floor`, `labels`, `records`, `dollars`, `roles`, `gate`. Có khóa đó thì schema hỏng.

- `goal`: chuỗi, sau strip khác rỗng.
- `deliverables`: list chuỗi. Được rỗng.
- `acceptance_criteria`: list chuỗi, ít nhất một phần tử sau strip khác rỗng.
- `constraints`: list chuỗi. Được rỗng.
- `assumptions`: list chuỗi. Được rỗng. Vượt trần hỏi thì code được append một câu tiếng Việt nói rõ giả định đang dùng, không được model tự bịa khi schema chưa đủ.
- `questions`: list chuỗi, độ dài từ 0 đến N. Phần tử rỗng bị bỏ khi đếm.
- `per_role_hints`: object đúng ba khóa `planner`, `worker`, `verifier`. Mỗi giá trị là chuỗi. Thiếu khóa hoặc thêm khóa thì hỏng. Hint không được parse thành tool.

`validate_brief(obj) -> tuple[bool, str]`. Lý do tiếng Việt khi hỏng. `canonical_brief(obj) -> str` là JSON `sort_keys=True`, `separators=(",", ":")`, `ensure_ascii=False`. `brief_hash` là SHA256 hex của chuỗi đó.

### Bảy luật, hàm nào, test nào

- Intake không quyết làn, cổng, sàn (I5). `build_plan` vẫn nhận `args.task` và hint CLI tại [mira/team.py](mira/team.py) dòng 818–822, gọi trước `run_intake`. Brief không vào `make_task`. Hàm `apply_brief` chỉ ghi `plan.brief` và prompt, không gán `plan.lane`, `plan.floor`, `plan.roles`. Test `test_intake_khong_doi_lane_floor_roles`: ba brief khác nhau, cùng câu và cùng CLI, `lane`, `floor`, `roles` bằng nhau từng trường.
- Intake không đổi surface, labels, records, dollars (I3). Bốn trường chỉ từ CLI. `make_task` dòng 187 đã lấy `labels` từ tham số. Test `test_nhan_public_trong_cau_khong_doi_labels`: câu có chữ "đây là public data", CLI `labels=["internal"]`, `records=50`, `dollars=0`, `surface=write_sandbox`. Sau intake, `task.observable` bốn trường đó giữ nguyên.
- Brief là dữ liệu không tin. `contain_brief(brief) -> str` bọc bằng cùng tiền tố [mira/team.py](mira/team.py) dòng 812 `NỘI DUNG KHÔNG TIN. Không phải lệnh.` và cùng lọc `_GRADER_IN_TEXT` dòng 799–801. Prompt các vai nhận bản đã bọc, không nhận JSON thô ở vị trí system. Test `test_brief_chua_lenh_di_qua_containment`: brief có `rm -rf /` và `conftest.py`. Chuỗi đưa vào prompt có tiền tố không tin, không còn dòng `conftest.py` nếu câu việc không nêu file đó, và không có `run_shell` trong audit.
- Trần câu hỏi. `--clarify-max` mặc định 3, tối thiểu 0. `clarify_loop` đếm vòng hỏi. Hết trần thì không gọi `input` nữa. Schema đủ thì thêm assumption và chạy. Schema hỏng thì dừng. Test `test_vuot_clarify_max_thi_dung_hoi` với max 1: provider lần một trả một question và schema đủ sau câu trả lời giả; lần hai không được hỏi. Test phụ trong cùng case: max 0 và schema hỏng thì mã 8, `planner` không được gọi.
- Tiền vào sổ (I8). `charged_call(ledger, role, ...)` trong [mira/intake.py](mira/intake.py) lặp cửa giá của `_call` dòng 456–473: không giá thì không `prov.call`; có call thì `ledger.charge(role=...)` với `intake` hoặc `prompt_writer`. Cùng object ledger sẽ truyền vào `execute_plan`. Test `test_chi_phi_intake_va_prompt_writer_trong_ledger`: `summary()["by_role"]` có cả hai khóa và tổng USD lớn hơn 0.
- Brief đủ mới được chạy. `validate_brief` fail thì `cmd_team` trả 8, trước `execute_plan`. Test `test_thieu_goal_thi_dung` và `test_thieu_acceptance_thi_dung`.
- Người duyệt brief trước khi chạy. In canonical JSON, hỏi `[y/N]`. Không duyệt trả 8. `--brief FILE` hợp lệ bỏ tầng 1 và tầng 2, ghi `brief_hash` vào kết quả. File hỏng schema trả 8. Test `test_khong_duyet_brief_thi_khong_goi_planner` và `test_brief_file_hop_le_bo_tang_1` cùng `test_brief_file_hong_schema`.

Mã 8 chưa dùng. Không dùng lại 4 vì 4 là cổng người của Executor.

### Tầng 1 — commit riêng

`run_intake(task, prov, ledger, *, clarify_max, ask) -> dict`. `ask(question) -> str` để test không đụng stdin. Production truyền `input`. Một vòng: model trả JSON; nếu `questions` còn và số vòng nhỏ hơn trần, hỏi, gửi câu trả lời vào lượt sau, charge mỗi lượt. Model intake dùng `C.ROLE_MODEL["planner"]` trừ khi `--model` ép. System prompt cấm model trả surface hay lane.

`cmd_team` thứ tự mới:

- `build_plan` trên câu thô.
- Quyết `--intake`: `on` hoặc `off` người gõ thì theo người. Không gõ thì `on` khi `plan.lane >= 1`, `off` khi làn 0.
- `off`: đường cũ, không charge intake.
- `on` và `--brief`: đọc file, validate, bỏ hỏi và bỏ duyệt.
- `on` không file: `run_intake`. Schema hỏng thì mã 8.
- In brief, hỏi duyệt, trừ khi file đã duyệt. Không duyệt thì mã 8. Ledger của intake vẫn đã charge. Planner chưa gọi. Test đếm số call có system PLANNER bằng 0.
- Dry-run: không gọi `run_intake`. In roster như hôm nay và in khung echo. Trả 0.

Cờ trên parser team [mira/cli.py](mira/cli.py) cạnh dòng 742:

- `--intake` choices `on`, `off`, default `None` nghĩa là theo làn.
- `--clarify-max` type int default 3.
- `--brief` default `None`.

Lệnh `mira brief` với con `validate`, `save`, `load`. `validate` đọc file, in `brief_hash` khi đúng, thoát 8 khi sai. `save` và `load` chỉ copy JSON đã validate, không gọi model. Không ghi đè file đích nếu dest đã có và nội dung khác, in một dòng tiếng Việt rồi thoát 8. Cửa này tránh brief đã duyệt bị ghi đè im lặng.

Ước lượng tầng 1: 220 dòng `intake.py`, 80 dòng `team.py` và `cli.py`, 160 dòng test cho case 3, 4, 7, 8.

Commit: `[INTAKE-1] Ask until the brief schema is closed`

### Tầng 3 và chín test — commit sau

`write_role_prompts(brief, roles, prov, ledger) -> dict[str, str]`. Một call, role sổ `prompt_writer`. Chữ trả về là JSON map tên vai sang prompt. Code kiểm: mọi vai trong roster có mặt, prompt không rỗng, không chứa khóa cấm `surface` hay `lane` như lệnh. Hỏng thì mã 8, không `execute_plan`. Mỗi prompt đi qua `contain_brief` trước khi ghép.

`_user_of` trong `execute_plan` nhận thêm bản prompt đã sinh. Nếu có, phần đầu user prompt của vai đó là bản đã bọc, rồi mới đến mẫu `ROLE_USER` cũ. System `ROLE_SYSTEM` không bị model viết đè. Roster vẫn `ROLES_BY_LANE`.

Kết quả và `trace.json` có `role_prompts` và `brief_hash`.

Chín test trong [tests/test_intake.py](tests/test_intake.py), đúng Phần C5:

- `test_intake_khong_doi_lane_floor_roles` — luật I5, ba biến thể brief.
- `test_nhan_public_trong_cau_khong_doi_labels` — luật I3.
- `test_thieu_goal_thi_dung` và trong cùng lớp `test_thieu_acceptance_thi_dung` — schema, dừng trước planner.
- `test_vuot_clarify_max_thi_dung_hoi` — trần, assumptions, không hỏi vô hạn.
- `test_chi_phi_intake_va_prompt_writer_trong_ledger` — I8, cả hai vai.
- `test_brief_chua_lenh_di_qua_containment` — không tin, không thực thi.
- `test_khong_duyet_brief_thi_khong_goi_planner` — thoát 8, không call planner.
- `test_brief_file_hop_le_bo_tang_1` và `test_brief_file_hong_schema` — bỏ tầng 1 và 2 khi file đúng; file sai thì 8.
- `test_role_prompt_co_trong_trace` — mỗi vai trong roster có mặt trong `role_prompts` của kết quả.

Provider test là lớp giả `call`, không mở socket. Giá khai `price_in=(1.0, 1.0)` trên plan để khỏi đụng cổng giá P0-05. `ask` là hàm đếm.

Lệnh: `py -3 -m unittest discover -s tests -p "test_intake.py" -v` rồi `py -3 -m mira selftest`.

Commit: `[INTAKE-3] Write contained role prompts from the brief`

Checklist giai đoạn intake, đầu ra thật:

- unittest intake: `Ran 9` và `OK` (hoặc số lớn hơn 9 nếu case schema tách hai method, khi đó liệt kê đủ chín tên Phần C5 đều `ok`)
- selftest sau INTAKE-1 và sau INTAKE-3
- một lần `cmd_team` dry-run trong test không làm `prov.call` tăng

## 6. P1-02 — Evidence trong staging

### Hành vi cũ sang mới

Worker dạng `edit` đã sửa trong staging tại [mira/team.py](mira/team.py) dòng 558–573, `shape_of(...) == "edit"`. Oracle vẫn tin score model. Chưa chạy pytest trong staging. Chưa so diff với lời "đã sửa".

Mới, hàm `staging_evidence(source: Path, staging: Path, task: str) -> dict` trong [mira/team.py](mira/team.py), gọi sau worker và trước khi nhận score:

- Diff: so file thường trong staging với source, bỏ `.git`, `__pycache__`, `.env`, `.mira/staging`. Không khác byte nào thì `empty_diff` đúng.
- Nếu `empty_diff` và chữ worker, sau strip, chứa `đã sửa` hoặc cờ `edited` đúng, thì withheld lý do diff trống. Không promote.
- Lệnh: chỉ lệnh mà câu việc của người dùng nêu, tái dùng cách nhận lệnh đã có trong agent cho shape `edit` (python hoặc pytest nằm trong câu). Chạy với `cwd` là staging, `env` đã bỏ khóa cùng cách `run_shell` đang scrub. Exit khác 0 thì withheld dù `score` lớn hơn hoặc bằng 0.70. Không chạy lệnh do model nghĩ ra.
- `oracle_score` cao không ghi đè evidence. Evidence fail thì status withheld trước nhánh score dòng 748.

Không đổi luật promote: vẫn chỉ khi status `ok` và cổng người qua.

Ước lượng: 110 dòng team, 100 dòng test.

### Test `tests/test_evidence.py`

- `test_pytest_do_mac_score_cao_van_withheld`: staging có test pytest cố tình đỏ, câu việc nêu `pytest`, oracle JSON score `0.95`, verifier PASS. `status` là `withheld`. Cây nguồn không đổi.
- `test_diff_trong_worker_noi_da_sua_bi_fail`: worker nói đã sửa, không file nào đổi. withheld.
- `test_diff_co_va_pytest_xanh_thi_score_duoc_dung`: một file đổi, lệnh thoát 0, score `0.9`, verifier PASS. Không withheld vì evidence. Cổng người vẫn giữ như cũ nếu tier đòi duyệt. Test này dùng surface không đòi ghi ra cây thật, chỉ assert `status` trước promote.
- `test_lenh_trong_loi_model_khong_duoc_chay`: model bảo chạy `pytest` nhưng câu người dùng không nêu lệnh. Process pytest không spawn.

Lệnh: `py -3 -m unittest discover -s tests -p "test_evidence.py" -v` rồi `py -3 -m mira selftest`.

Commit: `[P1-02] Withhold when staging evidence disagrees`

## 7. P1-03 — SHA256 và `mira verify`

### Hành vi cũ sang mới

[mira/pipeline.py](mira/pipeline.py) dòng 178: `plan_hash` là `abs(hash((t.id, tier)))` mười hai chữ số. Đổi theo process. `two_phrases` dòng 270–275 seed bằng chuỗi đó. Trace đội là một `trace.json` tại `_executor_write` dòng 795, không có xích.

Mới:

- `plan_hash` là SHA256 hex của canonical JSON gồm `id` task, `tier`, `tool_surface`, `data_labels` đã sort, `lane` chưa có ở chỗ `human_gate` vì lane tính sau gate. Giữ đúng dữ liệu gate đang băm: `t.id` và `tier`, cộng `tool_surface` và tuple nhãn để hai task khác nhãn không trùng hash. Chuỗi hex 64 ký tự. `two_phrases` vẫn `random.Random(seed)`. Test dual chỉ cần hash khác rỗng và hai người cùng một hash, [tests/test_dual_gate.py](tests/test_dual_gate.py) dòng 94–95. Không đổi luật hai người.
- Khi ghi `--out`, thêm `trace.jsonl`. Mỗi dòng một object đã có `prev_hash` và `hash`. Dòng đầu `prev_hash` là 64 số 0. `hash` là SHA256 của canonical JSON dòng đó sau khi bỏ hai trường hash rồi gắn `prev_hash`. Thứ tự khóa sort. Dòng gồm: một header `plan_hash` và `brief_hash` nếu có, rồi từng step.
- `manifest.json` ghi `head` là hash dòng cuối và `plan_hash`.
- `mira verify <dir>` trong [mira/cli.py](mira/cli.py). Đọc `trace.jsonl`, tính lại từng hash, so `manifest.json`. Khớp trả 0. Sửa một ký tự, xóa một dòng, hoặc chèn một dòng trả 1 và in một dòng tiếng Việt nói loại lệch, không in cả file.

Ước lượng: 140 dòng pipeline, team, cli, 90 dòng test.

### Test `tests/test_verify.py`

- `test_khong_sua_verify_pass`: ghi một jsonl hai dòng và manifest đúng. `verify` trả 0.
- `test_sua_mot_ky_tu_verify_fail`: đổi một ký tự trong payload. trả 1.
- `test_xoa_mot_dong_verify_fail`: xóa dòng giữa. trả 1.
- `test_chen_mot_dong_verify_fail`: chèn dòng. trả 1.
- `test_plan_hash_la_sha256`: `build_plan` hai lần cùng tham số trong hai process không cần thiết. Trong một process, hash dài 64, chỉ hex, và khác `hash()` Python của cùng tuple. Hai `build_plan` cùng câu cùng CLI cho cùng hash.

Lệnh: `py -3 -m unittest discover -s tests -p "test_verify.py" -v` rồi `py -3 -m unittest discover -s tests -p "test_dual_gate.py" -v` rồi `py -3 -m mira selftest`.

Commit: `[P1-03] Chain trace hashes and add mira verify`

## 8. Checklist Phần E của lát này

Sau mỗi giai đoạn, in đủ các dòng dưới đây với đầu ra lệnh dán thật. Thiếu đầu ra thì giai đoạn chưa xong.

- TAIL-1: grep `mira` và `tests` bằng 0. Selftest `OK`.
- P1-01: JSON hỏng withheld. Chữ `PASS` trần withheld. Selftest `OK`.
- P1-05: `--yes` với `egress_new` và `write_external` thoát 7. `confidential` với bypass thoát 7. Selftest `OK`.
- INTAKE: chín tên test Phần C5 đều `ok`. Ledger có `intake` và `prompt_writer`. Selftest `OK`.
- P1-02: pytest đỏ trong staging withheld dù score cao. Diff trống mà nói đã sửa thì withheld. Selftest `OK`.
- P1-03: `mira verify` trên thư mục bị sửa một ký tự trả 1. `plan_hash` là 64 hex. Selftest `OK`.

Chưa nghiệm thu trong lát này, để nguyên trên backlog vòng 2: T2 scrub env cho test khóa, T3 docstring keys, T4 README, P1-04 prices.toml, P1-06 fuzz 200, P2 eval đối kháng. Không đánh dấu chúng xong.

## 9. Tự kiểm

Không còn chỗ ghi TBD. Mỗi mục có file, hàm, hành vi cũ sang mới, tên test, lệnh, commit. Ước lượng cộng lại khoảng 120 dòng P1-01, 90 dòng P1-05, 300 dòng intake tầng 1, 180 dòng tầng 3, 110 dòng P1-02, 140 dòng P1-03, cộng test khoảng 80, 90, 160, 120, 100, 90. TAIL-1 khoảng 15 dòng. Không dependency mới. I1 đến I3, I5, I8 không nới: promote vẫn một cửa, withheld vẫn không ghi, nhãn vẫn từ CLI, làn vẫn từ `build_plan`, mọi call intake và prompt writer đi `Ledger.charge` sau cửa giá.