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

## 4. Bảo vệ khả năng truy vết

`scrub_value` bỏ qua `SAFE_KEYS` = `ts`, `level`, `service`, `correlation_id`,
`user_id_hash`, `session_id`, `feature`, `model`, `env`.

Lý do cụ thể: `user_id_hash` là hex 12 ký tự, có xác suất thật rơi vào dạng
12 chữ số và bị pattern `cccd` xoá mất. Mất `user_id_hash` hoặc `correlation_id`
là mất luôn khả năng nối Metrics → Traces → Logs, tức là hỏng mục tiêu chính của
bài lab. Bằng chứng: `test_scrub_value_keeps_structural_fields_intact` và
`test_correlation_metadata_survives_redaction`.

## 5. Kết quả kiểm chứng

- `pytest tests/test_pii.py tests/test_pii_global_redaction.py -v` → **22 passed**
  (xem `pytest_pii_cp1_security.txt`).
- Toàn bộ suite: **42 passed** (22 test có sẵn + 20 test mới, không phá test của A/C).
- `python scripts/validate_logs.py` → **100/100**, `Potential PII leaks detected: 0`
  trên 30 record (xem `validate_logs_cp1_security.txt`).
- Log thật của 4 request probe: xem `log_pii_global_redaction_sample.jsonl`.

Input gốc gửi vào API (không ghi xuống log, chỉ để đối chiếu):

```text
pii-session-01: "Lien he toi qua 0912345678 hoac email test.pii@vinuni.edu.vn, the 4111 1111 1111 1111"
pii-session-02: "CCCD cua toi la 012345678901, passport B1234567, IP 192.168.1.104"
pii-session-03: "Giao hang toi 123 Nguyen Trai, Phuong 7, Quan 5 va 45 Le Loi, Phường Bến Nghé"
pii-session-04: "Latency 3000 ms, quan sat p95 tang manh va tinh trang dang xau di"  <- phải giữ nguyên
```

Kết quả trong log:

```text
req-7c9b633f  Lien he toi qua [REDACTED_PHONE_VN] hoac email [REDACTED_EMAIL], the [REDACTED_C...
req-2bd9926e  CCCD cua toi la [REDACTED_CCCD], passport [REDACTED_PASSPORT], IP [REDACTED_IP_A...
req-105f1db6  Giao hang toi [REDACTED_VN_ADDRESS], Quan [REDACTED_VN_ADDRESS]
req-eb47a73f  Latency 3000 ms, quan sat p95 tang manh va tinh trang dang xau di
```

Ba dòng đầu bị che đúng loại PII; dòng thứ tư là log vận hành và được giữ nguyên.
