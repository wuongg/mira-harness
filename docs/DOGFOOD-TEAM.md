# Dogfood đội web — khách đặt một trang giới thiệu frog

Đơn của khách: "Tôi cần một trang web giới thiệu frog để gửi cho bạn bè xem."

Vòng 1 chạy trên code `85c40c0` (sau [PROV-9R], trước [S-ROLES]).
Môi trường: venv mới `dogfood-team-r1`, HOME riêng, không có khóa trả phí nào trong môi trường.
Provider giả: `tools/fake_9router.py` ở `127.0.0.1:18990` đóng vai 9router (trả lời theo kịch bản cố định, không phải model).
Bản chậm ở `127.0.0.1:18991` ngủ 8 giây ở vai `worker` để thử hủy giữa chừng.
Mọi số giây là đồng hồ ngoài của lệnh đã chạy. Không có lượt gọi model thật nào trong vòng 1.

## Hành trình vòng 1

| bước | lệnh | kết quả | giây |
| --- | --- | --- | --- |
| cài | `python -m venv` rồi `python -m pip install -e .` | exit 0 | 7.5 + 9.8 |
| doctor | `python -m frog doctor` | "môi trường OK", 9router không kết nối được ở 20120 | 4.6 |
| đơn, không cờ | `frog team "<đơn>"` | làn 0, 1 vai `worker sonnet-5.5`, chặn vì thiếu `ANTHROPIC_API_KEY` | 0.3 |
| thêm provider | `frog team --provider 9router "<đơn>"` | vẫn gửi `sonnet-5.5`, 9router báo không có model, liệt kê model gần nhất | 0.4 |
| thêm model | `... --model cu/gpt-5.6-sol-high "<đơn>"` | "đã làm", hỏi cổng ghi dù không có `--out` | 0.3 |
| thêm out | `... --out site "<đơn>"` + `y` | ghi `site/<giờ-mã>/result.md`, không có `index.html` | 0.4 |
| diễn đạt 2 | `"làm cho tôi 1 trang web của frog"` | 1 vai | 0.4 |
| diễn đạt 3 | `"tôi muốn frog có trang chủ"` | 1 vai | 0.3 |
| đơn lớn | `"trang giới thiệu kèm form đăng ký nhận tin, lưu danh sách email"` + `y`,`y` | làn 1, 2 vai `worker`,`verifier` cùng model, 4 lượt gọi | 0.5 |
| dặn thêm | đơn + "Hãy lập đội như một công ty làm web: PM, thiết kế, lập trình, kiểm thử, bàn giao." | vẫn 1 vai | 0.4 |
| gõ sai lệnh | `frog teem "<đơn>"` | dump argparse, không gợi ý `team` | 0.3 |
| gõ sai cờ | `frog team --provder 9router "<đơn>"` | "unrecognized arguments: --provder <cả câu đơn>" | 0.3 |
| thiếu khóa | bỏ `NINE_ROUTER_API_KEY` | "thiếu key cho 9router — đặt NINE_ROUTER_API_KEY (khóa ở trang Endpoint & Key của 9router)…" | 0.3 |
| hủy giữa chừng | Ctrl+C (ngắt main thread ở giây 3) khi `worker` đang chờ | traceback Python, exit -1073741510, thoát ở giây 8.5 | 8.5 |
| chạy tiếp | `frog team --resume 0864df47bca1 ...` + `y` | chạy tiếp và ghi được | 0.4 |

Số vai qua tay: đơn nhỏ 1 vai, đơn lớn 2 vai. Phải đoán 3 cờ (`--provider`, `--model`, `--out`) và 4 lần gõ lệnh mới có file.
Không có cách nào khiến đội phân vai như công ty, kể cả khi dặn thẳng trong đơn.

## Vết

Trạng thái: `còn tồn` là chưa sửa. `đã sửa` chỉ ghi sau khi chạy lại trên venv sạch mới, kèm lệnh và giây.

| id | bước | chuyện gì | vì sao ngứa | đề xuất | mức | trạng thái |
| --- | --- | --- | --- | --- | --- | --- |
| T-01 | đơn, không cờ | Đơn web ra đúng 1 vai `worker` (làn 0). Không PM, không thiết kế, không QA, không bàn giao | Không ai thiết kế, không ai kiểm, không ai giao | Tuyển vai từ danh mục theo cỡ đơn | P0 | còn tồn |
| T-02 | đơn, không cờ | Không có quyết định có backend hay không, không có danh sách vai đã cân nhắc mà không tuyển | Khách không biết đội đã nghĩ tới bảo mật, triển khai hay chưa | Sơ đồ 2 phần: đã tuyển + lý do, không tuyển + lý do, kèm quyết định backend | P0 | còn tồn |
| T-03 | đơn, không cờ | Không có bước đề xuất sơ đồ nhân sự cho khách duyệt. Làn 0 tắt intake và chạy luôn | Khách không thêm bớt vai được trước khi tốn quota | Trình sơ đồ trong brief, duyệt brief là duyệt nhân sự | P0 | còn tồn |
| T-04 | dặn thêm | Dặn thẳng "lập đội như công ty: PM, thiết kế, lập trình, kiểm thử, bàn giao" vẫn ra 1 vai | Lời khách không đổi được đội | Đội đọc đơn qua intake, khách sửa bằng `--hire`/`--drop` | P0 | còn tồn |
| T-05 | đơn lớn | Form lưu email chỉ thêm `verifier` vì chữ "email" kích hoạt cờ nội dung không tin (sàn 2). Không backend, không `security_reviewer` | Dữ liệu người dùng mà không ai lo lưu trữ và bảo mật | Luật cỡ đơn: form lưu dữ liệu là đơn vừa, bắt buộc `backend_api_engineer` và `security_reviewer` | P0 | còn tồn |
| T-06 | đơn, không cờ | Chỉ có khóa 9router mà đội đòi `ANTHROPIC_API_KEY` vì model mặc định là `sonnet-5.5` | Khách có khóa vẫn bị chặn | Có khóa 9router thì vai làm dùng `cu/gpt-5.6-sol-high`, vai kiểm dùng `cu/claude-opus-5-thinking-high` | P0 | còn tồn |
| T-07 | thêm provider | `--provider 9router` vẫn gửi `sonnet-5.5`. Lỗi có liệt kê model gần nhất nhưng khách phải đoán `--model` | Thêm một vòng đoán | Như T-06 | P1 | còn tồn |
| T-08 | thêm model | `--model` ép một model cho mọi vai, nên `worker` và `verifier` cùng họ | Người kiểm cùng họ với người làm, mất độc lập | Model theo nhóm vai, mặc định khác họ khi đi 9router | P1 | còn tồn |
| T-09 | thêm model | "đã làm" khi không có vai kiểm nào | Trạng thái đẹp hơn sự thật | Đơn web bắt buộc có vai review, review gate cả ở làn 0 | P1 | còn tồn |
| T-10 | thêm model | Không có `--out` mà vẫn hỏi "Cổng tầng 2 — duyệt để ghi?" | Duyệt xong cũng không ghi gì | Không hỏi cổng khi không có chỗ ghi, nói rõ cần `--out` | P1 | còn tồn |
| T-11 | thêm out | Bàn giao là `site/<giờ-mã>/result.md`, HTML nằm trong khối code kèm nhãn "NỘI DUNG KHÔNG TIN" | Khách phải tự chép HTML ra file mới mở được trang | Executor tách khối ` ```html site/index.html ` ra file trong `--out` sau cổng | P1 | còn tồn |
| T-12 | đơn lớn | Brief in ra một dòng JSON | Khách không đọc được thứ mình đang duyệt | In brief dạng mục | P1 | còn tồn |
| T-13 | đơn, không cờ | Đơn mơ hồ ("gửi bạn bè") không có câu hỏi làm rõ nào vì làn 0 tắt intake | Không ai hỏi ngôn ngữ, thiết bị, nội dung chính | Đơn web luôn qua intake, intake được dặn hỏi đối tượng và ngôn ngữ | P1 | còn tồn |
| T-14 | doctor | "môi trường OK" khi không nhà cung cấp nào dùng được | Khách tưởng chạy được | Doctor đếm nhà cung cấp dùng được | P1 | còn tồn |
| T-15 | doctor | Cổng mặc định 20120 không trả lời trên máy này, 9router đang ở 20128 | Lần đầu luôn hỏng nếu không đặt `NINE_ROUTER_BASE_URL` | Chủ repo xác nhận cổng. Lỗi doctor nhắc 20128 là cổng mặc định của 9router | P1 | còn tồn |
| T-16 | README | README không nhắc 9router, `NINE_ROUTER_API_KEY`, `NINE_ROUTER_BASE_URL` | Phải đợi doctor báo lỗi mới biết tên biến | Quickstart có mục 9router | P1 | còn tồn |
| T-17 | gõ sai lệnh | `frog teem` không gợi ý `team`. Gợi ý cũ chỉ so ba ký tự đầu | Lỗi gõ phổ biến không được đỡ | Gợi ý bằng độ gần chuỗi | P1 | còn tồn |
| T-18 | gõ sai cờ | `--provder` báo "unrecognized arguments: --provder <cả câu đơn>", không gợi ý `--provider` | Câu đơn bị lẫn vào lỗi | Gợi ý cờ gần nhất | P1 | còn tồn |
| T-19 | hủy giữa chừng | Ctrl+C in traceback Python, exit -1073741510, không nói đã dừng hay cách chạy tiếp | Khách tưởng hỏng, không biết `--resume` | Bắt Ctrl+C, in "đã dừng — chạy tiếp: frog team --resume <id>" | P1 | còn tồn |
| T-20 | hủy giữa chừng | Ctrl+C ở giây 3 nhưng lệnh thoát ở giây 8.5, khi model trả lời xong | Hủy không dừng ngay | Ghi rõ trong thông báo dừng. Gọi HTTP trên Windows không bị ngắt giữa chừng | P2 | còn tồn |
| T-21 | chạy tiếp | Dòng chi phí "uncertain (subscription quota) · 1 lượt · uncertain · 1 lượt". Lượt bị ngắt mất nhãn gói thuê bao | Một lượt quota thành hai loại | Lượt 9router bị ngắt giữ nhãn gói thuê bao | P2 | còn tồn |
| T-22 | hủy giữa chừng | Checkpoint của run bị ngắt ghi `status: ok` với 0 bước | Trạng thái lệch sự thật | Ghi `interrupted` | P2 | còn tồn |
| T-23 | đơn, không cờ | Biệt ngữ: "T1a xếp làn cơ sở 0 theo bề mặt tool read_only + bồi hoàn C1", "Capability read", "fail-closed (I2)" | Khách không hiểu | Dòng tiếng thường cho khách, chi tiết vào trace | P2 | còn tồn |
| T-24 | thiếu khóa | Chưa gọi model nào mà vẫn in "Chi phí $0.000000 · 0+0 tok" | Đọc như 9router miễn phí | In "chưa gọi model" | P2 | còn tồn |
| T-25 | thêm provider | Lượt 9router báo không có model vẫn ghi "uncertain (subscription quota) · 1 lượt" | Có thể chưa tốn quota | Giữ uncertain là đúng luật, ghi lý do 9router từ chối | P2 | còn tồn |
| T-26 | đơn lớn | Trả "y" qua pipe UTF-8 có BOM bị coi là không duyệt, im lặng | Trên PowerShell 5.1 không duyệt được | Bỏ ký tự vô hình trước khi so câu trả lời | P2 | còn tồn |
| T-27 | đơn lớn | "chưa duyệt brief — không chạy planner." khi đội không có planner | Thông báo sai vai | "không chạy đội" | P2 | còn tồn |
| T-28 | thêm out | Thư mục con theo giờ `site\20261020-101147-6281b2\` | Khách phải đi tìm file | In đường dẫn đầy đủ của file chính | P2 | còn tồn |

## Vòng 2 — sau [S-ROLES] `e7bab57`

Môi trường: venv mới `dogfood-team-r2`, HOME riêng, không khóa trả phí. 9router giả khởi động lại bằng code mới, bản chậm ngủ 8 giây ở `frontend_engineer`.

| bước | lệnh | kết quả | giây |
| --- | --- | --- | --- |
| cài | `python -m venv` rồi `python -m pip install -e .` | exit 0 | 6.3 + 9.3 |
| đơn, không cờ | `frog team "<đơn>"` | vẫn chặn: "thiếu khóa cho intake (model opus-5.5, nhà anthropic)… thêm --intake-model…" | 0.3 |
| provider 9router | `frog team --provider 9router "<đơn>"` + `y` | sơ đồ 2 phần: 5 vai tuyển, 14 vai không tuyển kèm lý do, backend KHÔNG; vai làm `cu/gpt-5.6-sol-high`, vai kiểm `cu/claude-opus-5-thinking-high`; 6 lượt gọi; "đã làm" sau khi `qa_reviewer` PASS | 0.5 |
| khách thêm vai | `--hire security_reviewer,content_writer --out site` + `y`,`y` | 7 vai, nguồn "khách"; 8 lượt gọi; `result.md` có 7 mục theo vai; vẫn không có `index.html` | 0.6 |
| bỏ vai bắt buộc | `--drop qa_reviewer` | "không bỏ được qa_reviewer: bắt buộc với đơn nhỏ", exit 8 | 0.3 |
| 3 diễn đạt | 3 câu đơn nhỏ | cùng 5 vai, cùng nguồn | 0.5 mỗi lần |
| đơn lớn | form lưu email | intake giả nói "nhỏ", code nâng "vừa"; thêm `backend_api_engineer`, `integration_engineer`, `security_reviewer`, `content_writer`; 9 vai; backend CÓ | 0.5 |
| gõ sai | `frog teem`, `--provder` | như vòng 1, không gợi ý | 0.3 |
| thiếu khóa | bỏ `NINE_ROUTER_API_KEY` | "thiếu khóa cho intake (model cu/gpt-5.6-sol-high, nhà 9router). Gõ frog keys set --provider 9router. Hoặc đặt NINE_ROUTER_API_KEY." | 0.3 |
| hủy giữa chừng | Ctrl+C ở giây 3 khi `frontend_engineer` chờ | traceback, exit -1073741510, thoát ở giây 8.6 | 8.6 |
| chạy tiếp | `--resume 76a7c879158c --provider 9router` | `frontend_engineer` gửi `sonnet-5.5` sang 9router và lỗi | 0.4 |

Vết mới vòng 2:

| id | bước | chuyện gì | vì sao ngứa | đề xuất | mức | trạng thái |
| --- | --- | --- | --- | --- | --- | --- |
| T-29 | đơn, không cờ | Gợi ý thiếu khóa của `team` bảo thêm `--intake-model`, cờ chỉ có ở `giao`; không nhắc 9router | Làm theo gợi ý thì lại lỗi cờ | Gợi ý theo đúng lệnh, nhắc 9router | P1 | còn tồn |
| T-30 | provider 9router | 13 vai không tuyển dùng chung một lý do "đơn nhỏ: trang tĩnh…", kể cả `security_reviewer` và `content_writer` mà luật bảo phải cân nhắc | Lý do không nói gì về vai đó | Lý do riêng từng vai, nói khi nào nên `--hire` | P1 | còn tồn |
| T-31 | chạy tiếp | Chạy tiếp đơn web qua 9router không giữ model theo nhóm vai, gửi `sonnet-5.5` | Không chạy tiếp được | Resume dùng cùng model theo nhóm như lần đầu | P1 | còn tồn |
| T-32 | provider 9router | Bảng sơ đồ rộng hơn 200 cột, xuống dòng | Khó đọc trên terminal thường | Cắt cột lý do, bỏ cột trùng | P2 | còn tồn |
| T-33 | bỏ vai bắt buộc | `--drop` vai bắt buộc chỉ bị từ chối sau một lượt intake | Tốn một lượt quota | Kiểm `--drop` trước khi gọi intake | P2 | còn tồn |
| T-34 | provider 9router | Danh sách không tuyển xếp theo danh mục, vai luật bảo cân nhắc nằm lẫn | Khó thấy vai đáng cân nhắc | Vai cần cân nhắc lên đầu | P2 | còn tồn |

Trạng thái vết vòng 1 sau vòng 2 (chạy lại trên `dogfood-team-r2`):

| id | trạng thái | bằng chứng |
| --- | --- | --- |
| T-01 | đã sửa | `frog team --provider 9router "<đơn>"`: 5 vai từ danh mục, 0.5 giây |
| T-02 | đã sửa | cùng lệnh: bảng "Đã cân nhắc, không tuyển 14 vai" và dòng "Backend KHÔNG · trang tĩnh…" |
| T-03 | đã sửa | cùng lệnh: "Duyệt brief và sơ đồ nhân sự này? [y/N]" trước THỰC THI |
| T-04 | đã sửa | `--hire security_reviewer,content_writer`: 7 vai, nguồn "khách", 0.6 giây |
| T-05 | đã sửa | đơn lớn: code nâng cỡ "vừa", thêm `backend_api_engineer` và `security_reviewer`, 0.5 giây |
| T-09 | đã sửa | "đã làm" chỉ in sau "qa_reviewer PASS"; bài `test_vai_kiem_fail_thi_khong_ban_giao` |
| T-27 | đã sửa | thông báo đổi thành "chưa duyệt brief — không chạy đội" |
| T-06, T-07 | còn tồn | không cờ vẫn đòi khóa Anthropic (sửa ở vòng 3/4) |
| T-08 | sửa một phần | đi 9router thì vai làm và vai kiểm khác họ; `--model` vẫn ép mọi vai, theo thiết kế |
| T-13 | chưa kiểm | đơn web đã luôn qua intake; câu hỏi làm rõ chưa thử trên giả |
| còn lại | còn tồn | chưa sửa ở vòng này |

## Vòng 3 — sau [UX-6] `b195bcb`

Môi trường: `dogfood-team-r3`, chỉ `NINE_ROUTER_API_KEY`, giả ở `18990`.

| bước | lệnh | kết quả | giây |
| --- | --- | --- | --- |
| đơn, không cờ | `frog team "<đơn>"` + `y` | "chỉ có khóa NINE_ROUTER_API_KEY nên đội đi 9router"; 5 vai; đã làm | ~0.5 |
| FAKE_ASK | cùng + `FAKE_ASK=1` | intake hỏi tiếng Việt/thiết bị trước khi tuyển | ~0.5 |

## Vòng 4 — sau [UX-7] `09bcc6f`

Môi trường: venv mới `dogfood-team-r4`, HOME `dogfood-team-r4-home`, chỉ khóa 9router giả (đã gỡ `ANTHROPIC_*` / `OPENAI_*` khỏi tiến trình). Giả `127.0.0.1:18990`.

| bước | lệnh | kết quả | giây |
| --- | --- | --- | --- |
| bare | `frog team "<đơn>"` + `y` | đội đi 9router; brief dạng mục; 5 vai; "Không có --out nên không ghi…"; exit 0 | 0.5 |
| no-out | `--provider 9router` + `y` | như trên, không hỏi cổng ghi | 0.5 |
| with-out | `… --out site` + `y`,`y` | ghi `files/site/index.html`; in đường dẫn đầy đủ; 1 file bàn giao | 0.5 |
| big | form lưu email + `--out big` | 9 vai, backend CÓ, nâng cỡ vừa; `index.html` | 0.6 |
| hire | `--hire security_reviewer,content_writer` | 7 vai; `index.html` | 0.5 |
| ask | `FAKE_ASK=1` | có câu hỏi làm rõ | 0.5 |
| typo | `frog teem`, `--provder` | gợi ý `team` / `--provider` | 0.3 |
| doctor | `frog doctor --base-url …18990` | "nhà cung cấp có khóa: 9router"; môi trường OK | 0.5 |

Trạng thái vết sau vòng 4:

| id | trạng thái | bằng chứng |
| --- | --- | --- |
| T-06, T-07 | đã sửa | bare chỉ khóa 9router → đội đi 9router, không đòi Anthropic |
| T-08 | sửa một phần | như vòng 2; `--model` vẫn ép mọi vai |
| T-10 | đã sửa | bare/no-out: "Không có --out…" exit 0 |
| T-11, T-28 | đã sửa | `files/site/index.html` + đường dẫn đầy đủ |
| T-12 | đã sửa | BRIEF in Mục tiêu / Bàn giao / … |
| T-13 | đã sửa | `FAKE_ASK=1` hỏi tiếng Việt/thiết bị |
| T-14 | đã sửa | doctor liệt kê nhà cung cấp có khóa |
| T-15 | sửa một phần | doctor nhắc thử 20128 khi mặc định 20120 chết; mặc định code vẫn 20120 |
| T-16 | đã sửa | README Quickstart có mục 9router |
| T-17, T-18 | đã sửa | gợi ý lệnh/cờ gần nhất |
| T-19 | đã sửa (code) | `KeyboardInterrupt` → exit 130 + `--resume`; chưa dogfood Ctrl+C lại trên r4 |
| T-29 | đã sửa | `_key_hint(..., command="team")` không nhắc `--intake-model` |
| T-30, T-34 | đã sửa | lý do riêng + vai cân nhắc xếp trước |
| T-31 | đã sửa (code) | resume truyền `role_models` / staffing checkpoint |
| T-20…T-26, T-32, T-33 | còn tồn | chưa đụng vòng này |

## [S-TEAM] A/B giả + bảng cỡ đơn

Provider giả, cùng `FAKE_STAFF=lazy`. Ba diễn đạt đơn nhỏ:

| lần | diễn đạt | exit | giây | chuỗi vai (bước thực thi) |
| --- | --- | --- | --- | --- |
| A | trang giới thiệu frog gửi bạn bè | 0 | 0.5 | product_manager → ux_designer → frontend_engineer → qa_reviewer → handoff_editor |
| B | làm cho tôi 1 trang web của frog | 0 | 0.4 | cùng chuỗi |
| C | tôi muốn frog có trang chủ | 0 | 0.4 | cùng chuỗi |

Ổn định: **CÓ** — cùng 5 vai, cùng thứ tự.

Bảng cỡ đơn (settle + luật `REQUIRED`, proposal intake kiểu lazy 3 vai rồi code bổ sung):

| cỡ | tín hiệu đơn | số vai | vai chính |
| --- | --- | --- | --- |
| nhỏ | trang web giới thiệu | 5 | product_manager, ux_designer, frontend_engineer, qa_reviewer, handoff_editor |
| vừa | form đăng ký + lưu email | 9–10 | + content_writer, backend_api_engineer, integration_engineer, security_reviewer (± devops) |
| lớn | đăng nhập + thanh toán | 14 | + project_coordinator, backend_db_engineer, devops, perf, a11y, … |

Sơ đồ nhân sự cuối (đơn nhỏ mặc định, giả r4):

```
Đã tuyển 5: product_manager, ux_designer, frontend_engineer, qa_reviewer, handoff_editor
Backend: KHÔNG · trang tĩnh
Đã cân nhắc, không tuyển 14: content_writer / security_reviewer / devops… (lý do riêng; cân nhắc lên đầu)
```

## Chạy thật 9router (`127.0.0.1:20128`)

Khóa lấy từ `apiKeys` active trong DB cục bộ của 9router (không ghi vào sổ). Mặc định sản phẩm vẫn `http://localhost:20120`; máy này lắng nghe **20128**.

| # | lệnh | kết quả | giây |
| --- | --- | --- | --- |
| S1 | `frog doctor --base-url http://127.0.0.1:20128` | 270 model, khóa có | 0.6 |
| S2 | `… --smoke cu/default` | trả `pong`, uncertain (subscription quota) | 3.7 |
| R1–R3 | `frog team --provider 9router …` model mặc định nhóm vai | intake lỗi `Cursor AgentService returned an empty turn` | 1.1–1.6 |
| R4 | `--model cu/default` | intake không trả JSON | 10.4 |
| S3 | `--smoke cu/claude-4.5-sonnet` | empty turn | 1.3 |

Hết ngân sách thử thật trong hạn mức (2 smoke + ≤6 chạy). Kết nối và sổ uncertain ổn trên `cu/default`. Đội web mặc định (`cu/gpt-5.6-sol-high` / `cu/claude-opus-5-thinking-high`) chưa hoàn thành một đơn thật vì AgentService phía sau 9router trả lượt rỗng / không JSON. Chất lượng nội dung trang **chưa** có bằng chứng model thật.

## Ghi chú trung thực

- Provider giả trả kịch bản cố định. Verifier giả luôn PASS. Kết luận về chất lượng model chỉ lấy từ chạy thật.
- PROV-9R `85c40c0`: CI 10/11, ô Windows 3.12 đỏ ở `T-INTERRUPT` (bài kill đọc checkpoint khi Windows đang thay file). Đã yêu cầu chạy lại riêng ô đỏ.
- UX-7 `09bcc6f`: unittest local 670 OK (skipped=3). CI GitHub chưa xác nhận ở bước ghi sổ này.
