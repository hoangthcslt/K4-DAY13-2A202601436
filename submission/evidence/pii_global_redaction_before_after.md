# CP1 — Security & Compliance: nâng cấp che PII toàn cục

Phần này nối tiếp CP1 của Thành viên A (đã bật `scrub_event` và thêm pattern).
Sau khi rà lại, `scrub_event` mới chỉ che được **một tầng của `payload`**, nên vẫn
còn ba đường rò PII mà `validate_logs.py` không phát hiện (validator chỉ quét các
log record do app hiện sinh ra, vốn có payload phẳng).

## 1. Ba lỗ hổng đã bịt

Repro: log 3 record với PII ở vị trí mà `scrub_event` cũ không duyệt tới, rồi quét
file JSONL bằng đúng bộ detector của `scripts/validate_logs.py`.

| Trường hợp | Trước | Sau |
|---|---|---|
| `payload` lồng nhau (dict trong dict, list) | `LEAK -> credit_card, email, phone_vn` | `sach` |
| Exception traceback (`exc_info=True`) | `LEAK -> credit_card, email` | `sach` |
| Field top-level ngoài `payload` | `LEAK -> phone_vn` | `sach` |

### Nguyên nhân 1 — chỉ duyệt một tầng

`scrub_event` cũ chỉ map qua `payload.items()` và bỏ qua giá trị không phải `str`,
nên dict/list lồng bên trong không được scrub.

**Fix:** thêm `scrub_value()` trong `app/pii.py` — duyệt đệ quy dict/list/tuple
(giới hạn `MAX_SCRUB_DEPTH = 6`), `scrub_event` gọi thẳng trên cả `event_dict`.

### Nguyên nhân 2 — sai thứ tự processor

Chuỗi processor cũ đặt `scrub_event` **trước** `format_exc_info`:

```text
TimeStamper -> scrub_event -> StackInfoRenderer -> format_exc_info -> JsonlFileProcessor
```

`format_exc_info` là processor sinh ra key `exception` dưới dạng chuỗi traceback.
Vì nó chạy *sau* `scrub_event`, chuỗi traceback không bao giờ đi qua bộ scrub và
được ghi thẳng xuống JSONL. Traceback thường chứa cả giá trị biến và message lỗi
— đúng chỗ PII hay lọt ra nhất.

**Fix:** chuyển `scrub_event` xuống sau `format_exc_info`, vẫn giữ trước
`JsonlFileProcessor` (file JSONL được ghi ngay tại processor này):

```text
TimeStamper -> StackInfoRenderer -> format_exc_info -> scrub_event -> JsonlFileProcessor
```

Bằng chứng: `tests/test_pii_global_redaction.py::test_exception_traceback_is_redacted_in_log_file`.

## 2. Sửa false positive của pattern `vn_address`

Pattern địa chỉ trước đó dùng cờ `(?i)` toàn cục với danh sách từ khoá không dấu
(`quan`, `xa`, `tinh`, `thanh pho`). Các từ này trùng với từ thông dụng trong log
vận hành, nên **xoá nhầm 4/5 câu log bình thường**:

| Câu log | Pattern cũ | Pattern mới |
|---|---|---|
| `Latency 3000 ms, quan sat p95 tang manh` | `Latency [REDACTED_VN_ADDRESS]` | giữ nguyên |
| `Threshold 2000 ms, xa hon muc SLO` | `Threshold [REDACTED_VN_ADDRESS]` | giữ nguyên |
| `Ghi nhan 15 loi, tinh trang dang xau di` | `Ghi nhan [REDACTED_VN_ADDRESS]` | giữ nguyên |
| `P95 la 4200 ms, thanh pho khong lien quan` | `P95 la [REDACTED_VN_ADDRESS]` | giữ nguyên |
| `Nha toi o 123 Nguyen Trai, Phuong 7, Quan 5` | che | che |

Che nhầm cũng là hỏng: dashboard latency và phần điều tra challenge đọc chính
những chuỗi này, mất chúng là mất dữ liệu điều tra.

Pattern mới bỏ `(?i)` toàn cục và tách ba nhánh:

1. từ khoá **có dấu** (`phường`, `xã`, `quận`, `huyện`, `thành phố`, `tỉnh`) — rõ
   nghĩa nên cho phép theo sau là chữ bất kỳ;
2. từ khoá **không dấu + số** (`Phuong 7`, `Quan 5`, `Q.1`);
3. từ khoá **không dấu viết hoa + danh từ riêng viết hoa** (`Tinh Binh Duong`).

Kết quả đo: 6/6 địa chỉ vẫn bị che, 7/7 câu log vận hành giữ nguyên.
Bằng chứng: `test_new_patterns_are_redacted` và
`test_observability_messages_are_not_over_redacted`.

## 3. Pattern bổ sung

- `ip_address` — IP là dữ liệu cá nhân theo GDPR, và log AI hay ghi IP client.
- Đổi thứ tự pattern: `credit_card` chạy trước `cccd` để chuỗi 16 số không bị
  pattern 12 số cắt trước.

## 4. Bảo vệ khả năng truy vết — và giới hạn của nó

`scrub_value` bỏ qua `SAFE_KEYS` = `ts`, `level`, `service`, `user_id_hash`,
`model`, `env`.

Lý do cụ thể: `user_id_hash` là hex 12 ký tự, có xác suất thật rơi vào dạng
12 chữ số và bị pattern `cccd` xoá mất. Mất `user_id_hash` là mất khả năng nối
Metrics → Traces → Logs, tức là hỏng mục tiêu chính của bài lab.
Bằng chứng: `test_scrub_value_keeps_structural_fields_intact`.

### Lỗi tự phát hiện khi rà lại yêu cầu

Bản đầu tiên của `SAFE_KEYS` có thêm `session_id`, `feature` và `correlation_id`.
Đó là sai: cả ba đều **do client kiểm soát** — `session_id`/`feature` đến thẳng từ
body `ChatRequest`, `correlation_id` lấy từ header `x-request-id` nếu client gửi.
Đưa chúng vào danh sách miễn scrub nghĩa là mở lại đúng đường rò vừa bịt.

Đo được: log một record với `session_id="0912345678"` và
`feature="lienhe-4111 1111 1111 1111"` → `validate_logs.py` báo
`LEAK -> ['credit_card', 'phone_vn']`. Sau khi loại ba key này khỏi `SAFE_KEYS` →
`sach`.

Việc redact không phá correlation, vì redact là ánh xạ tất định: cùng một
`correlation_id` luôn cho ra cùng một chuỗi `[REDACTED_*]`, nên các log của cùng
một request vẫn nối được với nhau. Bằng chứng:
`test_client_controlled_fields_are_scrubbed` và
`test_redacted_correlation_id_still_correlates`.

Nguyên tắc rút ra: chỉ field **server tự sinh** mới được miễn scrub.

### Đề xuất cho phần Middleware (ngoài phạm vi CP1 Security)

`app/middleware.py` hiện nhận `x-request-id` từ client mà không kiểm tra định
dạng. Nên chỉ chấp nhận header khi khớp `^[A-Za-z0-9_-]{1,64}$`, ngược lại tự
sinh `req-<8hex>`. Đây là hardening ở biên, thuộc file của thành viên phụ trách
middleware nên chưa tự sửa; hiện tại rủi ro đã được chặn ở lớp scrub.

## 5. Kết quả kiểm chứng

- `pytest tests/test_pii.py tests/test_pii_global_redaction.py -v` → **22 passed**
  (xem `pytest_pii_cp1_security.txt`).
- Toàn bộ suite: **42 passed** (22 test có sẵn + 20 test mới, không phá test của A/C).
- `python scripts/validate_logs.py` → **100/100**, `Potential PII leaks detected: 0`
  trên 30 record (xem `validate_logs_cp1_security.txt`).

### 5.1 Bằng chứng trên dữ liệu chính thức của lab

`data/sample_queries.jsonl` đã cắm sẵn ba loại PII. Toàn bộ 10 query này được gửi
qua API và đây là log thật sinh ra:

| Session | Input gốc trong `sample_queries.jsonl` | `message_preview` trong log |
|---|---|---|
| `s01` | `...My email is student@vinuni.edu.vn` | `...My email is [REDACTED_EMAIL]` |
| `s05` | `Here is my phone 0987654321, ...` | `Here is my phone [REDACTED_PHONE_VN], ...` |
| `s09` | `...credit card 4111 1111 1111 1111?` | `...credit card [REDACTED_CREDIT_CARD]?` |

Correlation ID tương ứng: `req-d59990e5`, `req-e1852d42`, `req-13ecffa9` —
xem `log_pii_global_redaction_sample.jsonl`.

### 5.2 Fixture bổ sung cho phần dữ liệu lab không phủ

`sample_queries.jsonl` không có mẫu nào cho các pattern được thêm ở mục 2–3, và
cũng không có câu nào để kiểm tra chiều ngược lại (log vận hành **không** được bị
che nhầm). Bốn request dưới đây được thêm để phủ đúng hai khoảng trống đó — giá
trị dùng là dữ liệu tổng hợp, không phải thông tin của người thật:

```text
pii-session-02: "CCCD cua toi la 012345678901, passport B1234567, IP 192.168.1.104"
pii-session-03: "Giao hang toi 123 Nguyen Trai, Phuong 7, Quan 5 va 45 Le Loi, Phường Bến Nghé"
pii-session-04: "Latency 3000 ms, quan sat p95 tang manh va tinh trang dang xau di"  <- phải giữ nguyên
```

Kết quả trong log:

```text
req-2bd9926e  CCCD cua toi la [REDACTED_CCCD], passport [REDACTED_PASSPORT], IP [REDACTED_IP_A...
req-105f1db6  Giao hang toi [REDACTED_VN_ADDRESS], Quan [REDACTED_VN_ADDRESS]
req-eb47a73f  Latency 3000 ms, quan sat p95 tang manh va tinh trang dang xau di
```

Hai dòng đầu bị che đúng loại PII; dòng thứ ba là log vận hành và được giữ nguyên.

### 5.3 Vì sao ba lỗ hổng ở mục 1 phải repro bằng lời gọi logger

Ba trường hợp ở mục 1 **không thể tạo ra bằng bất kỳ input nào gửi vào `/chat`**,
kể cả input trong `config/challenge.json`: `app/main.py` luôn ghi payload phẳng
`{"message_preview": ...}` và không dùng `exc_info`. Payload lồng nhau, traceback
và field top-level là đặc tính của **cách gọi log**, không phải nội dung request.
Vì vậy repro và test cho ba trường hợp này gọi thẳng structlog logger — xem
`tests/test_pii_global_redaction.py`.

Đây cũng chính là lý do phải sửa: ngay khi một thành viên khác thêm một dòng
`log.error(..., exc_info=True)` hoặc một payload lồng nhau trong CP2/CP3, PII sẽ
rò mà `validate_logs.py` vẫn báo xanh.
