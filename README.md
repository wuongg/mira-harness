# R0 shadow — harness đo lường cho SPEC đội nhóm agent

Chạy toàn bộ đường ống của SPEC (**T1a → T1b → T2 → sàn động → cổng người →
oracle/verifier → D1–D4 → sổ cái**) ở chế độ **shadow**: ghi log, **không hành động**.

Bản này tương ứng **SPEC v1.2.1** · CLI v1.15.0.

---

## Cài một lần — rồi gõ `mira`

Giống Claude Code: cài xong, mở terminal mới, gõ `mira` là vào phiên.
Không cần kích hoạt môi trường ảo, không cần đứng trong thư mục này.

```bat
install.bat
```

Linux / macOS: `python3 -m r0 install`

Lệnh này ghi `mira` vào `%USERPROFILE%\.local\bin` và thêm thư mục đó vào PATH.
Launcher là file `.cmd` gọi `python -m r0`, nên không dính file `mira.exe`
mà AppLocker trên Windows hay chặn.

Mở **terminal mới**, gõ:

```text
mira
```

## CHẠY NGAY — ba cách

### Cách 1 · một lệnh, tự lo hết (dễ nhất)

```bash
cd mira-install
./run.sh          # Linux / macOS
run.bat           # Windows (bấm đúp cũng được)
```

`run.sh` tự tạo môi trường ảo, cài, chạy `selftest`, rồi chạy shadow.

### Cách 2 · tự cài rồi dùng

```bash
cd mira-install
python3 -m venv .venv
source .venv/bin/activate        # Linux/macOS
.venv\Scripts\activate          # Windows
pip install -e .
mira                        # vào phiên — hoặc `python -m r0 install` để gõ được ở mọi terminal
```

### Cách 3 · không cài gì cả

```bash
python3 -m r0                    # vào phiên, chạy thẳng từ mã nguồn
python3 -m r0 selftest           # chạy bộ kiểm tra
```

---

## Vào phiên

Gõ **`mira`** rồi Enter — **không kèm tham số nào**. Lần đầu chưa có khoá API thì nó hỏi khoá, rồi vào phiên luôn.

Menu 4 việc vẫn còn, gọi riêng: `mira menu`.

Gõ **`mira menu`** nếu muốn danh sách việc:

```
  mira  harness R0
  ────────────────────────────────────────────────
  1  Chạy shadow (320 tác vụ)
  2  Xem báo cáo
  3  Sinh phiếu gán nhãn
  4  Xem phiếu đã điền được bao nhiêu
  5  Chấm bằng nhãn người đã điền
  s  Thống kê (bảng điều khiển)
  S  Thống kê — chọn chỉ số
  t  TUI toàn màn hình
  ...
  q  Thoát
```

Menu chỉ hiện khi gõ trong **terminal thật**. Nếu chuyển hướng đầu ra
(`mira > file.txt`) thì nó in trợ giúp thay vì vào phiên — vì không có bàn phím
để bấm.

---

## TUI toàn màn hình

```bash
mira run --out out      # phải có số trước đã
mira tui --run out      # mở TUI (màn hình thay thế, có chuột)
```

Trong TUI: `↑↓` cuộn · `tab` đổi mục · `1`–`5` nhảy mục · `enter` chi tiết ·
`r` nạp lại · `q` thoát.

Máy không có `curses` (Windows) hoặc không có TTY: dùng bản tĩnh

```bash
mira tui --run out --dump        # in một khung ra văn bản
mira stats --run out             # bảng điều khiển một màn hình
```

---

## 0. Cần gì

| Thứ | Yêu cầu |
|---|---|
| Python | **3.9 trở lên** (đã thử trên 3.12) |
| Thư viện ngoài | **KHÔNG có.** Chỉ thư viện chuẩn — không cần `pip install` gì thêm |
| Hệ điều hành | Linux · macOS · Windows |

---

## 1. Cài

```bash
cd mira-install
python3 -m venv .venv
source .venv/bin/activate          # Linux/macOS
.venv\Scripts\activate             # Windows
pip install -e .
```

Xong. Kiểm tra: `mira doctor` — phải báo **môi trường OK**.
Rồi `mira selftest` — phải **28 bài OK, 0 đỏ**.

Không muốn cài? Chạy thẳng: `python3 -m r0 <lệnh>`
Không có Python? `docker build -t mira . && docker run --rm -v "$PWD/out:/app/out" mira run`

---

## 2. Dùng nhanh nhất: menu

```bash
mira
```

Gõ số để chọn. Menu tự dẫn qua đúng thứ tự công việc:

```
  1. Chạy shadow (320 tác vụ)
  2. Xem kết quả dạng bảng
  3. Sinh phiếu gán nhãn
  4. Xem phiếu đã điền được bao nhiêu
  5. Chấm bằng nhãn người đã điền
  6. Đo độ nhạy cache (0% · 50% · 70%)
  7. Kiểm tra môi trường
  8. Kiểm tra bất biến (selftest)
  q. Thoát
```

*(Menu chỉ hiện khi chạy trong terminal thật. Chạy qua pipe thì in trợ giúp.)*

---

## 3. Dùng bằng lệnh

```bash
mira run                       # chạy shadow, in bảng kết quả
mira report                    # xem lại kết quả đã chạy
mira report --top 5            # kèm 5 tác vụ tốn kém nhất
mira task T0007                # xem chi tiết một tác vụ
mira labels export             # sinh phiếu gán nhãn
mira labels status             # đã điền bao nhiêu dòng
mira labels check              # kiểm tra phiếu hợp lệ
mira run --out out-lab --labels out/labels.csv   # chấm bằng nhãn người
mira compare --a out --b out-cache0              # so hai lần chạy
mira doctor                    # kiểm tra môi trường
mira selftest                  # kiểm tra bất biến
```

### Tùy chọn của `run`

| Cờ | Ý nghĩa |
|---|---|
| `--out DIR` | thư mục kết quả (mặc định `out`) |
| `--cache-hit 0.0…1.0` | tỉ lệ cache hit giả định (mặc định `0.9`) |
| `--seed N` | đổi seed ⇒ kết quả khác, dùng để kiểm độ ổn định |
| `--n N` | chỉ chạy N tác vụ đầu (chạy thử nhanh) |
| `--labels FILE` | chấm bằng nhãn NGƯỜI đã điền |
| `--json` | in số liệu thô thay vì bảng |
| `--quiet` | không in gì |

### Đầu ra

| Tệp | Nội dung |
|---|---|
| `out/trace.jsonl` | một dòng JSON mỗi tác vụ — toàn bộ quyết định, đủ để audit |
| `out/metrics.json` | 16 chỉ số §19 + khoảng Wilson + quy tắc 3/n |

Muốn máy đọc: `mira report --json`. Muốn tắt màu: `--no-color` hoặc `NO_COLOR=1`.
Màu cũng tự tắt khi ghi ra tệp: `mira report > bao-cao.txt`.

---

## 3b. Đội agent — giao một task, nó tự phân vai

Đây là phần **gọi model thật**. Đưa một yêu cầu, harness tự quyết định làn, tự
chẻ vai, chạy từng vai, rồi mới ghi kết quả — nếu qua được cổng.

```bash
# 1) xem kế hoạch phân vai, KHÔNG gọi model, KHÔNG tốn tiền
mira team "soạn báo cáo tổng kết quý" --dry-run

# 2) chạy thật (cần API key trong biến môi trường)
export ANTHROPIC_API_KEY=sk-ant-...
mira team "soạn báo cáo tổng kết quý" --records 5000 --out ket-qua

# 3) tác vụ ghi ra hệ thống ngoài — cổng tầng 2/3 sẽ hỏi duyệt
mira team "cập nhật 300 bản ghi lên CRM" --surface write_external \
  --labels confidential --records 300 --dollars 400 --out ket-qua
```

### Phân vai do CODE quyết, không do model quyết

| Làn | Vai được gọi |
|---|---|
| 0 | `worker` |
| 1 | `worker` → `verifier` |
| 2 | `planner` → `coordinator` → `worker` → `verifier` → `oracle` → `critic` |

Làn lấy từ chính logic của SPEC: bề mặt tool, nhãn dữ liệu, bồi hoàn, quy mô
→ `T1a` → sàn rủi ro → `T2`. Không có LLM nào tham gia vào việc chọn làn (I5).

### Cờ của `team`

| Cờ | Ý nghĩa |
|---|---|
| `--surface` | `read_only` · `write_sandbox` · `write_external` · `egress_new` |
| `--labels` | nhãn dữ liệu, do **bạn** khai (I3) — `public`, `internal`, `confidential`, `restricted` |
| `--records`, `--dollars` | quy mô, quyết định tầng cổng người |
| `--reversibility` | `C1` tự bồi hoàn · `C2` cần hành động · `C3` không bồi hoàn |
| `--dry-run` | in kế hoạch, không gọi model |
| `--provider` | `anthropic` · `openai` · `xai` (tự suy từ tên model nếu bỏ trống) |
| `--model` | ép một model cho mọi vai |
| `--base-url` | trỏ vào endpoint khác (dùng cho kiểm thử / model cục bộ) |
| `--approve` | duyệt cổng người không cần hỏi (dùng trong script) |
| `--out` | thư mục Executor ghi kết quả |

### Biến môi trường cho API key

```bash
ANTHROPIC_API_KEY=...   # cho model claude / opus / sonnet / haiku
OPENAI_API_KEY=...      # cho model gpt
XAI_API_KEY=...         # cho model grok
```

Key chỉ đọc từ môi trường — **không bao giờ** ghi ra tệp, không in ra màn hình.

### Fail-closed — điều quan trọng nhất

| Tình huống | Kết quả |
|---|---|
| Verifier trả `FAIL` | **Không ghi gì.** Hồ sơ lưu vào `withheld.json` |
| Oracle chấm < 0,70 | **Không ghi gì** |
| Cổng tầng 2/3 chưa duyệt | **Không ghi gì** |
| Thiếu API key | Dừng ngay, **không gọi** model nào |
| Vượt trần ngân sách làn | Dừng, giữ phần đã làm |

Cửa ghi duy nhất là hàm `_executor_write()` trong `r0/team.py` — không có đường
vòng nào khác (I1).

### Kiểm chứng không cần API key

Toàn bộ vòng lặp gọi model được kiểm bằng **server giả** chạy trong bộ test:
`tests/test_team.py` dựng một HTTP server cục bộ, chạy trọn 6 vai qua đó, và
kiểm cả nhánh `PASS` lẫn nhánh fail-closed. Nên bạn không phải là người chạy
thử đầu tiên.

```bash
mira selftest        # chạy tất cả, gồm cả test đội agent
```

---

## 3c. Agent CLI kiểu phiên làm việc (`chat` + `agent`)

Hai chế độ, giống cách các agent CLI quen thuộc chia việc:

```bash
mira chat                       # phiên tương tác (REPL)
mira chat --mode plan           # chỉ đề xuất, KHÔNG ghi, KHÔNG chạy lệnh
mira chat --team               # định tuyến qua làn + đội nhiều vai của SPEC
mira chat --resume 20261011-2201-ab12

mira agent "đọc README rồi tóm tắt"        # một lượt headless
mira agent "..." --json                    # envelope JSON cho script/CI
mira agent "..." --yes                     # tự duyệt mọi cổng (CẨN THẬN)

mira agent "..." --protocol native         # ép gọi công cụ GỐC (native tool-calling)
mira agent "..." --protocol text           # ép giao thức văn bản <tool>{...}</tool>
mira agent "..." --no-stream               # tắt streaming (dễ ghi log)
mira agent "..." --max-turns 8             # trần vòng gọi công cụ (mặc định 25)
mira agent "..." --max-budget-usd 0.50     # dừng ngay khi lượt vượt $0,50
mira team "..." --workers 4                # làn 2: 4 worker + 4 verifier song song
mira team "..." --workers 2 --sub-depth 2  # mỗi worker mở đội con, lồng 2 cấp
```

### Trong phiên, gõ `/` để điều khiển

| Lệnh | Việc |
|---|---|
| `/help` | danh sách lệnh |
| `/mode plan\|default\|acceptEdits\|bypass` | đổi mức quyền |
| `/model <tên>` | đổi model |
| `/team on\|off` | bật định tuyến theo làn + đội nhiều vai |
| `/tools` | các công cụ agent có |
| `/cost` | token và chi phí phiên |
| `/audit` | đã ghi gì, đã chạy gì |
| `/clear` · `/save` · `/sessions` · `/resume <id>` | ngữ cảnh và phiên |
| `/exit` | thoát |

### Công cụ agent có

| Công cụ | Xin phép? |
|---|---|
| `read_file` · `list_dir` · `grep` | không |
| `write_file` | **có** (trừ `acceptEdits`) |
| `run_shell` | **luôn luôn** |
| `finish` | không |

Mọi đường dẫn bị khoá trong `--cwd`. Thoát ra ngoài bằng `../` bị từ chối.
Trong chế độ `plan`, `write_file` và `run_shell` trả về "BỊ CHẶN" — agent được
yêu cầu trình bày đề xuất thay vì tự làm.

### Bốn mức quyền

| Chế độ | Đọc | Ghi tệp | Chạy lệnh |
|---|---|---|---|
| `plan` | có | **chặn** | **chặn** |
| `default` | có | hỏi | hỏi |
| `acceptEdits` | có | tự duyệt | hỏi |
| `bypass` | có | tự duyệt | tự duyệt |

### Giao thức gọi công cụ: `native` hay `text`

Mặc định `--protocol auto`: với `anthropic`/`openai`/`xai` dùng **native
tool-calling** (model trả khối `tool_use` / `tool_calls` có cấu trúc, không
phải văn bản), các nhà cung cấp khác rơi về giao thức văn bản.

| | `native` | `text` |
|---|---|---|
| Định dạng | khối JSON có cấu trúc của hãng | model tự viết `<tool>{...}</tool>` |
| Nhiều công cụ / lượt | **có, chạy song song** | tuần tự, mỗi lượt một |
| Độ bền | cao — không phụ thuộc model chịu viết đúng thẻ | thấp hơn — model có thể viết sai cú pháp |
| Cần gì | provider hỗ trợ tool-calling | chạy được ở mọi provider |

Cả hai đều đi qua **cùng** vòng lặp cổng xin phép, cùng khoá đường dẫn, cùng
sổ audit — đổi giao thức không nới bất kỳ bất biến nào.

### Hai van an toàn: trần lượt và trần ngân sách

`--max-turns` và `--max-budget-usd` đếm bằng CODE từ token đã tiêu — không hỏi
model, không nằm trong prompt (đúng I8). Vượt ngưỡng thì dừng ngay và trả
`status` là `stopped_turns` hoặc `stopped_budget`, kèm trường `stopReason`.

| Van | Mặc định | Khi vượt |
|---|---|---|
| `--max-turns N` | 25 | dừng sau đúng N vòng gọi công cụ |
| `--max-budget-usd X` | không giới hạn | dừng ngay khi chi phí lượt ≥ X |

Van chỉ CHẶN, không nới: dừng vì van vẫn đi qua đúng cổng xin phép và vẫn ghi audit.

### Làn 2 chạy song song

`team ... --workers N` cho làn 2 chạy N worker rồi N verifier SONG SONG (thread
pool). Chỉ THỜI GIAN đổi — mọi cổng, khoá đường dẫn và fail-closed vẫn nguyên,
vì chúng do code quyết chứ không do model. Sổ cái được khoá khi ghi nên I8 vẫn đúng.

Đo bằng provider giả (mỗi shard 0,4s), cùng một kế hoạch làn 2:

| N shard | tuần tự | song song | nhanh hơn | đỉnh đồng thời |
|---|---|---|---|---|
| 1 | 0,50s | 0,50s | 1,00× | 1 |
| 3 | 1,34s | 0,50s | 2,67× | 3 |
| 5 | 2,19s | 0,51s | 4,32× | 5 |
| 8 | 3,45s | 0,50s | **6,84×** | 8 |

Thứ tự bước trả về vẫn theo chỉ số (planner → coordinator → worker×N → verifier×N
→ oracle → critic) nên hình dạng kết quả tất định; nội dung do model sinh nên vẫn ngẫu nhiên.

### Đội con lồng nhau (`--sub-depth`)

`team ... --sub-depth N` cho mỗi worker ở **làn 2** mở một đội con có verifier
riêng. Đội con **KHÔNG được cấp trần mới** — nó chỉ nhận một phần trần *còn lại*
của cha:

```
trần cha $2,46  ─┬─ đội con #1  ≤ 50% còn lại
                 ├─ đội con #2  ≤ 50% còn lại
                 └─ …
```

Vì `share = 50%` và **sổ cái dùng chung cả cây**, tổng chi của cả cây không thể
vượt trần cha: cấp con giảm theo cấp số nhân, và cổng chặn cuối vẫn là trần của cha.

| Quy tắc | Giá trị | Vì sao |
|---|---|---|
| Phần trần cấp cho một đội con | 50% trần **còn lại** | con không thể vượt cha (I8) |
| Đội con làn nào | làn 2 nếu còn độ sâu, ngược lại làn 1 | làn 1 luôn có verifier riêng |
| Làn nào được mở đội con | **chỉ làn 2** | làn 0/1 giữ đúng định nghĩa 1 agent / 1 cặp |
| Trần cứng số đội con | 12 mỗi cây | chặn bùng nổ |
| Verifier con FAIL | **cả lượt bị giữ lại** | đọc chặt của I2: đội con chưa qua kiểm thì không giao |

Điểm cuối là điểm dễ hiểu sai nhất: kể cả khi verifier **cha** chấm PASS, chỉ cần
một đội con không qua kiểm là cả lượt bị `withheld`. Đội con chưa kiểm được thì
kết quả của nó cũng chưa kiểm được.

### T1b đọc NỘI DUNG, không rút thăm

Classifier **không đọc `truth`**. Nó quét chính `observable["content"]` — email/tài
liệu mà hệ thống thật sự đọc — bằng một bộ dò tất định (từ khoá + mẫu địa chỉ ngoài).
Nhờ vậy recall/precision trở thành **số đo được**, thay vì hệ quả của một con số cấu hình.

| Bằng chứng khớp | Nghĩa | Độ tin |
|---|---|---|
| ghi đè chỉ dẫn | "bỏ qua hướng dẫn" + hành động | |
| chỉ dẫn nhắm vào agent | "trợ lý/agent" + động từ gửi | |
| gửi tới địa chỉ ngoài | động từ gửi + email/IP/URL ngoài | |

Độ tin **là hàm của số bằng chứng** (1 → 0,72 · 2 → 0,86 · 3 → 0,94), nên hiệu chuẩn
mới có nghĩa. Bộ dò **cố ý không hoàn hảo** — có dạng bị bỏ sót (chỉ đổi endpoint,
không có động từ gửi) và có dạng báo nhầm (câu lành tính chứa "trợ lý" + "gửi").
Đó là cái giá thật của một bộ dò từ khoá, và là lý do precision phải đo chứ không giả định.

### Envelope JSON của `agent --json`

```json
{ "ok": true, "status": "ok", "final": "...",
  "usage": {"input": 120, "output": 40, "total": 160},
  "costUsd": 0.0012, "assistantTurns": 2,
  "toolSummary": {"calls": 1, "tools": ["read_file"]},
  "model": "...", "provider": "...", "protocol": "native", "sessionId": "...",
  "mode": "default", "stopReason": null, "audit": [] }
```

Mã thoát: `0` xong · `1` lỗi/chặn · `2` đầu vào sai.

### Phiên lưu ở đâu

`~/.r0/sessions/<id>.jsonl` — mỗi dòng một sự kiện. `/sessions` liệt kê, `/resume <id>` mở lại.

---

## 4. Tự kiểm tra các bất biến

```bash
mira selftest
```

| Bài kiểm tra | Bất biến / tuyên bố |
|---|---|
| hai lần chạy trùng khít | số đo **tái lập được** (mỗi thành phần một luồng ngẫu nhiên) |
| shadow không hành động | I1, I2 — fail-closed |
| nhãn lấy từ nguồn | I3 |
| sàn không dưới mức quyền đòi hỏi | I4 |
| không hạ sàn khi chưa qua thời gian thử | đường hạ sàn đóng |
| cổng trả về số, 1..3 | I5 — cổng là code |
| sàn 3 ⇒ bắt buộc 2 người duyệt | cổng người |
| dự phòng kiểm tồn tại và < trần | I8 |
| phiếu gán nhãn không chứa `truth` | nhãn người không bị nhiễm |
| ô nhãn để trống | không đoán hộ |
| phiếu xếp theo `task_id` | thứ tự dòng không lộ tầng |

---

## 5. Cấu trúc

```
mira-install/
├── pyproject.toml          # gói cài được, console script `mira`
├── Makefile                # make install | test | run | labels
├── run.sh / run.bat        # chạy một phát, tự tạo venv
├── Dockerfile              # tự chạy selftest lúc build
├── labels.csv              # phiếu gán nhãn 320 dòng (bản mẫu)
├── r0/
│   ├── cli.py              # dòng lệnh + menu tương tác
│   ├── ui.py               # bảng, màu, thanh tiến độ (thuần thư viện chuẩn)
│   ├── config.py           # ngưỡng, giá model, mô hình dùng lượng token
│   ├── tasks.py            # bộ tác vụ 8 tầng  ← ĐIỂM THAY THẾ sang nhãn người
│   ├── pipeline.py         # T1a, sàn động, T1b, T2, cổng người, oracle, D1–D4, sổ cái
│   ├── metrics.py          # 16 chỉ số + Wilson + quy tắc 3/n
│   └── labels.py           # xuất/đọc phiếu gán nhãn
└── tests/test_invariants.py
```

### Muốn sửa thì sửa ở đâu

| Muốn đổi | Sửa tệp |
|---|---|
| Ngưỡng, giá model, mô hình token | `r0/config.py` |
| Bộ tác vụ mẫu | `r0/tasks.py` — hàm `load_tasks()` |
| Logic đường ống | `r0/pipeline.py` |
| Chỉ số báo cáo | `r0/metrics.py` |
| Thêm lệnh CLI | `r0/cli.py` |

---

## 6. CẢNH BÁO — đọc trước khi tin bất kỳ con số nào

Nhãn trong `tasks.py` là **NHÃN TỔNG HỢP do code sinh**, **KHÔNG phải nhãn người**.
Harness này kiểm chứng **đường ống đo**, không kết luận về ngưỡng sản xuất.

Những gì **KHÔNG** được chứng minh:

- Tỉ lệ đúng/sai chỉ là đúng/sai **so với luật sinh nhãn**.
- T1b là **stub tất định**, không phải model thật ⇒ đường hiệu chuẩn là của stub.
- Độ trễ và token là **mô phỏng** theo `config.USAGE`, không phải đo thật.
- Mẫu **phân tầng theo rủi ro** ⇒ phân bố làn **không phải** tỉ lệ sản xuất.
- Nhánh **hạ sàn chưa hề chạy** (0/151 lượt) ⇒ nửa tá số liên quan vẫn trống.

Muốn có số thật: điền cột `human_injection` (`yes`/`no`) trong `labels.csv` rồi chạy
`mira run --out out-lab --labels labels.csv`.

---

## 7. Giấy phép

MIT.
