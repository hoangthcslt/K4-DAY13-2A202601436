# Báo cáo Day 13 Observability

## 1. Thông tin nhóm

- Tên nhóm:
- Repository URL:
- Commit SHA cuối:
- Thành viên và vai trò:

## 2. Kết quả kỹ thuật

- Điểm `validate_logs.py`: baseline 30/100 (trước khi sửa `app/middleware.py`, `app/logging_config.py`, `app/main.py`, `app/pii.py`) → 100/100 sau khi hoàn thiện. Xem [evidence/validate_logs_result.txt](evidence/validate_logs_result.txt).
- Tổng số traces: runtime local đã sinh 2 trace ID có thể nối với log; chưa xác minh được trace ingest trên UI vì `auth_check` của cấu hình hiện tại trả HTTP 401. Sau khi cập nhật đúng key/host, chạy `python scripts/manage_langfuse_prompts.py bootstrap` và `python scripts/load_test.py` để tạo/nộp danh sách tối thiểu 10 trace thật. Xem [evidence/runtime_metrics_cp2.json](evidence/runtime_metrics_cp2.json).
- Số PII leak còn lại: 0 (`validate_logs.py` báo `Potential PII leaks detected: 0` trên 30 log record). Ngoài email/phone/thẻ, đã bịt thêm ba đường rò mà validator không quét tới: payload lồng nhau, exception traceback và field top-level ngoài `payload`. Xem [evidence/pii_global_redaction_before_after.md](evidence/pii_global_redaction_before_after.md) và [evidence/validate_logs_cp1_security.txt](evidence/validate_logs_cp1_security.txt).
- Link/đường dẫn dashboard: contract tại [`config/dashboard.yaml`](../config/dashboard.yaml), validator evidence tại [evidence/validate_dashboard_cp2.txt](evidence/validate_dashboard_cp2.txt); screenshot runtime chưa thu.

## 3. Logging và tracing

- Evidence correlation ID: mỗi request sinh `correlation_id` dạng `req-<8hex>` (hoặc lấy từ header `x-request-id`), bind vào structlog contextvars nên xuất hiện xuyên suốt `request_received` → `response_sent` của cùng một request và trả lại qua header `x-request-id`. Xem [evidence/log_correlation_id_sample.jsonl](evidence/log_correlation_id_sample.jsonl) (`correlation_id=req-03387add` xuất hiện ở cả 2 dòng log).
- Evidence PII redaction: processor `scrub_event` scrub text trước khi `JsonlFileProcessor` ghi xuống JSONL. Đã test với email, số điện thoại VN, số thẻ tín dụng — cả ba đều bị thay bằng `[REDACTED_*]` trước khi ghi log. Xem [evidence/log_pii_redacted_sample.jsonl](evidence/log_pii_redacted_sample.jsonl).
- Evidence PII redaction toàn cục: `scrub_event` được nâng cấp thành `scrub_value()` duyệt đệ quy toàn bộ `event_dict` (dict/list lồng nhau, giới hạn depth 6) và được **chuyển xuống sau `format_exc_info`** — trước đó nó chạy trước processor này nên chuỗi traceback do `format_exc_info` sinh ra chưa từng đi qua bộ scrub. Bổ sung pattern `ip_address`, sửa `vn_address` để hết xoá nhầm log vận hành, và chỉ giữ các field server kiểm soát như `user_id_hash`/`trace_id` trong `SAFE_KEYS`; các field client kiểm soát như `correlation_id` vẫn được scrub. Xem [evidence/pii_global_redaction_before_after.md](evidence/pii_global_redaction_before_after.md), [evidence/log_pii_global_redaction_sample.jsonl](evidence/log_pii_global_redaction_sample.jsonl) và [evidence/pytest_pii_cp1_security.txt](evidence/pytest_pii_cp1_security.txt).
- Evidence trace waterfall: chưa thể chụp từ Langfuse UI do credential hiện trả 401; không dùng trace ID local để giả bằng chứng ingest.
- Evidence nối trace/log: [evidence/log_trace_correlation_cp2.jsonl](evidence/log_trace_correlation_cp2.jsonl) chứa `trace_id=5831c0ad9a97784a50284ef6bb921ce7` và `correlation_id=req-f8bf566d` trên response runtime thật. Trace UI/waterfall vẫn chờ credential hợp lệ.
- Giải thích một span đáng chú ý: trace generation được cấu hình không capture input/output thô để tránh PII; metadata chứa prompt name/label/version/source, user hash, session, feature/model tags và correlation ID. `request_failed` cũng ghi trace ID khi dependency ném lỗi.

## 4. Prompt versioning

- Prompt name: `day13-chat` (cấu hình qua `LANGFUSE_PROMPT_NAME`).
- Version/label baseline: script `manage_langfuse_prompts.py bootstrap` tạo label `baseline` + `production`; version runtime chưa xác minh do credential 401.
- Version/label candidate: cùng script tạo candidate giữ đúng ba biến prompt; version runtime chưa xác minh do credential 401.
- Trace ID của mỗi version: chờ chạy lại load test sau khi sửa credential; không dùng local fallback làm evidence managed prompt.
- Bằng chứng đổi label hoặc rollback: `promote` chuyển `production` sang candidate; `rollback` chuyển về baseline bằng API Langfuse. Test tự động xác nhận đúng version/label operation trong `tests/test_manage_langfuse_prompts.py`; ảnh UI vẫn cần thu sau khi credential hợp lệ.

## 5. Dashboard, SLO và alerts

- Kết quả `validate_dashboard.py`: **HỢP LỆ: 6/6 panel**, xem [evidence/validate_dashboard_cp2.txt](evidence/validate_dashboard_cp2.txt).
- Evidence dashboard: contract 6 panel nằm tại `config/dashboard.yaml`; screenshot runtime vẫn cần chụp từ công cụ dashboard với time range 60 phút, refresh 30 giây và threshold hiển thị.
- SLO đã chọn và lý do: cửa sổ rolling 28 ngày; P95 <= 3000 ms, error rate <= 2%, daily cost <= 2.5 USD và quality mean >= 0.75. Mỗi SLI có công thức, nguồn event, comparison, minimum traffic, target và error budget trong `config/slo.yaml`; threshold được test luôn khớp dashboard.
- Alert rules và runbook: 3 symptom-based alerts cho error rate, P95 latency và quality degradation, có severity, minimum traffic, window, duration, owner và link runbook. Runbook tại `docs/alerts.md` mô tả triage Metrics → Traces → Logs, mitigation, escalation và tiêu chí resolve.
- Runtime metric: 2 success + 1 error tạo `error_rate_pct=33.33`, `errors_total=1`, traffic=3; xem [evidence/runtime_metrics_cp2.json](evidence/runtime_metrics_cp2.json). Toàn bộ suite **54 passed**, xem [evidence/pytest_cp2.txt](evidence/pytest_cp2.txt).

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
