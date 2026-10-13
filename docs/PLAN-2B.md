# Plan vệ sinh vòng 2b (S1 đến S5)

Sau khi duyệt, ghi nguyên văn tài liệu này vào [docs/PLAN-2B.md](docs/PLAN-2B.md). Chưa sửa code ở bước lập plan. Nguồn sự thật là cây đang ở `f308234` trên `main`. P1 và INTAKE không được mở cho đến khi Phần E đạt. Không thêm dependency. Không rewrite lịch sử public. Chuỗi người dùng giữ tiếng Việt. Định danh code mới là tiếng Anh, ASCII. Tiêu đề commit từ sprint này là ASCII, không dấu, không BOM, không zero-width, không quá 72 ký tự.

Mâu thuẫn trong chính sprint, đã khóa cách làm:

- S1 được MD gọi là "commit thuần rename" nhưng cùng mục bắt thêm shim, cảnh báo, và migration `~/.r0`. Một commit `[S1]` sẽ chứa cả `git mv` lẫn code mới. Không tách thêm ID ngoài `[S1]`–`[S5]`. `git show --stat` của S1 sẽ có file mới, không chỉ rename. S2 và các `git mv` thư mục eval mới là rename kèm đúng dòng tham chiếu, không kèm sửa luật an toàn.
- Phần E ghi `HEAD~6..HEAD`. Sau đúng 5 commit sprint, range đó còn kéo `f308234`, commit không có `[ID]`. Máy gác sẽ fail đúng như thiết kế. Lệnh nộp bài dùng `HEAD~5..HEAD`. Không sửa commit cũ.
- Trên Windows lệnh kiểm là `py -3 -m mira selftest` và `py -3 -m r0 selftest`. `python3` không có trên máy này.

## 0. Đối chiếu Phần A

### A1. Ba tên. Đúng.

- Sản phẩm `mira`: [pyproject.toml](pyproject.toml) dòng 5 `name = "mira"`, dòng 15 `mira = "r0.cli:main"`. [mira.cmd](mira.cmd) dòng 4 gọi `python -m r0`. Runtime cây làm việc là `.mira/` tại [r0/team.py](r0/team.py) dòng 232 (`staging = root / ".mira" / "staging"`) và [r0/skills.py](r0/skills.py) dòng 87.
- Package vẫn là `r0`: [pyproject.toml](pyproject.toml) dòng 19 `packages = ["r0"]`, dòng 22 `version = {attr = "r0.__version__"}`. Có [r0/__main__.py](r0/__main__.py) nên `python -m r0` chạy được.
- Khóa người dùng: [r0/keys.py](r0/keys.py) dòng 18 `KEYS_PATH = Path.home() / ".r0" / "keys.json"`. Phiên: [r0/repl.py](r0/repl.py) dòng 26 và [r0/activity.py](r0/activity.py) dòng 21 đều `Path.home() / ".r0" / "sessions"`. MD chỉ nêu `keys.json`. Phiên cũng nằm dưới `~/.r0`. Migration phải mang cả hai, nếu không doctor trỏ `~/.mira` trong khi hội thoại cũ vẫn ở `~/.r0`.
- `r0-shadow`: [pyproject.toml](pyproject.toml) dòng 16 trỏ cùng `r0.cli:main`. Help [r0/cli.py](r0/cli.py) dòng 5–12 là tám ví dụ `r0-shadow`. Docstring [r0/install_path.py](r0/install_path.py) dòng 4–5 nói AppLocker chặn `mira.exe` và launcher gọi `python -m r0`. Đúng như A1.

Đếm import Python `from r0` hoặc `import r0` trên file thật, không đếm hai lần vì dấu slash: 109 chỗ trong tests cộng 1 chỗ `import r0` trong [r0/cli.py](r0/cli.py) dòng 375. Trong package, phần còn lại là import tương đối. Ngoài Python: [Dockerfile](Dockerfile) dòng 7 `COPY r0 ./r0`, [.github/workflows/test.yml](.github/workflows/test.yml) dòng 33 `python -m r0 run`, [run.sh](run.sh) dòng 19 và 22, [mira.cmd](mira.cmd) dòng 4, [tests/test_install.py](tests/test_install.py) dòng 13 và 25 chờ chữ `python -m r0`.

### A2. Định danh lai. Đúng một phần.

- `HOI_TOOLS`: đúng hai chỗ, [r0/team.py](r0/team.py) dòng 82 (khai báo) và dòng 147 (`tool not in HOI_TOOLS`). Không có chỗ thứ ba trong `tests/`.
- `"sua"`: đúng là giá trị shape. Không chỉ ở team. [r0/tools.py](r0/tools.py) dòng 89 `return "sua"`, dòng 623 `shape in ("sua", "chay")`. [r0/team.py](r0/team.py) dòng 670 so `== "sua"`. [r0/agent.py](r0/agent.py) dòng 55. Test: [tests/test_skills.py](tests/test_skills.py) dòng 212 và các gán `shape = "sua"` dòng 228, 243, 258, 284, 295, 307.
- MD không kể ba giá trị cùng enum: `"chay"` [r0/tools.py](r0/tools.py) dòng 91 và 621–623, `"doc"` dòng 93 và 619, `"hoi"` dòng 94 và 619, cộng [r0/agent.py](r0/agent.py) dòng 115 `session.shape != "hoi"`, [tests/test_skills.py](tests/test_skills.py) dòng 213–221, [tests/test_tools.py](tests/test_tools.py) dòng 203. Phần B mục 2 bắt mọi giá trị shape là tiếng Anh. S2 đổi cả bốn: `sua`→`edit`, `chay`→`run`, `doc`→`read`, `hoi`→`ask`. Không đụng `CONTENT_KIND` trong [r0/tasks.py](r0/tasks.py) dòng 87–88: chữ `"doc"` ở đó là loại nội dung shadow, không phải shape.
- `r0/chon_dat_256.txt` tồn tại. Chỗ nạp duy nhất: [r0/mascot_art.py](r0/mascot_art.py) dòng 588 `_IDX = Path(__file__).with_name("chon_dat_256.txt")`.
- 14 thư mục eval đúng bảng MD. [eval/tasks/doi_gia_tri/task.json](eval/tasks/doi_gia_tri/task.json) không có trường `id` hay `name` trùng tên thư mục. Không thêm `axis_vi`. [r0/bench.py](r0/bench.py) dòng 33–36 nạp bằng listing `eval/tasks`, nên đổi tên thư mục không cần sửa loader.
- Sai thêm: [r0/mascot_art.py](r0/mascot_art.py) dòng 16 và [tests/test_mascot_art.py](tests/test_mascot_art.py) dòng 7 trỏ `chon_dat_cutout.png` ở gốc repo.

### A3. Commit. Đúng, không rewrite.

- `205a671` được tạo bằng PowerShell `Set-Content -Encoding utf8`, cách đó ghi BOM U+FEFF vào đầu tiêu đề. `git log` in subject bắt đầu bằng ký tự đó. Không amend, không rebase. Lịch sử đã ở `origin/main`.
- `f308234` tiêu đề `Cho model giả trong test một giá khai, để cổng giá không chặn server cục bộ.` Không có `[ID]`. Giữ nguyên.
- Các commit trước `76fae07` là câu tiếng Việt dài, nhiều việc một commit. Giữ nguyên.

### A4. Rác gốc. MD sai với cây này.

- `chon_dat.ansi`, `chon_dat_80.png`, `chon_dat_cutout (1).png`, `chon_dat_cutout.png` không có trong worktree và không có trong `git ls-files` dạng glob png/ansi. Vòng 1 đã ghi trong [docs/PLAN.md](docs/PLAN.md) dòng 10 rằng ảnh không tồn tại. S3 không có file để `git mv` hay `git rm`.
- Đã có trong `docs/`: `cach-dung-moi.txt`, `chon_dat.sh`, `PLAN.md`. Không có `docs/PLAN-V2.md`. S5 không tạo file đó chỉ để chèn một dòng.
- [.gitignore](.gitignore) đã có `out/`, `out-*/`, `__pycache__/`, `labels.csv`. Thiếu `.mira/` và `*.withheld/`.
- [Dockerfile](Dockerfile) dòng 9 vẫn `COPY labels.csv ./` dù `labels.csv` đã bỏ khỏi git ở P0-08. S1 sửa Dockerfile nên bỏ dòng COPY đó, nếu không image gãy. Không phải việc đổi tên.

Không còn TBD.

## 1. S1 — Package `mira`, shim, migration

Một commit. Tiêu đề ASCII:

`[S1] Rename package r0 to mira and migrate user data`

Ước lượng: khoảng 250 dòng cơ học (import và đường dẫn) cộng khoảng 120 dòng mới (shim, migration, cảnh báo). Không đổi `t1a_policy`, cổng người, hay luật shape ngoài việc package đổi tên.

### 1a. Đổi cây package

- `git mv r0 mira`. Kèm `mira/chon_dat_256.txt` (đổi tên file này để S2, không làm trong S1).
- Trong `mira/**/*.py`, `tests/**/*.py`: `from r0` → `from mira`, `import r0` → `import mira`. Danh sách file test có import, mỗi file một lần: `test_activity.py`, `test_agent.py`, `test_chat.py`, `test_classifier.py`, `test_classifier_model.py`, `test_classifiers.py`, `test_content.py`, `test_detect.py`, `test_disk_guard.py`, `test_dual_gate.py`, `test_eval.py`, `test_guards.py`, `test_install.py`, `test_invariants.py`, `test_key_leak.py`, `test_keys.py`, `test_lineedit.py`, `test_mascot_art.py`, `test_mira.py`, `test_native.py`, `test_open.py`, `test_panel.py`, `test_price_gate.py`, `test_repl_ux.py`, `test_repo_hygiene.py` (đường dẫn `r0/team.py` trong test compile), `test_selftest_isolated.py`, `test_skills.py`, `test_team.py`, `test_tools.py`, `test_tui.py`, `test_ui.py`, `test_verdict.py`, `test_wts.py`.
- [pyproject.toml](pyproject.toml): `packages = ["mira"]`, attr `mira.__version__`. Scripts: `mira = "mira.cli:main"` không cảnh báo. `r0 = "mira.cli:deprecated_main"` và `r0-shadow = "mira.cli:deprecated_main"`.
- [mira/cli.py](mira/cli.py) thêm `deprecated_main`: in một dòng tiếng Việt ra stderr `r0 và r0-shadow sẽ bị gỡ sau phiên bản kế tiếp. Hãy gọi mira.` rồi gọi `main`. Entry `mira` không in dòng đó.
- [Dockerfile](Dockerfile): `COPY mira ./mira`. Xóa `COPY labels.csv ./`.
- [.github/workflows/test.yml](.github/workflows/test.yml) dòng 33: `python -m mira run`.
- [run.sh](run.sh), [mira.cmd](mira.cmd), [mira/install_path.py](mira/install_path.py) dòng 37, 40, 48, 51: `python -m mira` và `py -3 -m mira`. Docstring install_path còn một câu: launcher `.cmd` gọi module, không tạo exe. Bỏ đoạn AppLocker.
- [tests/test_install.py](tests/test_install.py) đổi kỳ vọng `python -m mira`.
- [mira/cli.py](mira/cli.py) `cmd_doctor`: import `mira`, in đường dẫn gói `mira`, in `~/.mira` là chỗ khóa và phiên. Giữ câu "môi trường OK".
- Help và chuỗi `r0-shadow` trong code được S5 sửa ở README. Trong S1, các chuỗi người dùng vẫn chạy được. Doctor và entry point phải hết phụ thuộc import `r0`, nếu không `python -m mira` gãy. Các câu help `r0-shadow` còn lại là chữ, không phải import. S5 mới quét README. S1 vẫn sửa mọi chuỗi khiến lệnh thật gọi `python -m r0` (launcher, install shim, workflow, run.sh).

### 1b. Shim `r0`

Tạo [r0/__init__.py](r0/__init__.py) và [r0/__main__.py](r0/__main__.py) sau khi thư mục cũ đã thành `mira/`.

- `__init__.py` gọi `warnings.warn("Gói r0 chỉ là vỏ. Hãy import mira. Vỏ này bị gỡ sau phiên bản kế tiếp.", DeprecationWarning, stacklevel=2)` rồi import `mira` và gán `__version__`.
- `__main__.py` in cùng câu ra stderr và gọi `mira.cli.main`.
- `pyproject` không liệt kê `r0` trong `packages`. `python -m r0` từ gốc repo vẫn thấy thư mục shim vì cwd nằm trên `sys.path`. Script cài `r0` và `r0-shadow` không cần package `r0`.
- Cấm `mira/**` import `r0`. Nếu không, shim và package vòng nhau.

### 1c. Migration `~/.r0` sang `~/.mira`

Hàm `migrate_user_home()` trong [mira/keys.py](mira/keys.py), gọi một lần ở đầu `mira.cli.main` và đầu `deprecated_main`, trước khi đọc khóa hay phiên.

Bước, theo đúng thứ tự:

1. `old = Path.home() / ".r0"`, `new = Path.home() / ".mira"`. Không có `old` thì dừng.
2. `new.mkdir(parents=True, exist_ok=True)`.
3. Khóa. `src = old / "keys.json"`, `dst = new / "keys.json"`. Nếu `src` là file và `dst` chưa tồn tại: `copy2` rồi `os.replace(src, old / "keys.json.migrated")`. Không `unlink`. Nếu `dst` đã tồn tại: không copy, không đổi tên `src`, in một dòng tiếng Việt rằng hai file cùng tồn tại nên giữ cả hai.
4. Phiên. Với mỗi `*.jsonl` trong `old / "sessions"`: nếu `new / "sessions" / cùng tên` chưa có thì `copy2`. Không xóa file cũ. Không đổi tên thư mục cũ. Ghi `old / "sessions" / ".migrated"` sau khi vòng copy không lỗi, để lần sau biết đã thử.
5. Gán `KEYS_PATH = new / "keys.json"` và `SESS_DIR` của repl và activity sang `new / "sessions"`. Hàm migrate chạy trước các hằng được đọc. Vì hai module đang gắn hằng lúc import, migrate phải sửa thuộc tính module (`keys.KEYS_PATH`, `repl.SESS_DIR`, `activity.SESS_DIR`) chứ không chỉ đổi hằng cục bộ đã bị copy.
6. Lần gọi thứ hai: `dst` đã có nên không đè. File `.migrated` không bị copy lại thành `keys.json`.

Rủi ro và test bẫy từng rủi ro, file `tests/test_home_migrate.py`. Mọi test dùng `tmp_path` và monkeypatch `Path.home`, không đụng `~` thật.

- `test_chi_co_khoa_cu_thi_copy_dung_byte`: chỉ có `old/keys.json` nội dung `{"anthropic":"sk-cu"}`. Sau migrate, `new/keys.json` đọc lại đúng byte, `old/keys.json` không còn, `old/keys.json.migrated` còn đúng byte.
- `test_da_co_khoa_moi_khac_noi_dung_thi_khong_de`: `dst` chứa `sk-moi`, `src` chứa `sk-cu`. Sau migrate, `dst` vẫn `sk-moi`, `src` vẫn tên `keys.json` và vẫn `sk-cu`.
- `test_goi_lan_hai_khong_de`: chạy migrate hai lần sau case chỉ có khóa cũ. Lần hai không tạo file mới, không đổi byte `dst`.
- `test_rename_loi_sau_khi_copy`: `os.replace` ném `OSError` sau `copy2`. `dst` có nội dung, `src` vẫn còn. Lần gọi sau thấy `dst` đã có nên không đè và không xóa `src`.
- `test_phien_thieu_o_dich_thi_copy_file_thieu`: `old/sessions/a.jsonl` và `b.jsonl`, `new/sessions/a.jsonl` đã có chữ khác. Sau migrate, `a` ở đích giữ nguyên, `b` xuất hiện đúng nội dung cũ, cả hai file cũ vẫn nằm ở `old/sessions`.
- `test_khong_co_thu_muc_cu`: không tạo `.mira` chỉ vì migrate. `new` không bị tạo khi `old` vắng.
- `test_shim_in_canh_bao`: chạy `py -3 -m r0 selftest` là quá nặng cho một case. Case này gọi `r0.__main__` với argv `["doctor"]` trong subprocess từ gốc repo, bắt stderr chứa `Hãy gọi mira`, mã thoát 0. `py -3 -m mira doctor` không in câu đó.
- `test_entry_cu_khong_dung_home_that`: doctor in ra đường dẫn có `.mira` khi `Path.home` bị patch. Không đọc khóa thật của máy.

Ước lượng test: khoảng 160 dòng.

Lệnh sau S1, từ gốc repo, cây sạch không cần `out/`:

```text
py -3 -m unittest discover -s tests -p "test_home_migrate.py" -v
py -3 -m unittest discover -s tests -p "test_install.py" -v
py -3 -m mira selftest
py -3 -m r0 selftest
```

Kỳ vọng: cả hai selftest PASS. Lần `r0` in cảnh báo ra stderr. Selftest không bật `-W error`.

## 2. S2 — Định danh và slug eval

Một commit. Tiêu đề:

`[S2] Rename mixed code names and eval slugs`

Không sửa luật cổng. Chỉ đổi tên hằng, chuỗi enum, tên file, tên thư mục, và assertion tương ứng.

Bảng đổi, đủ chỗ:

- `HOI_TOOLS` → `READ_TOOLS` tại [mira/team.py](mira/team.py) (sau S1) đúng hai dòng khai báo và chỗ `not in`.
- Shape trong [mira/tools.py](mira/tools.py) `shape_of` và ba nhánh `_permit` khoảng dòng 619–623. [mira/team.py](mira/team.py) chỗ `== "sua"`. [mira/agent.py](mira/agent.py) dòng 55 và 115.
- Test shape: [tests/test_skills.py](tests/test_skills.py) dòng 212–215 và mọi `shape = "sua"|"doc"`. [tests/test_tools.py](tests/test_tools.py) dòng 203 `"hoi"` → `"ask"`.
- `git mv mira/chon_dat_256.txt mira/tui_palette_256.txt`. Sửa [mira/mascot_art.py](mira/mascot_art.py) dòng 588 sang tên mới. Không đổi thuật toán vẽ.
- `git mv` 14 thư mục, nội dung `task.json` giữ nguyên:

`doi_gia_tri` → `swap_values`, `dung_skill` → `use_skill`, `file_kem` → `missing_file`, `gioi_han_tool` → `tool_limit`, `hai_skill` → `skill_deleted`, `lenh_la` → `stray_command`, `lenh_xong` → `command_done`, `nho_fact` → `forgot_fact`, `nho_lan_sau` → `remember_next`, `noi_dung_la` → `stray_content`, `path_la` → `stray_path`, `plan_khong_ghi` → `plan_no_write`, `script_chua_mo` → `script_unopened`, `tuyen_vai` → `role_recruit`.

Không thêm `axis_vi` vì không có `id`/`name` trùng tên thư mục.

Test mới `tests/test_names.py`:

- `test_shape_bon_gia_tri_tieng_anh`: `shape_of` của bốn câu đang có trong test_skills trả `edit`, `run`, `read`, `ask`.
- `test_khong_con_hoi_tools`: `mira.team.READ_TOOLS` chứa `read_file`, không còn thuộc tính `HOI_TOOLS`.
- `test_eval_slug_moi`: 14 thư mục mới tồn tại, 14 tên cũ không còn, mỗi thư mục có `task.json`.
- `test_palette_doi_ten`: `mira/tui_palette_256.txt` tồn tại, `chon_dat_256.txt` không còn.

Lệnh:

```text
py -3 -m unittest discover -s tests -p "test_names.py" -v
py -3 -m unittest discover -s tests -p "test_skills.py" -v
py -3 -m unittest discover -s tests -p "test_eval.py" -v
py -3 -m mira selftest
py -3 -m r0 selftest
```

Grep bắt buộc, kỳ vọng 0 dòng trong code và test (file sprint và PLAN được phép còn chữ cũ vì là biên bản):

```text
git grep -nE "HOI_TOOLS|\"sua\"|\"chay\"|\"hoi\"|chon_dat_256" -- mira tests pyproject.toml Dockerfile .github
```

`"doc"` không nằm trong grep này vì `tasks.py` còn loại nội dung `doc`. Grep riêng shape đã được test_names khóa.

Ước lượng: khoảng 40 dòng sửa chữ, 14 rename thư mục, 1 rename file palette.

`git show --stat` của S2 được phép hiện rename thư mục và dòng sửa tên. Không được hiện sửa hàm cổng, ledger, hay staging.

## 3. S3 — Rác và gitignore

Một commit. Tiêu đề:

`[S3] Ignore runtime junk and guard repo filenames`

Vì png và ansi không có trong git:

- Không `git mv` `chon_dat.ansi`. Không `git rm` png.
- Giữ tham chiếu `chon_dat_cutout.png` trong mascot: test đã `skipTest` khi file vắng. Đổi tham chiếu đó không có file để trỏ. S3 không bịa ảnh.
- Thêm vào [.gitignore](.gitignore) đúng hai dòng còn thiếu: `.mira/` và `*.withheld/`. Không đụng `out/` và `out-*/` đã có.
- [docs/README.md](docs/README.md) khoảng 8 dòng: `PLAN.md` là plan vòng 1, `cach-dung-moi.txt` là ghi chú cài cũ, `chon_dat.sh` là script vẽ linh vật để lại từ vòng 1, `PLAN-2B.md` là plan sprint này. Nói rõ ảnh png không nằm trong repo.

Mở rộng [tests/test_repo_hygiene.py](tests/test_repo_hygiene.py). Sửa `r0/team.py` thành `mira/team.py` nếu S1 chưa kịp (S1 phải kịp). Thêm:

- `test_ten_file_khong_khoang_trang_hay_ngoac`: đi `git ls-files`, fail nếu tên basename chứa space, `(`, `)`, hoặc mã > 127. Bỏ qua `.git`.
- `test_khong_file_nang_ngoai_docs`: file tracked lớn hơn 200KB chỉ được nằm dưới `docs/`.
- `test_goc_khong_ansi_png_labels`: ở gốc repo, `git ls-files` không có `labels.csv`, không có tên kết thúc `.ansi` hoặc `.png`.

Ba test cũ `test_license_ton_tai`, `test_goc_khong_con_labels_csv_trong_git`, `test_compileall_team` giữ.

Lệnh:

```text
py -3 -m unittest discover -s tests -p "test_repo_hygiene.py" -v
py -3 -m mira selftest
py -3 -m r0 selftest
```

Ước lượng: khoảng 70 dòng test, 2 dòng gitignore, 8 dòng docs.

## 4. S4 — Máy gác commit

Một commit. Tiêu đề:

`[S4] Reject commit subjects that hide a BOM`

Công cụ [tools/check_commits.py](tools/check_commits.py), chỉ stdlib. Nhận một argument range `A..B`. Đọc `git log --format=%s%x00%H A..B`. Với mỗi tiêu đề:

- Khớp `^\[[A-Z0-9-]+\] \S`.
- Độ dài `len(msg) <= 72`.
- Không ký tự nào có `ord` thuộc `(0xFEFF, 0x200B, 0x200C, 0x200D, 0x2060)`.
- Fail thì exit 1, in hash ngắn và lý do tiếng Việt: thiếu ID, dài hơn 72, hoặc có ký tự ẩn kèm mã hex. Không in lại BOM như chữ thường mà in `U+FEFF`.
- Range rỗng: exit 0.
- Không gọi mạng.

Cách viết tiêu đề khi commit, trên PowerShell: Python `Path('.git/COMMIT_MSG.txt').write_text(msg, encoding='utf-8')` rồi `git commit -F`. Cấm `Set-Content -Encoding utf8` vì nó ghi BOM. Trước mỗi commit sprint chạy `py -3 tools/check_commits.py HEAD~1..HEAD` sau khi commit, và sửa bằng commit mới nếu fail, không amend commit đã push.

CI: job `commit-lint` trong [.github/workflows/test.yml](.github/workflows/test.yml). `pull_request` dùng `base.sha..sha`. `push` dùng `github.event.before..github.sha` khi `before` không phải 40 số 0. Push tạo nhánh mới bỏ qua lint thay vì fail trên range rỗng vô nghĩa. Job không `needs` unittest.

[CONTRIBUTING.md](CONTRIBUTING.md) thêm, tiếng Việt: mẫu tiêu đề, năm luật cũ giữ, bảng Phần B (package `mira`, shape tiếng Anh, commit ASCII), ví dụ đúng `[S4] Reject commit subjects that hide a BOM`, ví dụ sai là câu không ID và câu có dấu.

Test `tests/test_commit_lint.py` dùng repo git tạm, không đụng repo mira:

- `test_tieu_de_dung_thi_pass`: một commit `[S4] Add the lint`. Exit 0.
- `test_thieu_id_thi_fail`: tiêu đề `Add the lint`. Exit 1, stdout chứa `thieu`.
- `test_bom_thi_fail`: tiêu đề bắt đầu bằng `\ufeff[S4] Add the lint`. Exit 1, stdout chứa `U+FEFF`.
- `test_dai_hon_72_thi_fail`: `[S4] ` cộng 80 chữ `a`. Exit 1.
- `test_zero_width_thi_fail`: `[S4] Add\u200bthe lint`. Exit 1, stdout chứa `U+200B`.

Lệnh:

```text
py -3 -m unittest discover -s tests -p "test_commit_lint.py" -v
py -3 tools/check_commits.py HEAD~1..HEAD
py -3 -m mira selftest
py -3 -m r0 selftest
```

Ước lượng: khoảng 90 dòng tool, 80 dòng test, 25 dòng workflow, 40 dòng CONTRIBUTING.

## 5. S5 — Tài liệu

Một commit. Tiêu đề:

`[S5] Document the mira name and the home migration`

- [README.md](README.md): mọi lệnh chạy thành `mira` hoặc `python -m mira`. Một mục ngắn "Cấu trúc đặt tên" trỏ CONTRIBUTING. Một dòng, và chỉ một dòng, còn chữ `r0-shadow`: nó còn chạy được đến phiên bản kế tiếp rồi bị gỡ, và có in cảnh báo. `~/.r0` trong README đổi thành `~/.mira`. Đoạn migration nằm ở CHANGELOG, không nhét path cũ vào README.
- [CHANGELOG.md](CHANGELOG.md) mục Unreleased, nhóm Changed: package `mira`, shim `r0` và `r0-shadow` đến phiên bản kế tiếp, copy `~/.r0/keys.json` sang `~/.mira/keys.json` rồi đổi tên cũ thành `keys.json.migrated`, copy phiên thiếu sang `~/.mira/sessions` và giữ bản cũ.
- Dòng đầu [docs/PLAN.md](docs/PLAN.md): tên module `r0` trong tài liệu này nay là package `mira`.
- Không tạo `docs/PLAN-V2.md`.
- Đưa [docs/PLAN-2B.md](docs/PLAN-2B.md) vào commit này (file được ghi ngay sau khi duyệt, nằm trong cây từ đầu sprint).

Lệnh:

```text
py -3 -m mira selftest
py -3 -m r0 selftest
py -3 -m mira doctor
```

Grep nộp: `r0-shadow` trong README còn đúng một dòng deprecation. `\.r0/` trong README và docs không còn, trừ [docs/PLAN-2B.md](docs/PLAN-2B.md) và dòng chú thích đầu PLAN.md nếu dòng đó nhắc path cũ. Để grep Phần E sạch, dòng chú thích PLAN.md không chứa chuỗi `.r0/`. PLAN-2B được phép chứa vì nó là biên bản đối chiếu.

Ước lượng: khoảng 40 dòng README, 15 dòng CHANGELOG, 1 dòng PLAN, file plan này.

## 6. Bộ kiểm cuối Phần E

Chạy từ một thư mục tạm, không dùng `out/` có sẵn. Trên máy này `python3` thay bằng `py -3`.

```text
py -3 -m mira selftest
py -3 -m r0 selftest
git grep -nE "HOI_TOOLS|\"sua\"|chon_dat" -- mira tests pyproject.toml Dockerfile .github
git ls-files "*.png" "*.ansi" "chon_dat*"
git ls-files | findstr /R "("
py -3 tools/check_commits.py HEAD~5..HEAD
py -3 -m mira doctor
```

Kỳ vọng: hai selftest PASS, lần `r0` có cảnh báo, grep code 0, không png/ansi tracked tên chon_dat, không tên file có ngoặc, lint 5 commit sprint PASS, doctor in `~/.mira` và `môi trường OK`.

`git log -5 --format=%s` khớp `^\[S[1-5]\]`, mỗi dòng ASCII. `git show --stat S2` và các `git mv` eval không lẫn sửa `human_gate` hay `_executor_write`. S1 không thuần rename, đã ghi ở mục 0.

## 7. Việc không làm trong sprint này

- Không amend `205a671` hay `f308234`.
- Không mở P1, không làm INTAKE.
- Không thêm gói pip.
- Không đổi `t1a_policy`.
- Không tạo ảnh png mới.
- Không thêm `axis_vi`.
