# Alert rules và runbook

Nguồn chuẩn là `data/logs.jsonl`; threshold khớp với `config/slo.yaml` và
`config/dashboard.yaml`. Mỗi alert chỉ được đánh giá khi đủ traffic tối thiểu để
tránh cảnh báo nhiễu. Khi xử lý, lưu time range, metric, trace ID và log có
correlation ID vào `submission/evidence/`.

## Quy trình chung

1. Acknowledge alert, ghi thời điểm bắt đầu và cố định cùng một time range trên dashboard.
2. Xác nhận triệu chứng trên panel tương ứng; không kết luận root cause chỉ từ metric.
3. Chọn một request bất thường, mở `trace_id` trong Langfuse và tìm log có cùng `correlation_id`.
4. Mitigate trước nếu người dùng đang bị ảnh hưởng; sau đó mới hoàn tất phân tích nguyên nhân.
5. Chỉ resolve khi metric ở dưới/ngược threshold liên tục ít nhất 15 phút và có request canary thành công.

## Chat High Error Rate

- Severity: `critical`.
- SLI/SLO: `error_rate_pct <= 2%`; alert khi lớn hơn 2% trong cửa sổ 5 phút,
  kéo dài 10 phút và có ít nhất 20 request.
- Ảnh hưởng: người dùng nhận HTTP 500 hoặc không nhận được câu trả lời.
- Owner: `ai-platform-oncall`.

Ba bước kiểm tra đầu tiên:

1. Mở panel Errors, xác nhận tử số `request_failed`, mẫu số `request_received`
   và breakdown `error_type`; kiểm tra alert không phải do traffic quá thấp.
2. Lọc log trong cùng 5 phút với `event == "request_failed"`, nhóm theo
   `error_type`, rồi lấy một `correlation_id` đại diện.
3. Tìm trace có metadata `correlation_id` đó trong Langfuse; kiểm tra prompt
   metadata và span lỗi để phân biệt retrieval, prompt fetch và LLM.

Mitigation:

- Nếu lỗi tập trung sau một thay đổi prompt, chuyển `production` về version
  `baseline` bằng `python scripts/manage_langfuse_prompts.py rollback`.
- Nếu dependency ngoài lỗi, giữ local prompt fallback, giảm concurrency hoặc
  tạm vô hiệu feature bị ảnh hưởng; không xóa log lỗi.

Escalation và resolve:

- Escalate incident commander ngay nếu error rate trên 10% trong 5 phút hoặc
  mọi request của một feature đều lỗi.
- Resolve sau khi `error_rate_pct <= 2%` liên tục 15 phút; lưu metric trước/sau,
  trace ID, correlation ID, root cause và preventive action.

## Chat High P95 Latency

- Severity: `critical`.
- SLI/SLO: `latency_p95_ms <= 3000`; alert khi vượt 3000 ms trong cửa sổ 5
  phút, kéo dài 10 phút và có ít nhất 5 response.
- Ảnh hưởng: ít nhất 5% người dùng chờ lâu hơn 3 giây.
- Owner: `ai-platform-oncall`.

Ba bước kiểm tra đầu tiên:

1. So sánh P50/P95/P99 và traffic với 15 phút trước để xác nhận đây là tail
   latency, không chỉ là một outlier đơn lẻ.
2. Chọn `response_sent` có `latency_ms > 3000`, lấy `trace_id` và
   `correlation_id`, rồi mở waterfall Langfuse.
3. Xác định span chiếm phần lớn thời gian; đối chiếu log và trạng thái incident
   để chứng minh retrieval, LLM hay dependency nào chậm.

Mitigation:

- Với retrieval chậm: giảm concurrency, dùng context fallback/cached context
  hoặc tạm vô hiệu feature bị ảnh hưởng.
- Với output quá dài: rollback prompt candidate hoặc giới hạn output token.

Escalation và resolve:

- Escalate khi P95 trên 6000 ms trong 5 phút hoặc P99 tiếp tục tăng hai cửa sổ.
- Resolve khi P95 không quá 3000 ms liên tục 15 phút và canary có trace/log đầy đủ.

## Chat Quality Degradation

- Severity: `warning`.
- SLI/SLO: `quality_score_avg >= 0.75`; alert khi nhỏ hơn 0.75 trong cửa sổ 15
  phút, kéo dài 15 phút và có ít nhất 10 response.
- Ảnh hưởng: câu trả lời vẫn trả về nhưng có nguy cơ thiếu context hoặc không hữu ích.
- Owner: `ai-quality`.

Ba bước kiểm tra đầu tiên:

1. Xác nhận mean và phân phối `quality_score`, chia theo `feature` và prompt label.
2. So sánh trace của `baseline` và `candidate`; kiểm tra `prompt_name`,
   `prompt_label`, `prompt_version`, `doc_count` và model.
3. Đối chiếu query với retrieval context và log `response_sent`; không dùng
   quality proxy làm bằng chứng duy nhất cho chất lượng thực tế.

Mitigation:

- Chuyển traffic về prompt `baseline` nếu suy giảm chỉ xuất hiện ở candidate.
- Tạm dùng local fallback khi managed prompt lỗi; giữ nguyên trace metadata
  `prompt_source=local-fallback` để việc điều tra không mất dấu.

Escalation và resolve:

- Escalate cho `ai-quality` nếu score dưới 0.60 hoặc nhiều feature cùng suy giảm.
- Resolve sau khi quality mean đạt ít nhất 0.75 liên tục 30 phút; lưu trace hai
  version, thao tác rollback và đánh giá thủ công một mẫu câu trả lời.
