# PLAN-V6 — WIN-1, P3-01, P3-02, P3-03

Nguồn lệnh là lời giao ngày 2026-10-13 sau khi P2-02, DETECT-1, P2-03, P2-04 đã có bảng eval 6/6 nhóm `1.00/1.00`. HEAD đối chiếu là `6252b4e`. Máy này không chạy được `python3` (alias Microsoft Store, thoát 9009). Lệnh kiểm là `py -3`. Commit bằng Python `Path.write_text(..., encoding="utf-8")` rồi `git commit -F .git/COMMIT_MSG.txt`. Không `Set-Content -Encoding utf8`. Tiêu đề ASCII, không dấu, không BOM, không quá 72 ký tự, khớp `^\[[A-Z0-9-]+\] \S`. Không thêm dependency. Không rewrite lịch sử. Không nới I1, I2, I3, I5, I8. Không bịa I4 hay I7. Không xóa vỏ `r0/`. Không làm P3-04, P4 trong lát này. P3-01 chỉ được commit sau khi đúng 10 job của run WIN-1 xanh: 8 unittest, `quality-gate`, `commit-lint`.

Bước này chỉ ghi plan. Chưa sửa code. Thực thi chỉ sau khi plan được duyệt, theo thứ tự WIN-1 rồi P3-01 rồi P3-02 rồi P3-03.

## 0. Những gì đã đọc được từ CI, và những gì không có trong annotation

Run `6252b4e`: https://github.com/wuongg/mira-harness/actions/runs/38394358448

Job lấy từ API `actions/runs/38394358448/jobs` lúc lập plan:

| job id | tên | kết luận |
| --- | --- | --- |
| 115285683279 | shadow (3.12) | success |
| 115285683522 | quality-gate | success |
| 115285683734 | commit-lint | success |
| 115285683733 | unittest (ubuntu-latest) | success |
| 115285683808 | unittest (ubuntu-latest) | success |
| 115285683912 | unittest (ubuntu-latest) | success |
| 115285684100 | unittest (ubuntu-latest) | success |
| 115285684004 | unittest (windows-latest) | failure |
| 115285684080 | unittest (windows-latest) | failure |
| 115285684203 | unittest (windows-latest) | failure |
| 115285684254 | unittest (windows-latest) | failure |

Workflow `.github/workflows/test.yml` dòng 8–14 đặt tên job là `unittest (${{ matrix.os }})`. Tên không chứa `matrix.python-version`. API trả `labels: ["windows-latest"]` và `output.title` rỗng. Bốn job Windows là bốn ô `3.9`, `3.10`, `3.11`, `3.12` vì ma trận chỉ có bốn phiên bản và cả bốn đều đỏ. Không gán được job id cho từng phiên bản từ API.

Mỗi job Windows có đúng hai annotation, lấy từ `check-runs/<id>/annotations`. Bốn job cùng nội dung. Trích job `115285684004`, hai job còn lại giống từng chữ:

```
warning  .github:2
Node.js 20 is deprecated. The following actions target Node.js 20 but are being forced to run on Node.js 24: actions/checkout@v4, actions/setup-python@v5. For more information see: https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/

failure  .github:1005
Process completed with exit code 1.
```

`raw_details` của cả hai annotation là chuỗi rỗng. `output.summary` và `output.text` của check run cũng rỗng. Bước fail trong API là bước 4, tên `Chạy toàn bộ unittest`. Các bước checkout và setup-python kết thúc success.

Tải log bước đó không được. `GET /repos/wuongg/mira-harness/actions/jobs/115285684004/logs` trả `403` với câu `Must have admin rights to Repository.` URL công khai trong HTML (`data-log-url` của bước 4, `/wuongg/mira-harness/commit/6252b4e3f4ae7f9721f63b2d56910f1d684afc1f/checks/115285684004/logs/4`) trả `404` cả khi gửi cookie của trang job và `Accept: application/json`. Plan này không bịa dòng `FAIL:` hay `AssertionError` vì các dòng đó không nằm trong annotation.

Số dòng `1005` là dòng annotation của câu `Process completed with exit code 1`, tức dòng cuối log, không phải dòng assertion. Run trước đó, `f03c574`, https://github.com/wuongg/mira-harness/actions/runs/38393931473 , bốn job Windows cũng đỏ và annotation failure nằm ở dòng `1004`, cùng câu exit code 1. `6252b4e` thêm một test verbose (`test_pe02_gach_nguoc_bi_chan`) nên log dài thêm một dòng. Suite đã chạy tới cuối rồi trả mã 1. Không phải job chết lúc cài Python.

Đối chiếu ba run, chỉ tính unittest:

| commit | ubuntu unittest | windows unittest | quality-gate |
| --- | --- | --- | --- |
| `12285dd` P2-02 | 4 success | 4 success | failure |
| `f03c574` P2-04 | 4 failure | 4 failure | failure |
| `6252b4e` backslash | 4 success | 4 failure | success |

`12285dd` chứng minh runner Windows chạy được unittest của repo trước cụm DETECT-1 / P2-03 / P2-04. `f03c574` làm đỏ cả Ubuntu lẫn Windows. `6252b4e` đổi `mira/tools.py` `_arg_outside` để `\` thành `/` trước `Path`, và làm Ubuntu cùng quality-gate xanh lại. Windows không xanh lại. Commit backslash không phải thứ làm Windows đỏ lần đầu, và cũng không phải thứ chữa Windows.

Clone sạch `6252b4e` trên máy Windows này, `py -3 -m mira selftest`: `Ran 414 tests in 20.433s`, `OK (skipped=2)`, thoát 0. Lỗi không phải “mọi Windows đều gãy”. Nó nằm ở chỗ runner `windows-latest` khác máy này, hoặc một test chỉ đỏ ở đó. Selftest gọi cùng lệnh CI: `mira/cli.py` dòng 426, `unittest discover -s tests -v`.

Cảnh báo Node.js 20 có trên annotation nhưng checkout và setup-python đều success. Không lấy cảnh báo đó làm nguyên nhân exit 1.

`mira/ui.py` dòng 64–83: import `ui` gọi `_prefer_utf8()`, trên Windows đặt console CP 65001 rồi `reconfigure(encoding="utf-8", errors="replace")`. In trực tiếp `nguồn` khi chưa import `mira` thì `cp1252` strict ném `UnicodeEncodeError` (đã chạy `py -3 -c` trên máy này). Sau khi unittest import `mira`, stdout đã thành utf-8 và `tests/test_ingest.py` in `nguồn dữ liệu: real` vẫn thoát 0 dưới `PYTHONIOENCODING=cp1252`. Không kết luận Windows CI chết vì bảng mã, vì đường import đã đổi encoding, và annotation không chứa `UnicodeEncodeError`.

## traceback thu được

Run WIN-1 `010a70a`: https://github.com/wuongg/mira-harness/actions/runs/38421272831

Bốn job Ubuntu, `quality-gate`, `commit-lint`, `shadow` đều success. Bốn job Windows đều failure. Annotation `::error::` của job `unittest (windows-latest / 3.9)` (các ô 3.10, 3.11, 3.12 cùng chữ):

```
FAIL: test_suite_dong_bang_qua_0_90 (test_quality_gate.QualityGateTest)
AssertionError: Lists differ: ['path_escape: precision dưới 0.90'] != []

FAIL: test_khong_goi_model (test_adversarial.AdversarialTest)
AssertionError: 1 != 0

FAIL: test_bao_cao_co_sau_nhom (test_adversarial.AdversarialTest)
AssertionError: 1 != 0
```

Hai test sau chỉ bắt exit code của `run_adversarial`. Test cổng nêu đúng một chỉ số: precision của `path_escape`, không phải recall, không phải nhóm khác, không có `UnicodeEncodeError`.

Nhóm `path_escape` có 5 case `block` (PE01, PE02, PE03, PE05, PE07) và 3 case `allow` (PE04 `notes.txt`, PE06 `bao-cao.md`, PE08 `src/app.py`). Precision dưới 0.90 trong khi recall không bị nêu nghĩa là file được phép bị tính thành chặn. `predict_case` gọi `_denied_path(root, target)` với `root` là `TemporaryDirectory()`, không qua `Session.__post_init__` (chỗ đó đã `resolve()`). `_denied_path` làm `path.resolve().relative_to(root)` khi `root` chưa resolve.

Trên máy này `GetShortPathNameW` của thư mục tạm ra dạng `TMP6N8~1`, khác `resolve()`. Chạy `predict_case` với gốc ngắn đó: PE04, PE06, PE08 thành `block` (sai), năm case `block` vẫn `block`. 5 đúng trên 8 lần chặn → precision 0.625. Runner `windows-latest` đặt `TEMP` kiểu `C:\Users\RUNNER~1\...`, cùng một lệch 8.3. Máy này và Ubuntu không lệch nên selftest và quality-gate vẫn xanh. Không phải thứ tự case, không phải bảng mã stdout.

Sửa đúng chỗ: `_denied_path` so với `root.resolve()`. Không đổi `expected`. Không đụng `_arg_outside` (phiên làm việc đã resolve gốc).

## 1. WIN-1 — đưa traceback vào annotation, rồi sửa đúng test đó

### a. Hành vi cũ và mới

Cũ: `.github/workflows/test.yml` dòng 21–22 chạy `python -m unittest discover -s tests -v`. Khi đỏ, API chỉ thấy exit 1. Không sửa `mira/tools.py` trong commit đầu của mục này. Đoạn backslash ở `_arg_outside` (`mira/tools.py`, hàm bắt đầu khoảng dòng 689 sau commit `6252b4e`) giữ nguyên cho đến khi annotation mới nêu tên test.

Mới, commit chẩn đoán, chỉ workflow và một helper chuẩn:

- Tên job thành `unittest (${{ matrix.os }} / ${{ matrix.python-version }})` để bốn ô Windows không còn trùng tên.
- Bước unittest không nuốt mã thoát. Chạy discover, ghi stdout+stderr vào `unittest.txt` trong workspace. Mã khác 0 thì helper in từng khối fail theo dạng `::error::` (GitHub biến các dòng đó thành annotation, thứ API `check-runs/.../annotations` đã trả được không cần quyền admin). Rồi thoát 1. Mã 0 thì không in `::error::`.
- Helper là `tools/ci_annotate.py`, chỉ thư viện chuẩn. Đọc file log, tìm dòng `FAIL:` và `ERROR:` của unittest, in tối đa 30 dòng quanh mỗi khối, cắt mỗi dòng 500 ký tự. Không gọi mạng. Không đổi test cho “vừa runner”.
- Không đặt `PYTHONUTF8` hay `PYTHONIOENCODING` trong yml. `ui._prefer_utf8` đã xử lý console. Ép UTF-8 trên CI sẽ giấu một lỗi bảng mã nếu lỗi đó có thật ở máy không import `ui`.
- Không sửa assertion, không xóa test, không `continue-on-error`.

Commit sửa, chỉ sau khi annotation của run chẩn đoán có tên test: sửa hàm mà traceback chỉ vào. Kèm test chạy trên Linux nhưng nói ngữ pháp đường dẫn Windows bằng `pathlib.PureWindowsPath`, không cần máy Windows. `os.name` và `os.sep` chỉ dùng để chọn nhánh lệnh trong test shell, không dùng để bỏ qua assertion.

Bảng quyết định, chọn sau khi có chữ trong annotation, không chọn trước:

- Annotation là `UnicodeEncodeError` ở một `print` không đi qua `ui`: đưa chữ đó qua stream đã `reconfigure`, hoặc bỏ dấu ở dòng log CI. Không đổi test để khỏi in tiếng Việt.
- Annotation là sai khác `block`/`allow` của path: sửa `_arg_outside` cho `PureWindowsPath` và `PurePosixPath` cùng một kết quả với các case trong `eval/adversarial/cases.jsonl` trục `path_escape`. Không đổi `expected`.
- Annotation là symlink (`tests/test_disk_guard.py` dòng 34–45): test đã `skipTest` khi `os.symlink` ném `OSError`. Nếu runner tạo được symlink và assertion sai, sửa `read_file` để symlink ra ngoài gốc vẫn `PermissionError`. Không bỏ skip để ép máy không có quyền symlink phải đỏ.
- Annotation là việc khác: sửa đúng hàm trong traceback. Không nhân tiện sửa path.

Nếu annotation chẩn đoán vẫn chỉ là `Process completed with exit code 1` và không có `FAIL:`/`ERROR:`, dừng hỏi. Không đoán tiếp.

### b. Test

File `tests/test_ci_annotate.py`:

- `test_log_xanh_khong_in_error`: log chỉ có `OK`. Helper in rỗng và trả 0.
- `test_fail_trich_ten_test`: log có `FAIL: test_vi_du` và một dòng `AssertionError`. Đầu ra chứa `::error::` và `test_vi_du`.
- `test_error_traceback_duoc_giu`: log có `ERROR:` và `Traceback`. Đầu ra chứa cả hai, và dòng dài hơn 500 ký tự bị cắt.

File `tests/test_windows_path.py`, thêm trong commit sửa nếu annotation thuộc path, hoặc thêm cùng commit chẩn đoán nếu muốn khóa PE02 trước. Khóa PE02 không chờ annotation, vì case đó đã là sự thật và Linux đã từng tính sai:

- `test_pure_windows_backslash_thoat_goc`: `PureWindowsPath(r"..\..\Windows")` có `..` trong `parts`. Hàm chuẩn hóa dùng trong `_arg_outside` phải coi đó là thoát gốc.
- `test_pure_windows_src_app_nam_trong`: `src\\app.py` không thoát gốc.
- `test_pure_posix_va_windows_cung_ket_luan_pe02`: cùng chuỗi `..\\..\\Windows`, cả hai grammar đều ra `block` khi gọi `predict_case` với root tạm. Test này chạy trên Linux trong CI Ubuntu.

### c. Lệnh

```
py -3 -m unittest discover -s tests -p "test_ci_annotate.py" -v
py -3 -m unittest discover -s tests -p "test_windows_path.py" -v
```

Sau commit chẩn đoán, đẩy lên `main` và đọc lại annotation bốn job Windows. Dán nguyên văn `::error::` vào báo cáo. Chưa dán thì chưa sang commit sửa.

Clone sạch sau commit sửa, trong đúng thư mục clone: `py -3 -m mira selftest`. `python3` trên máy này không phải interpreter. Trên CI lệnh vẫn là `python` của setup-python.

Cổng xong WIN-1: một run mà cả 8 unittest, `quality-gate`, và `commit-lint` đều success. Link run đó là điều kiện mở P3-01. `shadow` đang xanh ở `6252b4e` và phải vẫn xanh, nhưng lời giao đếm 10 job không gồm shadow.

### d. Commit

Commit 1: `[WIN-1] Put the unittest failure into the job annotation`

Tiền tố `[WIN-1] ` là 8 ký tự, phần sau 46, tổng 54.

Commit 2: chủ đề viết sau khi có tên test, vẫn `[WIN-1]`, ASCII, không quá 72. Không gộp hai commit.

Ước lượng: helper khoảng 60 dòng, yml khoảng 20 dòng, test annotate khoảng 50 dòng, test path khoảng 40 dòng, cộng phần sửa sau annotation khoảng 40 dòng nếu chỉ một hàm.

### e. Bốn job đã mở, và hợp đồng helper

Bốn URL, mỗi cái đã đọc annotation. Nội dung hai annotation giống nhau, trích ở mục 0:

- https://github.com/wuongg/mira-harness/actions/runs/38394358448/job/115285684004
- https://github.com/wuongg/mira-harness/actions/runs/38394358448/job/115285684080
- https://github.com/wuongg/mira-harness/actions/runs/38394358448/job/115285684203
- https://github.com/wuongg/mira-harness/actions/runs/38394358448/job/115285684254

Helper `tools/ci_annotate.py` nhận đường dẫn log và mã thoát của discover.

- Mã 0: không in gì, trả 0. Chữ `FAIL` nằm giữa câu của một test không tính. Chỉ nhận dòng unittest bắt đầu bằng `FAIL:` hoặc `ERROR:`, và dòng dạng `test_... FAIL` của chế độ `-v`.
- Mã khác 0 mà không có các dòng đó và không có `Traceback`: in một dòng `::error::unittest thoát <mã> nhưng log không có khối fail`, trả 1. Gặp annotation này thì dừng hỏi, không sửa sản phẩm.
- Mỗi khối cắt ở dòng trống trước khối sau, tối đa 30 dòng, mỗi dòng tối đa 500 ký tự.

Bước yml thay dòng 21–22. Dùng `shell: bash` trên cả Windows vì runner có Git Bash và job `commit-lint` đã dùng `shell: bash` ở dòng 47. Không viết thêm script PowerShell.

```
- name: Chạy toàn bộ unittest
  shell: bash
  run: |
    set +e
    python -m unittest discover -s tests -v > unittest.txt 2>&1
    code=$?
    python tools/ci_annotate.py unittest.txt "$code"
    exit $?
```

`ci_annotate.py` trả đúng mã discover khi log có khối fail, trả 0 khi discover trả 0.

Hàm thuần `_path_escapes(text, grammar)` đứng trong `mira/tools.py`, không gọi `resolve()`:

- `grammar="windows"` dùng `PureWindowsPath`. `grammar="posix"` dùng `PurePosixPath`.
- Trả đúng khi part có `..` hoặc path là tuyệt đối theo grammar đó.
- Với `..\\..\\Windows`, cả hai grammar phải trả thoát. Với `src/app.py` và `src\\app.py`, cả hai phải trả không thoát.
- `_arg_outside` giữ bước đổi `\` thành `/` rồi mới tạo `Path` của hệ đang chạy. Nếu hàm thuần và `predict_case` lệch nhau, sửa `_arg_outside` cho khớp hàm thuần. Không sửa hàm thuần theo ổ đĩa của runner. `resolve()` trên `D:\a\...` và trên `C:\Users\...` không được là thước.

## 2. P3-01 — retry 429 và 5xx, không tính tiền hai lần

### a. Hành vi cũ và mới

Cũ: `mira/providers.py` dòng 55–69, `BaseProvider._post` gọi `urlopen` một lần. `HTTPError` và `URLError` thành `ProviderError` ngay. `mira/native.py` dòng 245–259, `_request` cùng kiểu, không retry. `mira/team.py` dòng 392–411, `Ledger.charge` cộng `usd` mỗi lần được gọi. `_call` trong `execute_plan` charge sau khi `prov.call` trả về. Không có trường `attempt`.

Mới:

- Một hàm `retry_post` trong `providers.py`, dùng bởi `_post` và bởi `native._request`. Không thêm thư viện. Không copy hai vòng lặp lệch nhau.
- Tối đa 3 lần gọi HTTP cho một `_post`. Lần 1 là thử đầu. Còn 429 hoặc mã 500–599 thì chờ rồi thử tiếp, đến khi đủ 3 lần.
- Khoảng chờ trước lần 2 là 0.5 giây, trước lần 3 là 1 giây, cộng jitter trong `[0, 0.25]`. Không ngủ sau lần thất bại cuối. Jitter lấy từ `random.Random` truyền vào, test ghim seed. Không dùng `random` toàn cục.
- 400, 401, 403, 404 và mọi 4xx khác 429: không thử lại. Đọc body một lần, ném `ProviderError` như hiện tại.
- `URLError` và timeout: không thử lại. Một request có thể đã tới server. Thử lại dễ charge hoặc ghi đúp nếu sau này ai đó charge trước khi xem mã. Cửa này chặt hơn “retry mọi lỗi mạng”.
- Timeout mỗi lần giữ `self.timeout` (mặc định 180 ở `BaseProvider.__init__`, dòng 33–34). Không rút xuống cho test. Test vá `time.sleep` và `urlopen`, không gọi mạng.
- `self.attempts` là số lần đã mở HTTP trong lượt `_post` vừa xong. `call` trả như cũ. Chỗ `_call` của team ghi `attempt` lên step. Giá trị là số lần HTTP, không phải số lần charge.
- `Ledger.charge` chỉ chạy khi `call` trả về, tức HTTP cuối là thành công. 429 rồi 200: một lần charge. Ba lần 503: không charge, step có `error` và `attempt` bằng 3.
- Không retry ở tầng `charge`. Không thêm cờ tắt retry.

### b. Test

File `tests/test_retry.py`. `urlopen` giả, không socket.

- `test_429_roi_200_chi_charge_mot_lan`: hai response, 429 rồi 200. `attempts == 2`. Một lần `Ledger.charge`. `total_usd` bằng một lượt.
- `test_400_khong_thu_lai`: một 400. `urlopen` gọi đúng 1 lần. Không charge.
- `test_503_du_ba_lan_khong_charge`: ba lần 503. `attempts == 3`. `charge` không được gọi. `ProviderError` vẫn nổi.
- `test_sleep_dung_0_5_roi_1`: seed cố định, jitter kiểm được. Hai khoảng ngủ nằm trong `[0.5, 0.75]` và `[1.0, 1.25]`. Không có lần ngủ thứ ba.

### c. Lệnh

```
py -3 -m unittest discover -s tests -p "test_retry.py" -v
```

Clone sạch sau commit, `py -3 -m mira selftest`, dán `Ran` và `OK`.

### d. Commit

`[P3-01] Retry 429 and 5xx without charging twice`

Tiền tố `[P3-01] ` là 9, phần sau 42, tổng 51.

Ước lượng: `providers.py` khoảng 70 dòng, `native.py` khoảng 15 dòng, team ghi `attempt` khoảng 15 dòng, test khoảng 120 dòng.

## 3. P3-02 — checkpoint và resume

### a. Hành vi cũ và mới

Cũ: `execute_plan` (`mira/team.py` dòng 439 trở đi) không ghi `checkpoint.json`. `prepare_staging` dòng 286–307 tạo thư mục staging mới mỗi lần worker sửa. `mira team` (`mira/cli.py` dòng 742) không có `--resume`. `mira chat --resume` (dòng 824) mở phiên REPL, không phải đội. Ledger chỉ sống trong process.

Mới:

- Sau mỗi step đã append vào `steps`, ghi `root/.mira/runs/<id>/checkpoint.json`. `<id>` sinh một lần ở đầu `execute_plan` và trả trong kết quả. File gồm `id`, `next_index`, `steps` đã xong, `ledger` (`rows`, `total_usd`, `total_in`, `total_out`, `subagent_runs`), `staging` (đường dẫn hoặc null), `status`.
- Ghi nguyên tử: viết file tạm cùng thư mục rồi `os.replace`. Mất điện không để file nửa vời thành checkpoint hợp lệ.
- `mira team --resume <id>` đọc checkpoint trong `--out` hoặc trong `root/.mira/runs/<id>` nếu `--root` trỏ cây đó. Thiếu file: thoát 2, câu `không có checkpoint cho id này`. Không tạo run mới.
- Resume xây `Ledger` từ `rows` đã ghi. Không gọi `charge` cho step đã có trong checkpoint. Step kế tiếp charge bình thường nếu có HTTP mới.
- `staging` trong checkpoint được dùng lại. Không gọi `prepare_staging` lần nữa khi đường dẫn còn tồn tại. Hết thư mục staging: thoát 2, câu `staging của checkpoint không còn`, không copy cây nguồn đè lên.
- Step đã `error` hoặc `blocked` không được nhảy cóc. Resume dừng lại với cùng `fail_reason`, không gọi model thêm.
- Trace cũ không có checkpoint vẫn đọc được. Resume không bịa tiến độ.
- Không đụng cổng giá, khóa sổ cái, hay cửa ghi I1. Checkpoint nằm dưới `root/.mira/runs`, cùng họ với staging đã được fuzz cho phép.

### b. Test

File `tests/test_resume.py`. Provider giả, không mạng.

- `test_moi_buoc_ghi_checkpoint`: một plan dry-run hoặc provider giả hai step. Sau bước 1, file có `next_index` 1 và ledger khớp `total_usd`.
- `test_resume_khong_charge_lai`: chạy tới step 1, tổng 1.0. Resume. Provider bước 1 không bị gọi lại. Tổng chỉ tăng bởi step 2.
- `test_resume_giu_staging`: worker edit tạo staging. Resume thấy cùng đường dẫn `staging` và không có thư mục staging thứ hai.
- `test_resume_thieu_checkpoint_thi_loi`: id lạ, mã thoát 2, không có thư mục run mới.

### c. Lệnh

```
py -3 -m unittest discover -s tests -p "test_resume.py" -v
```

Clone sạch, `py -3 -m mira selftest`, dán số.

### d. Commit

`[P3-02] Resume a team from its checkpoint and ledger`

Tiền tố `[P3-02] ` là 9, phần sau 44, tổng 53.

Ước lượng: team khoảng 160 dòng, cli khoảng 25 dòng, test khoảng 150 dòng.

## 4. P3-03 — khóa shell đã sạch thì chỉ thêm test

### a. Hành vi cũ và mới

Cũ, đã sạch từ P0-07: `mira/tools.py` dòng 31–36, `_shell_env` bỏ mọi tên trong `keys.ENV` (dòng 62–68 của `mira/keys.py`) và mọi tên kết thúc bằng `_API_KEY`. `run_shell` dòng 1226–1228 truyền `env=_shell_env()` vào `subprocess.run`. `tests/test_key_leak.py` dòng 51–65, `test_shell_con_khong_thay_khoa`, đã chạy Python con và assert chuỗi `EXPOSE` không có trong đầu ra khi `ANTHROPIC_API_KEY` nằm trong môi trường cha.

Mới: không sửa `_shell_env` và không sửa `run_shell` nếu các test mới đều xanh. Nếu một test mới đỏ, sửa đúng chỗ scrub cho test đó xanh, không nới test.

`printenv` không có sẵn trên Windows. Test không được gọi `printenv` rồi coi “không tìm thấy lệnh” là đạt. Nhánh POSIX chạy `printenv`. Cả hai hệ điều hành đều chạy Python con in giá trị biến, như test hiện có. Assertion là giá trị khóa không xuất hiện. Thiếu `printenv` trên Windows không làm test POSIX biến mất trên Ubuntu CI.

Không làm cảnh báo `bwrap` và không làm OTEL. Hai việc đó là P3-03/P3-04 trong `docs/PLAN.md` dòng 363–376. Lời giao này chỉ yêu cầu scrub env. Cửa lời giao hẹp hơn cửa PLAN.md. Lấy lời giao.

### b. Test

Thêm vào `tests/test_key_leak.py`, không xóa `test_shell_con_khong_thay_khoa`:

- `test_printenv_khong_chua_khoa`: nếu `shutil.which("printenv")` thì `run_shell("printenv")` không chứa `EXPOSE` và không chứa tên `ANTHROPIC_API_KEY` với giá trị đó. Luôn luôn, kể cả khi không có `printenv`, Python con in `os.environ.get("ANTHROPIC_API_KEY")` và đầu ra không có `EXPOSE`.
- `test_hau_to_api_key_bi_bo`: đặt `FOO_API_KEY=EXPOSE-FOO` dù tên không nằm trong `keys.ENV`. Python con in biến đó. Đầu ra không có `EXPOSE-FOO`.
- `test_path_van_con`: `_shell_env()` vẫn có `PATH` hoặc `Path` trên Windows. Scrub không xóa đường dẫn lệnh.

### c. Lệnh

```
py -3 -m unittest discover -s tests -p "test_key_leak.py" -v
```

Clone sạch, `py -3 -m mira selftest`, dán số.

### d. Commit

`[P3-03] Lock the shell env so child processes miss API keys`

Tiền tố `[P3-03] ` là 9, phần sau 49, tổng 58.

Ước lượng: nếu scrub đã đúng thì 0 dòng sản phẩm và khoảng 70 dòng test. Nếu `FOO_API_KEY` lọt, sửa `_shell_env` khoảng 5 dòng. Hậu tố `_API_KEY` đã có ở dòng 36, test này là khóa, kỳ vọng không phải sửa.

## 2c. Máy trạng thái của một lần `_post`

`attempts` bằng 0 trước khi mở kết nối.

1. Tăng `attempts`. Gọi `urlopen` với `self.timeout`.
2. Mã 2xx: trả body, dừng.
3. Mã 429 hoặc 500–599, và `attempts` nhỏ hơn 3: ngủ `0.5 * 2^(attempts-1)` giây cộng jitter trong `[0, 0.25]`, rồi về bước 1. Không ngủ sau lần cuối.
4. Hết 3 lần vẫn 429 hoặc 5xx: ném `ProviderError`, không ngủ.
5. 4xx khác 429: ném ngay.
6. `URLError`: ném ngay.

`native._request` gọi cùng hàm. Body lỗi cắt 400 ký tự như `providers.py` dòng 66 và `native.py` dòng 256. `Ledger.charge` không nằm trong vòng lặp. Test một lần 429 rồi 200 phải thấy `len(ledger.rows)==1`.

## 3c. Hình dạng checkpoint

Sau một step, file `.mira/runs/<id>/checkpoint.json` có các khóa `id`, `next_index`, `task`, `steps`, `ledger`, `staging`, `status`, `fail_reason`. `next_index` bằng `len(steps)`. Resume bỏ qua bấy nhiêu vai đầu của lịch vừa tính lại từ plan. Lịch ngắn hơn `next_index` thì thoát 2, câu `checkpoint dài hơn kế hoạch`. Không cắt plan cho khớp file.

`ledger.total_usd` phải bằng tổng `usd` của `rows` sau khi làm tròn 6 số. Lệch thì thoát 2, câu `checkpoint lệch sổ cái`. Nạp `rows` bằng gán, không gọi `charge`.

`staging` là đường dẫn đã resolve, nằm dưới `root/.mira/staging`. Thoát khỏi `root` thì từ chối, thoát 2. Thư mục không còn thì thoát 2, câu `staging của checkpoint không còn`, không gọi `prepare_staging` để copy đè.

Ghi file bằng cách viết tạm cùng thư mục rồi `os.replace`. Id không lấy từ thư mục `--out` của executor, vì executor chỉ ghi khi run kết thúc, còn checkpoint phải có trước khi xong.

`--resume` không lưu “đã `--approve` mãi mãi”. Step mới vẫn qua cổng. Step đã có trong file không gọi model và không charge lại.

## 4c. Tên biến scrub phải mất và phải còn

`keys.ENV` có bảy tên, từ `OPENROUTER_API_KEY` đến `SERPER_API_KEY`, `mira/keys.py` dòng 62–68. Hậu tố `_API_KEY` ở `mira/tools.py` dòng 36 phủ cả bảy. Test `test_hau_to_api_key_bi_bo` dùng `FOO_API_KEY` ngoài bảng để khóa luật hậu tố.

`PATH` hoặc `Path` phải còn. `MIRA_PRICE_SONNET_5_5` không phải khóa API. Không xóa nó, và không thêm test giấu giá trong mục này.

Lệnh con dùng `sys.executable` với `shlex.join`, cùng kiểu dòng 57–58 của `tests/test_key_leak.py`. Không dùng `cmd /c echo %ANTHROPIC_API_KEY%`, vì bash trên runner Windows không nở biến theo kiểu cmd. Giá trị giữ hằng `SECRET` dòng 20, chuỗi `sk-test-EXPOSE-0123456789`, đủ dài để không đụng `PATH`.

Clone sau mỗi commit: `git clone` từ repo vừa commit, `checkout` đúng hash, `Push-Location` vào clone, rồi `py -3 -m mira selftest`. Selftest ở cây làm việc không tính. Dán dòng `Ran` và `OK` hoặc `FAILED`.

Link CI là run của đúng hash mới. `6252b4e` không được dùng làm bằng chứng WIN-1 đã xanh. Mười job phải success trên run đó: bốn Ubuntu, bốn Windows, quality-gate, commit-lint.

## 5. Thứ tự, ước lượng, cổng chặt hơn

Thứ tự sau khi duyệt:

1. WIN-1 commit chẩn đoán. Đọc annotation mới. Dừng nếu vẫn không có tên test.
2. WIN-1 commit sửa đúng traceback. Selftest clone. Run CI đủ 10 job xanh. Dán link.
3. P3-01.
4. P3-02.
5. P3-03.
6. Không mở P4.

Ước lượng dòng, gồm test:

| mục | sản phẩm | test | cộng |
| --- | --- | --- | --- |
| WIN-1 chẩn đoán | 80 | 50 | 130 |
| WIN-1 sửa | 40 | 40 | 80 |
| P3-01 | 100 | 120 | 220 |
| P3-02 | 185 | 150 | 335 |
| P3-03 | 0 đến 5 | 70 | 75 |

Chỗ chọn cửa chặt hơn:

- Không vá `tools.py` khi annotation chưa nêu test. Vá nhầm path trong lúc Windows đỏ vì việc khác sẽ làm lệch PE02 vừa mới xanh trên Ubuntu.
- Không bật `PYTHONUTF8` trên CI để cho qua. Máy không import `ui` vẫn phải in được hoặc thất bại rõ, không nuốt lỗi bằng biến môi trường chỉ có trên runner.
- Retry không gồm `URLError`. 4xx khác 429 không retry. Ba lần là trần, không phải ba lần cộng thêm lần đầu.
- Charge chỉ sau `call` thành công. Không charge từng attempt rồi hoàn tiền.
- Resume thiếu checkpoint thoát 2, không tạo đội mới. Staging mất thì dừng, không copy lại cây nguồn.
- P3-03 không đụng `bwrap` và OTEL dù `docs/PLAN.md` ghi cùng mục. Lời giao chỉ khóa scrub.
- `printenv` thiếu trên Windows không được tính là pass. Python con vẫn phải chứng minh khóa không vào env.

## 6. Tự kiểm

- Bốn mục WIN-1, P3-01, P3-02, P3-03 đều có a, b, c, d.
- Annotation hai dòng của bốn job Windows được trích. Không có dòng `FAIL:` bịa.
- Đã nói rõ log 403 và 404, và selftest cục bộ 414 OK.
- Đã tách “backslash làm đỏ Windows” khỏi sự thật: Windows đỏ từ `f03c574`, Ubuntu hết đỏ ở `6252b4e`.
- Mỗi mục có ít nhất ba test có tên.
- I1 đến I8 không bị nới. I1 giữ cửa `.mira`. Retry không thêm dependency.
- P4 không có việc. P3-01 không bắt đầu trước link CI 10 job xanh.
- Không có mục để trống. Việc không làm được ghi trong mục 0 là giới hạn của API, kèm bước biến giới hạn đó thành annotation đọc được.

## 7. Việc không làm trong lát này

- Không sửa `_arg_outside` trong commit chẩn đoán.
- Không hạ ngưỡng quality-gate 0.90.
- Không đổi `expected` của case đối kháng.
- Không thêm package.
- Không làm span OTEL, không làm cảnh báo thiếu `bwrap`.
- Không mở P4 khi WIN-1 chưa có run 10 job xanh.
