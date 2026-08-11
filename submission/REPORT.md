# Báo cáo Day 13 Observability

## 1. Thông tin nhóm

- Tên nhóm:
- Repository URL:
- Commit SHA cuối:
- Thành viên và vai trò:

## 2. Kết quả kỹ thuật

- Điểm `validate_logs.py`: baseline 30/100 (trước khi sửa `app/middleware.py`, `app/logging_config.py`, `app/main.py`, `app/pii.py`) → 100/100 sau khi hoàn thiện. Xem [evidence/validate_logs_result.txt](evidence/validate_logs_result.txt).
- Tổng số traces:
- Số PII leak còn lại: 0 (`validate_logs.py` báo `Potential PII leaks detected: 0` trên 25 log record, đã test thêm email, số điện thoại VN, số thẻ tín dụng).
- Link/đường dẫn dashboard:

## 3. Logging và tracing

- Evidence correlation ID: mỗi request sinh `correlation_id` dạng `req-<8hex>` (hoặc lấy từ header `x-request-id`), bind vào structlog contextvars nên xuất hiện xuyên suốt `request_received` → `response_sent` của cùng một request và trả lại qua header `x-request-id`. Xem [evidence/log_correlation_id_sample.jsonl](evidence/log_correlation_id_sample.jsonl) (`correlation_id=req-03387add` xuất hiện ở cả 2 dòng log).
- Evidence PII redaction: processor `scrub_event` scrub text trước khi `JsonlFileProcessor` ghi xuống JSONL. Đã test với email, số điện thoại VN, số thẻ tín dụng — cả ba đều bị thay bằng `[REDACTED_*]` trước khi ghi log. Xem [evidence/log_pii_redacted_sample.jsonl](evidence/log_pii_redacted_sample.jsonl).
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
| | | | |
