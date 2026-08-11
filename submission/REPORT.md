# Báo cáo Day 13 Observability

## 1. Thông tin nhóm

- Tên nhóm:
- Repository URL:
- Commit SHA cuối:
- Thành viên và vai trò:

## 2. Kết quả kỹ thuật

- Điểm `validate_logs.py`: baseline 30/100 (trước khi sửa `app/middleware.py`, `app/logging_config.py`, `app/main.py`, `app/pii.py`) → 100/100 sau khi hoàn thiện. Xem [evidence/validate_logs_result.txt](evidence/validate_logs_result.txt).
- Tổng số traces:
- Số PII leak còn lại: 0 (`validate_logs.py` báo `Potential PII leaks detected: 0` trên 30 log record). Ngoài email/phone/thẻ, đã bịt thêm ba đường rò mà validator không quét tới: payload lồng nhau, exception traceback và field top-level ngoài `payload`. Xem [evidence/pii_global_redaction_before_after.md](evidence/pii_global_redaction_before_after.md) và [evidence/validate_logs_cp1_security.txt](evidence/validate_logs_cp1_security.txt).
- Link/đường dẫn dashboard:

## 3. Logging và tracing

- Evidence correlation ID: mỗi request sinh `correlation_id` dạng `req-<8hex>` (hoặc lấy từ header `x-request-id`), bind vào structlog contextvars nên xuất hiện xuyên suốt `request_received` → `response_sent` của cùng một request và trả lại qua header `x-request-id`. Xem [evidence/log_correlation_id_sample.jsonl](evidence/log_correlation_id_sample.jsonl) (`correlation_id=req-03387add` xuất hiện ở cả 2 dòng log).
- Evidence PII redaction: processor `scrub_event` scrub text trước khi `JsonlFileProcessor` ghi xuống JSONL. Đã test với email, số điện thoại VN, số thẻ tín dụng — cả ba đều bị thay bằng `[REDACTED_*]` trước khi ghi log. Xem [evidence/log_pii_redacted_sample.jsonl](evidence/log_pii_redacted_sample.jsonl).
- Evidence PII redaction toàn cục: `scrub_event` được nâng cấp thành `scrub_value()` duyệt đệ quy toàn bộ `event_dict` (dict/list lồng nhau, giới hạn depth 6) và được **chuyển xuống sau `format_exc_info`** — trước đó nó chạy trước processor này nên chuỗi traceback do `format_exc_info` sinh ra chưa từng đi qua bộ scrub. Bổ sung pattern `ip_address`, sửa `vn_address` để hết xoá nhầm log vận hành, và giữ `SAFE_KEYS` (`correlation_id`, `user_id_hash`, …) khỏi bị redact để không mất khả năng truy vết. Xem [evidence/pii_global_redaction_before_after.md](evidence/pii_global_redaction_before_after.md), [evidence/log_pii_global_redaction_sample.jsonl](evidence/log_pii_global_redaction_sample.jsonl) và [evidence/pytest_pii_cp1_security.txt](evidence/pytest_pii_cp1_security.txt).
- Evidence trace waterfall:
- Giải thích một span đáng chú ý:

## 4. Prompt versioning

- Prompt name:
- Version/label baseline:
- Version/label candidate:
- Trace ID của mỗi version:
- Bằng chứng đổi label hoặc rollback:

## 5. Dashboard, SLO và alerts

- Kết quả `validate_dashboard.py`:
- Evidence dashboard:
- SLO đã chọn và lý do:
- Alert rules và runbook:

## 6. Điều tra challenge

- Challenge ID:
- Triệu chứng từ metrics:
- Trace ID liên quan:
- Log line/correlation ID liên quan:
- Root cause:
- Fix action:
- Preventive measure:

## 7. Đóng góp cá nhân

Với mỗi thành viên, ghi rõ nhiệm vụ và link commit/PR tương ứng.

| Thành viên | Phần việc | Commit/PR | Điều đã học |
|---|---|---|---|
| Trần Tiến Dũng | CP1 — Security & Compliance: nâng `scrub_event` thành scrub đệ quy toàn `event_dict`; chuyển processor xuống sau `format_exc_info` để traceback cũng được che; sửa false positive của pattern `vn_address`; thêm `ip_address`; đặt `SAFE_KEYS` bảo vệ `correlation_id`/`user_id_hash`; viết 20 test trong `tests/test_pii_global_redaction.py` | Các commit có tiền tố `TranTienDung_CP1` (`git log --oneline --grep TranTienDung_CP1`) | Validator xanh không có nghĩa là đã che hết PII: `validate_logs.py` chỉ quét được những record app hiện sinh ra, nên payload lồng nhau và traceback vẫn lọt. Thứ tự processor trong structlog quyết định dữ liệu nào đã tồn tại lúc scrub — đặt scrub trước `format_exc_info` là che hụt toàn bộ traceback. Ngược lại, redact quá tay cũng là lỗi: pattern địa chỉ không dấu ban đầu xoá nhầm 4/5 log latency, làm mất chính dữ liệu cần cho dashboard và điều tra incident. |
