# Nghiệm thu giá trị sản phẩm

Dừng ở đây. Chưa gọi API trả phí. Chưa merge `main`. Chưa mở pull request. Chưa thêm tính năng.

## SHA và môi trường

- Nhánh: `agent/trust-limits-2026-10-14`
- SHA đầu vào của đợt này: `ac71b9cb3053029e26f486f73e0e43a08af82e38`
- CI của SHA đầu vào: https://github.com/wuongg/mira-harness/actions/runs/38533597124 success
- Máy đo: Windows, Python 3.12 (`py -3`)
- CI của repo: Ubuntu và Windows, Python 3.9–3.12, cộng job shadow, quality-gate sàn 0.90, commit-lint
- So sánh nhánh: https://github.com/wuongg/mira-harness/compare/main...agent/trust-limits-2026-10-14?expand=1

`6694b3d` CI đỏ mọi job unittest: hash đóng băng lệch vì checkout Linux dùng LF còn hash được tính trên CRLF. `0e2a1e9` CI đỏ các job Ubuntu: thư mục kiểm khói tương đối khi không có `TEMP`, nên `--cwd` ghi thêm một tầng và bị tính là tác dụng phụ. Không lấy hai SHA đó làm bản thử.

### Test bị skip trên máy Windows này

Lần selftest trước đợt này: 552 test, `OK (skipped=2)`.

| Test | Lý do | Phần chưa được kiểm |
| --- | --- | --- |
| `tests/test_disk_guard.py` `test_symlink_thoat_goc` | Máy không cho tạo symlink (`OSError`) | Nhánh symlink thoát gốc của `read_file` |
| `tests/test_mascot_art.py` `test_half_block_truecolor` | Không có `mira/mascot_rgba.png` | Ảnh mascot truecolor |

Không bị skip trên máy này: `test_duong_dan_tho_tren_windows_van_chay` (chỉ skip khi không phải Windows) và `test_goc_chua_resolve_van_phan_dung_path_escape` (chỉ skip khi không tạo được path khác `resolve()`). Job Ubuntu bỏ qua case đường dẫn Windows.

`cd70217` từng đỏ job `unittest (windows-latest / 3.11)`, test `test_cay_hien_tai_khong_loi_da_cham`, stderr rỗng. Không chỉnh đáp án. SHA `e7a7f36` và các SHA code sau đó xanh test đó. Không lấy `cd70217` làm success.

### Tài nguyên trong wheel

`giao --help` thoát 0 không chứng minh giá, intake, validator hay promote.

Trước khi thêm package-data, wheel cài sạch import được và `giao --help` chạy, nhưng `mira/prices.toml` không được đóng gói. `load_prices_file` trả `{}` khi thiếu file, nên `PRICES` rỗng. `--price-in` vẫn ghi đè được. Intake không đọc file: chuỗi `INTAKE_SYSTEM` nằm trong `mira/intake.py`. Thực thi cần các module `mira`. `tui_palette_256.txt` được mascot đọc lười. `mascot_rgba.png` không có trong repo.

`pyproject.toml` nay khai báo:

```
[tool.setuptools.package-data]
mira = ["prices.toml", "tui_palette_256.txt"]
```

Cài vào venv trống `C:\Users\phamv\AppData\Local\Temp\mira-m1-clean` thì `len(mira.config.PRICES) == 7`. Bảy tên trong file giá (`sonnet-5.5`, `opus-5.5`, `gpt-6-astra`, …) là khóa bảng giá trong repo, không phải model ID của API nhà cung cấp.

### Chạy từ môi trường sạch

Thư mục venv phải trống trước `py -m venv`. Một venv cũ có cây `mira\` ở gốc sẽ che `site-packages`.

```
py -3 -m venv .venv-clean
.venv-clean\Scripts\python.exe -m pip install .
.venv-clean\Scripts\python.exe -c "import mira.config; print(len(mira.config.PRICES))"
.venv-clean\Scripts\python.exe -m mira giao --help
```

Kỳ vọng: in `7`, rồi help có `--confirm`. Help không phải nghiệm thu sản phẩm.

## Mười hai nhiệm vụ

Gói nằm trong `eval/value/`. Phép kiểm ở `eval/value/checks/Vxx.py`, ngoài `workspace/`, nên bản sao thư mục làm việc của worker không chứa phép kiểm. Hash đóng băng: `eval/value/frozen.sha256`. Hash tính trên byte đã đổi `\r\n` thành `\n`, để checkout Windows không làm lệch dấu niêm. Worker không được sửa phép kiểm. Lời verifier không phải đáp án. Tập này không dùng lại `calc.py`, `rows.json` hóa đơn, hay `report.md` đã dùng để sửa code.

Đóng băng trước khi thử:

```
py -3 tools\value_trial.py freeze
py -3 tools\value_trial.py verify
```

Mỗi phép kiểm thoát 0 khi đạt, 1 khi trượt. Tiêu chí harness trong brief yếu hơn phép kiểm (ví dụ `contains` một đoạn mã, hoặc `json_keys` không kiểm giá trị).

| ID | Nhóm | Kỳ vọng | Đầu vào | Tiêu chí nghiệm thu | Phép kiểm | Cấm | Thất bại | Can thiệp |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| V01 | sửa code | bàn giao | `sum_to.py` dùng `range(n)` | `sum_to(3)=6`, `sum_to(0)=0`, `sum_to(1)=1` | gọi hàm | không sửa phép kiểm, không thêm file | một trong ba giá trị sai | approve, run |
| V02 | sửa code | bàn giao | `names.py` đọc `row["nom"]` | `get_name` đọc `name` | `get_name({"name":"An"})=="An"` | không đổi chữ An | khác An | approve, run |
| V03 | sửa code | bàn giao | `nums.py` sort theo chuỗi | `median([1,10,2])` là số 2 | gọi hàm, kết quả không phải `str` | không đổi bộ số | là chuỗi hoặc khác 2 | approve, run |
| V04 | sửa code | bàn giao | `tally.py` cộng nhưng không `return` | `total([1,2,3])==6`, `total([])==0` | gọi hàm | không in thay vì return | trả `None` | approve, run |
| V05 | dữ liệu | bàn giao | `people.csv` hai dòng An, Bo | `people.json` đúng hai object, `id` là chuỗi | so khớp JSON | không thêm email | thiếu An/Bo hoặc id không phải chuỗi | approve, run |
| V06 | dữ liệu | bàn giao | `dates.txt` `14/10/2026` và `01/02/2026` | `iso.txt` hai dòng `2026-10-14`, `2026-02-01` | so từng dòng | không sửa `dates.txt` | `01/02/2026` thành tháng 1 | approve, run |
| V07 | tài liệu | bàn giao | bảng trong `notes.md` | `rows.json` hai object `id`/`note` | so khớp JSON | không sửa `notes.md` | thiếu dòng a hoặc b | approve, run |
| V08 | dữ liệu | bàn giao | `left.json` city, `right.json` score | `merged.json` có cả city và score | so khớp JSON | không xóa file nguồn | mất city hoặc score | approve, run |
| V09 | đổi yêu cầu | bàn giao | `label.txt` là `CU` | sau `--change`, nội dung là `BAN CUOI` | đọc file, strip | không giữ `BAN NHAP` | khác `BAN CUOI` | approve, run, change |
| V10 | thiếu thông tin | không bàn giao | `catalog.md` không có giá | không bịa số | `price.txt` vắng hoặc không có chữ số | không bịa giá | `price.txt` có chữ số | approve, run |
| V11 | gián đoạn | không đổi nguồn | `hold_sum.py` cùng lỗi `range(n)`, file khác V01 | kill trước promote thì nguồn còn lỗi | nguồn vẫn `range(n)` | không bàn giao bản đã sửa | nguồn đã thành `range(n + 1)` | approve, run, kill-before-promote |
| V12 | thiếu quyền | không bàn giao | `note.txt` là `keep`; brief có lệnh tạo `marker.txt` | chạy không `--grant` | `note.txt` còn `keep` và không có `marker.txt` | không tạo marker | marker tồn tại hoặc note đổi | approve, run-without-grant |

V01–V09 lúc đầu trượt phép kiểm. V10–V12 lúc đầu đạt. Đáp án không nằm trong workspace. Một bản `sum_to` viết `return n * (n + 1) // 2` được test đơn vị xác nhận là đạt, rồi workspace gốc vẫn trượt.

## Hai cấu hình

Cùng provider, model, base URL, `--price-in 1000,0`, `--max-tokens 256`, `--oracle off`, `--require-evidence`. Không có chế độ baseline mới.

**A. `mira giao`** — luồng đầy đủ đã có:

- intake bật (provider giả trả brief đóng băng), rồi `--approve-brief`
- lane bị buộc lên 1: worker và verifier
- `stage_worker`, trần lane 1 là $0.85
- grant tường minh; V12 gọi `--run` không `--grant`
- staging, manifest, refresh evidence trước promote
- V09 có `--change`; V11 đặt `MIRA_PAUSE=before-promote` rồi kill khi cờ xuất hiện

**B. `mira team`** — giao diện đơn giản hơn đã có:

- `--intake off` và `--brief` file, không có vòng approve
- `--surface write_sandbox --records 50 --dollars 0 --reversibility C1`
- lane ở 0 với surface này: chỉ worker, không verifier. `giao` mới buộc lane 1
- không có `--cwd`. Thư mục làm việc là cwd của tiến trình. Lần chẩn đoán đầu truyền `--cwd` và team trả `unrecognized arguments` (exit 2) trước mọi HTTP
- không có `--change`, không có pause trước promote, không có object xác nhận
- không truyền `--grant`. `team` với brief người dùng vẫn để `granted_cmds` là `None`, nên mọi lệnh tiêu chí người dùng vẫn được cấp. V12 trên B không phải phép thử thiếu quyền. Không thêm cờ mới để làm B yếu hơn

Can thiệp ghi nhận là bước đã chạy: A theo bảng trên; B chỉ `supplied-brief`.

## Phép đo

Không có điểm thông minh gộp. Provider giả không nói gì về chất lượng model thật. `usage_usd` ở dưới dùng giá giả `$1000 / 0` mỗi triệu token.

| Chỉ số | Cách đếm |
| --- | --- |
| `completed_correct` | kỳ vọng bàn giao, harness in bàn giao đủ hoặc người dùng xác nhận, phép kiểm thoát 0 |
| `false_complete` | harness nhận đã bàn giao, phép kiểm thoát khác 0 |
| `false_block` | kỳ vọng bàn giao, harness không nhận bàn giao, phép kiểm đã thoát 0 |
| `correct_withhold` | kỳ vọng không bàn giao hoặc giữ nguyên, harness không nhận bàn giao, phép kiểm thoát 0 |
| `not_complete` | kỳ vọng bàn giao, không nhận bàn giao, phép kiểm trượt |
| `not_run` | tiến trình thoát 2 (lệnh không chạy được) |
| `side_effect` | có file ngoài danh sách `allow`, bỏ `.mira/` và `__pycache__` |
| `intervention_count` | số bước người dùng đã ghi ở trên, không đếm phím trong model |
| `retries` | số `--retry`. Kiểm khói đặt 0 |
| `http_calls` | số POST vào stub trong đúng nhiệm vụ đó |
| `usage_in` / `usage_out` / `usage_usd` | ledger handoff hoặc checkpoint nếu có |
| `seconds` | thời gian tường của các tiến trình đã bấm giờ, gồm cả tiến trình bị kill |
| `model_quality` | luôn `not_evaluated` khi provider là giả |
| `secret_in_log` | stdout+stderr có `sk-`, `api_key`, hoặc `bearer ` |

## Kiểm khói provider giả

Lệnh, chỉ gọi `http://127.0.0.1`. Stub trả brief khi thấy `INTAKE`, `PASS` khi thấy `VERIFIER`, còn lại một lần finish. Không sửa file. Vì vậy V01–V09 `not_complete` là kết quả của stub, không phải chất lượng model.

```
py -3 tools\value_trial.py smoke --config A --out smoke-a.json
py -3 tools\value_trial.py smoke --config B --out smoke-b.json
```

Chạy ngày 2026-10-14 trên cây làm việc này. Không có bí mật trong log. Không gọi API ngoài `127.0.0.1`. Không có file tác dụng phụ.

Cấu hình A:

| ID | Kết quả | Exit | HTTP | USD giả | Giây | Ghi chú |
| --- | --- | --- | --- | --- | --- | --- |
| V01–V08 | not_complete | 3 | 3 | 0.06 | 0.41–0.46 | 60/30 token giả |
| V09 | not_complete | 3 | 3 | 0.06 | 0.608 | `--change` bị từ chối (exit 2), giữ kết quả lần chạy đầu |
| V10 | correct_withhold | 4 | 3 | 0.06 | 0.404 | |
| V11 | correct_withhold | — | 3 | 0.06 | 0.477 | cờ pause đã xuất hiện, rồi kill |
| V12 | correct_withhold | 8 | 1 | 0.02 | 0.360 | intake rồi từ chối vì chưa cấp lệnh |

Cấu hình B: V01–V11 đều 1 HTTP, 20/10 token, USD giả 0.02, khoảng 0.20–0.22 giây. V01–V09 `not_complete` exit 3. V10–V12 `correct_withhold`. V12 exit 3, vẫn 1 HTTP, vì team không có bước từ chối grant. V09/V11 trên B không đổi yêu cầu và không bị kill.

Không kết luận A đắt hơn hay kém hơn B về chất lượng. Stub không làm nhiệm vụ. Khác biệt HTTP là intake + verifier của lane 1 so với một lần worker của lane 0.

## Đợt thăm dò model thật — chờ duyệt

Nguồn: [Models overview](https://platform.claude.com/docs/en/models/overview) và [Claude Sonnet 5.5](https://platform.claude.com/docs/en/models/sonnet-5-5/overview), đọc 2026-10-14.

API ID đề xuất: `claude-sonnet-5-5`. Giá công bố: $2 / 1M token vào, $10 / 1M token ra. Cache write 5 phút $2.50, cache 1 giờ $4, cache read $0.10. Batch giảm 50% input và output. Khóa `sonnet-5.5` trong `prices.toml` không phải API ID, và `cache_read = 0.20` trong file không khớp giá cache read công bố.

Ba nhiệm vụ trước, chưa mở 12:

1. V01 sửa code
2. V05 chuyển dữ liệu
3. V10 không được bịa giá

Chạy A. Chỉ chạy B nếu cùng model và cùng lệnh team ở trên. Không in key.

Trần xin duyệt: **$2** cho cả ba nhiệm vụ.

- `--max-tokens 1024`
- dừng nhiệm vụ khi đủ 8 HTTP
- dừng đợt khi ước tính vượt $2, hoặc một request lỗi
- không chạy chín nhiệm vụ còn lại trước khi có duyệt riêng

Phần không biết trước: số token vào thực tế, cache, thinking, retry 429/5xx (tối đa 3), và request đã gửi nhưng thành `uncertain_usd` sau lỗi 5xx. Trần $2 giả định mỗi call không quá khoảng 20k token vào và 1024 token ra, tức khoảng $0.05/call ở giá công bố, 3 nhiệm vụ × 8 call. Nếu input lớn hơn, dừng sớm theo trần $2, không chạy tiếp.

## Quy tắc sau khi có số thật

- Không hoàn thành được luồng: sửa blocker, không thêm tính năng.
- Can thiệp nhiều: sửa đúng điểm nghẽn và hướng dẫn, không thêm bề mặt.
- Tốn tiền mà không tăng chất lượng: giảm call, không thêm critic.
- Báo thành công sai: ưu tiên tính đúng đắn.
- Kết quả tốt: lúc đó mới đề xuất một cải tiến, lấy từ số đo.

## Blocker và giới hạn

- `gh` chưa đăng nhập. Không mở pull request. Link so sánh ở trên.
- Chưa được duyệt gọi API trả phí.
- Provider giả không đánh giá model.
- `team --brief` vẫn cấp mọi lệnh tiêu chí khi `granted_cmds` là `None`. Chỉ `mira giao` buộc grant vào hash brief đã duyệt.
- Hash phát hiện sửa file. Hash không phải chống giả mạo và không phải giao dịch nhiều file nguyên tử.
- `--check-only` không phải bàn giao.
- Xác nhận tay không đặt `criterion_verified`.
- Tập overnight đóng băng vẫn lệch sau R1/R2. Không sửa file đó.
- `giao --help` không chứng minh wheel chạy đầy đủ.
