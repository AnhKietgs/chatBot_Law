# PRD — Coding Loop và Legal-Document Loop Harness

**Trạng thái:** Sẵn sàng lập implementation plan  
**Ngày:** 2026-10-13  
**Sản phẩm:** Law RAG — Chatbot pháp luật Việt Nam có căn cứ  
**Chủ sở hữu:** Repository maintainer  

## 1. Tóm tắt

Project cần một harness có hai workflow độc lập:

1. **Coding loop** giúp coding agent lập kế hoạch, sửa code, kiểm tra, tự review và lặp lại có giới hạn trước khi tạo PR.
2. **Legal-document loop** xử lý văn bản pháp luật từ upload đến publish bằng state machine có retry, audit, quality gate và human approval.

Hai loop dùng chung nguyên tắc vận hành gồm run ID, stage, status, attempt, event, artifact, validation và điều kiện dừng. Chúng không dùng chung business state machine và không được gọi lẫn nhau.

Giải pháp phải tận dụng PostgreSQL, Redis, Celery, MinIO, Qdrant, Docker Compose và GitHub Actions đang có; không bổ sung workflow engine bên ngoài.

## 2. Thuật ngữ

- **Agent loop:** model chọn hành động hoặc tool, nhận kết quả, rồi tiếp tục cho đến trạng thái kết thúc.
- **Coding loop:** `task → plan → edit → verify → repair → review → PR`.
- **Legal-document loop:** `upload → validate → extract/OCR → scan → parse/chunk → audit → review → embed → verify → publish`.
- **Harness:** contract điều phối bao quanh loop, gồm instructions, tools, state, retry, validation, artifacts, approvals và exit criteria.
- **Quality gate:** điều kiện bắt buộc phải đạt trước khi chuyển stage.
- **Human gate:** stage bắt buộc người có thẩm quyền xác nhận.

## 3. Vấn đề cần giải quyết

### 3.1 Coding workflow

- Chưa có `AGENTS.md` làm bản đồ repo và định nghĩa hành vi hoàn tất.
- Chưa có một lệnh verify thống nhất cho backend, frontend, evaluator và Docker configuration.
- Coding agent có thể lặp lại cùng lỗi mà không có giới hạn hoặc failure signature.
- CI hiện chưa đại diện đầy đủ cho quality gate trước PR.

### 3.2 Legal-document workflow

- `IngestionJob` chỉ biểu diễn trạng thái tổng quát, không cho biết worker đang OCR, chunk, embed hay verify.
- Publish đang thực hiện embedding đồng bộ trong HTTP request.
- Celery task chưa có retry/backoff và crash-recovery contract rõ ràng.
- Chưa có staging state cho vector trước khi publish.
- Chưa có post-publish retrieval smoke test và artifact audit thống nhất.

## 4. Mục tiêu

- Mỗi coding run có quy trình kiểm chứng lặp lại được và có bằng chứng trước khi báo hoàn tất.
- Mỗi document run quan sát được theo stage, có retry an toàn và không tạo dữ liệu trùng.
- Không có vector chưa verify nào được truy xuất bởi chatbot.
- Con người luôn duyệt trước khi merge code và trước khi publish văn bản.
- Tác vụ OCR, embedding và verification dài không giữ HTTP request mở.
- Lỗi kỹ thuật tạm thời tự phục hồi; lỗi dữ liệu hoặc pháp lý dừng để người vận hành xử lý.

## 5. Ngoài phạm vi

- Tự động merge pull request.
- Tự động publish văn bản không qua quản trị viên.
- Chạy RAGAS đầy đủ sau từng lần publish.
- Thêm Temporal, Prefect, LangGraph hoặc agent framework mới.
- Thay đổi thuật toán trả lời, retrieval hoặc reranking hiện tại ngoài smoke test publish.
- Document loop dùng để bảo trì README hoặc tài liệu kỹ thuật của repo.

## 6. Người dùng

- **Developer/coding agent:** cần một contract rõ ràng để biết phải đọc gì, chạy gì và khi nào được coi là hoàn tất.
- **Quản trị viên kho luật:** upload, theo dõi tiến độ, kiểm tra cấu trúc, duyệt, publish hoặc retry.
- **Chuyên gia pháp lý:** xác nhận cấu trúc Điều/Khoản/Điểm và căn cứ trước khi publish.
- **Operator:** chẩn đoán job lỗi, xem retry, heartbeat, metrics và audit artifacts.

## 7. Yêu cầu chức năng theo Story → Epic → Task

### Story S1 — Coding agent hoàn thành thay đổi một cách kiểm chứng được

> Là developer, tôi muốn coding agent tuân theo một loop có giới hạn và quality gate rõ ràng để kết quả không chỉ dựa trên lời khẳng định của model.

#### Epic S1-E1 — Repository knowledge map

**Kết quả:** agent tìm được đúng tài liệu và lệnh kiểm chứng mà không cần nạp một manual lớn vào context.

- **Task S1-E1-T1 — Tạo `AGENTS.md` ngắn**
  - Liệt kê kiến trúc repo, nguồn sự thật, lệnh verify và quy tắc human approval.
  - Chỉ đóng vai trò mục lục; nội dung chi tiết nằm trong `docs/harness/`.
  - **Acceptance:** mọi đường dẫn/lệnh trong file tồn tại và CI kiểm tra được.

- **Task S1-E1-T2 — Viết coding-loop runbook**
  - Định nghĩa stage, exit criteria, failure signature và quy tắc dừng.
  - Quy định tối đa 5 repair rounds; cùng failure signature 3 lần liên tiếp phải dừng và báo blocker.
  - **Acceptance:** một agent mới có thể xác định chính xác bước tiếp theo từ runbook.

- **Task S1-E1-T3 — Viết legal-document-loop runbook**
  - Mô tả state machine, retryable errors, human gate, rollback và recovery.
  - **Acceptance:** stage trong runbook khớp enum/backend contract.

#### Epic S1-E2 — Unified verification command

**Kết quả:** local developer và coding agent dùng cùng một entrypoint kiểm chứng.

- **Task S1-E2-T1 — Tạo harness CLI đa nền tảng**
  - Cung cấp `python tools/harness.py code verify --scope changed|full --mode docker`.
  - Trả exit code khác `0` nếu bất kỳ gate nào thất bại.
  - **Acceptance:** CLI chạy được từ PowerShell và Linux shell mà không cần thay đổi source.

- **Task S1-E2-T2 — Cài đặt changed-scope verification**
  - Chọn targeted tests theo file thay đổi, sau đó chạy `git diff --check`.
  - **Acceptance:** thay đổi backend/frontend/evaluation kích hoạt đúng nhóm kiểm thử.

- **Task S1-E2-T3 — Cài đặt full verification**
  - Chạy backend pytest, frontend TypeScript/Vite build, evaluator tests, `docker compose config` và `git diff --check`.
  - **Acceptance:** summary ghi từng gate, thời gian, trạng thái và command đã chạy.

- **Task S1-E2-T4 — Lưu failure signature**
  - Chuẩn hóa command, exit code và phần lỗi ổn định thành signature.
  - **Acceptance:** cùng một lỗi qua 3 vòng được nhận diện là cùng signature dù timestamp khác nhau.

#### Epic S1-E3 — Pull-request quality gate

**Kết quả:** PR không thể xanh nếu contract chính bị hỏng.

- **Task S1-E3-T1 — Mở rộng GitHub CI**
  - Tách backend core tests, frontend build và evaluator contract thành các job độc lập.
  - **Acceptance:** failure của một job hiển thị riêng và làm workflow thất bại.

- **Task S1-E3-T2 — Validate repository knowledge links**
  - Kiểm tra file và command được tham chiếu bởi `AGENTS.md`/runbooks.
  - **Acceptance:** link tới file bị xóa làm CI fail với lỗi có thể hành động.

- **Task S1-E3-T3 — Chuẩn hóa coding-run artifact**
  - Lưu JSON summary và test logs ở local/GitHub artifact; không commit runtime logs.
  - **Acceptance:** artifact có run ID, gates, duration, failure signatures và final status.

### Story S2 — Quản trị viên xử lý văn bản pháp luật không bị timeout hoặc mất trạng thái

> Là quản trị viên, tôi muốn mỗi văn bản được xử lý bất đồng bộ và quan sát được để có thể biết nó đang ở bước nào và phải làm gì khi lỗi.

#### Epic S2-E1 — Durable job state

**Kết quả:** database biểu diễn đầy đủ loại job, stage, attempt và lỗi.

- **Task S2-E1-T1 — Mở rộng enum và model**
  - `JobType`: `INGEST`, `PUBLISH`, `REINDEX`.
  - `JobStatus`: `QUEUED`, `RUNNING`, `WAITING_APPROVAL`, `RETRYING`, `SUCCEEDED`, `FAILED`.
  - Thêm `PUBLISHING` vào `VersionStatus`.
  - **Acceptance:** transition không hợp lệ bị từ chối ở service boundary.

- **Task S2-E1-T2 — Mở rộng `IngestionJob`**
  - Thêm `job_type`, `stage`, `attempt`, `max_attempts`, `heartbeat_at`, `metrics`, `artifact_key`, `error_code`, `retryable`, `updated_at`.
  - **Acceptance:** mỗi commit tiến độ cập nhật stage, heartbeat và progress nhất quán.

- **Task S2-E1-T3 — Thêm migration và backfill**
  - Job cũ được gán loại/stage dựa trên trạng thái hiện tại.
  - Job lỗi cũ mặc định `retryable=false`.
  - **Acceptance:** migration chạy được trên database có dữ liệu mà không làm mất job/version.

#### Epic S2-E2 — Observable ingestion stages

**Kết quả:** ingest được chia thành các stage có metric và checkpoint rõ ràng.

- **Task S2-E2-T1 — Validate stage**
  - Kiểm tra file, MIME/extension, dung lượng, URL, hiệu lực, metadata, checksum và duplicate.
  - **Acceptance:** lỗi validation có error code ổn định và không retry.

- **Task S2-E2-T2 — Extract/OCR stage**
  - Extract theo từng trang và OCR trang thiếu text.
  - Lưu số trang, trang OCR, trang rỗng và `len(text)`.
  - **Acceptance:** PDF lai không bỏ sót trang scan và heartbeat cập nhật theo page/batch.

- **Task S2-E2-T3 — Security scan stage**
  - Scan trước extraction khi có plain text và scan lại text đã extract.
  - **Acceptance:** prompt injection bị cách ly, không tạo chunk/vector và không retry.

- **Task S2-E2-T4 — Parse/chunk stage**
  - Parse Điều/Khoản/Điểm, secondary split theo token và audit sample.
  - **Acceptance:** zero chunk, duplicate locator và chunk vượt policy làm quality gate fail.

- **Task S2-E2-T5 — Persist audit artifact**
  - Lưu report JSON vào MinIO và tham chiếu từ job.
  - **Acceptance:** report chứa checksum, extraction metrics, security result và chunk statistics.

#### Epic S2-E3 — Retry và crash recovery

**Kết quả:** lỗi tạm thời tự phục hồi nhưng lỗi dữ liệu không bị retry vô hạn.

- **Task S2-E3-T1 — Error taxonomy**
  - Retryable: storage/vector-store/model unavailable và worker lost.
  - Non-retryable: invalid metadata, unsafe content, unreadable document, invalid structure và quality-gate failure.
  - **Acceptance:** mọi exception tại task boundary được map vào một error code và cờ retryable.

- **Task S2-E3-T2 — Celery retry policy**
  - Tối đa 3 attempts, backoff có jitter khoảng `5s`, `30s`, `120s`.
  - **Acceptance:** attempt/progress/status phản ánh đúng từng lần retry.

- **Task S2-E3-T3 — Stale-job recovery**
  - Job không heartbeat 15 phút được đánh dấu stale và có thể chạy lại idempotently.
  - **Acceptance:** worker bị kill giữa batch không tạo provision/vector trùng khi chạy lại.

- **Task S2-E3-T4 — Active-job deduplication**
  - Cùng `version_id + job_type` đang active phải trả về job cũ.
  - **Acceptance:** double-click hoặc request retry không tạo hai worker xử lý cùng phiên bản.

### Story S3 — Chuyên gia pháp lý kiểm soát nội dung trước khi nó đến người dùng

> Là chuyên gia pháp lý, tôi muốn xem bằng chứng xử lý và xác nhận đúng snapshot cấu trúc trước khi văn bản được đưa vào retrieval.

#### Epic S3-E1 — Human legal approval

**Kết quả:** approval gắn với đúng cấu trúc đã review.

- **Task S3-E1-T1 — Giữ structure-hash approval**
  - Hash bao gồm locator, heading và content của toàn bộ provision.
  - **Acceptance:** bất kỳ thay đổi nào sau review làm publish request bị từ chối.

- **Task S3-E1-T2 — Waiting-approval state**
  - Ingest dừng ở `WAITING_APPROVAL`; không tự động chuyển sang publish.
  - **Acceptance:** không Celery task nào có thể bypass human approval.

- **Task S3-E1-T3 — Async publish API**
  - `POST /versions/{id}/publish` trả HTTP `202` với `JobSummary`.
  - **Acceptance:** endpoint không chờ embedding hoàn tất và không tạo publish job trùng.

#### Epic S3-E2 — Atomic vector publication

**Kết quả:** chatbot không nhìn thấy vector chưa được verify.

- **Task S3-E2-T1 — Staging payload**
  - Upsert vector với payload status `STAGING` và version status `PUBLISHING`.
  - **Acceptance:** retrieval production chỉ nhận cả Qdrant `PUBLISHED` và PostgreSQL version `PUBLISHED`.

- **Task S3-E2-T2 — Pre-publish verification**
  - So sánh vector count với chunk count, kiểm tra metadata và sample exact-locator retrieval.
  - **Acceptance:** thiếu một vector hoặc trả sai document/version làm publish fail.

- **Task S3-E2-T3 — Commit publication**
  - Chỉ chuyển Qdrant và PostgreSQL sang `PUBLISHED` sau verify.
  - **Acceptance:** crash tại mọi điểm trước commit không làm dữ liệu staging xuất hiện trong chat.

- **Task S3-E2-T4 — Post-publish smoke test**
  - Query sample locator sau publish; khi fail phải ẩn vector và ghi job failure.
  - **Acceptance:** corpus không tiếp tục phục vụ version có smoke test thất bại.

### Story S4 — Operator quan sát và phục hồi workflow mà không đọc log thô

> Là operator, tôi muốn giao diện cho biết stage, retry và nguyên nhân lỗi để có thể xử lý mà không phải đoán từ Docker logs.

#### Epic S4-E1 — Admin job observability

**Kết quả:** API và UI hiển thị cùng một nguồn trạng thái.

- **Task S4-E1-T1 — Mở rộng `JobSummary`**
  - Trả `job_type`, `stage`, `attempt`, `max_attempts`, `metrics`, `retryable`, `error_code`, `updated_at`.
  - **Acceptance:** schema backend và TypeScript type đồng nhất.

- **Task S4-E1-T2 — Stage-aware progress UI**
  - Hiển thị validate, OCR, chunk, waiting approval, embed, verify và publish.
  - **Acceptance:** reload hoặc chuyển tab không làm mất trạng thái job đang chạy.

- **Task S4-E1-T3 — Actionable error UI**
  - Phân biệt retryable technical error với document/legal error.
  - **Acceptance:** UI chỉ hiện nút retry khi backend trả `retryable=true`.

- **Task S4-E1-T4 — Manual retry endpoint**
  - `POST /jobs/{id}/retry` chỉ nhận failed job có `retryable=true`.
  - **Acceptance:** non-retryable, active hoặc succeeded job trả lỗi nghiệp vụ rõ ràng.

#### Epic S4-E2 — Evaluation và release operations

**Kết quả:** smoke test nhanh nằm trong publish loop; RAGAS đầy đủ vẫn là release gate riêng.

- **Task S4-E2-T1 — Giữ RAGAS ngoài publish path**
  - RAGAS chạy thủ công trước release và theo workflow định kỳ.
  - **Acceptance:** thiếu judge/golden set không ảnh hưởng ingest nhưng làm RAGAS release gate fail-closed.

- **Task S4-E2-T2 — Upload run artifacts**
  - GitHub lưu coding-run reports và RAGAS reports theo workflow run.
  - **Acceptance:** operator truy được command, metrics và kết quả theo run ID.

## 8. Public API và dữ liệu

### 8.1 `JobSummary`

Giữ các field hiện tại và bổ sung:

```text
job_type: INGEST | PUBLISH | REINDEX
stage: string
attempt: integer
max_attempts: integer
metrics: object
retryable: boolean
error_code: string | null
updated_at: datetime
```

### 8.2 Endpoint

- `POST /api/v1/admin/versions` → `202 JobSummary`.
- `GET /api/v1/admin/jobs/{job_id}` → expanded `JobSummary`.
- `POST /api/v1/admin/versions/{version_id}/publish` → đổi thành `202 JobSummary`.
- `POST /api/v1/admin/versions/{version_id}/reindex` → `202 JobSummary`.
- `POST /api/v1/admin/jobs/{job_id}/retry` → `202 JobSummary` khi retry hợp lệ.

### 8.3 State invariants

- Chỉ `PENDING_REVIEW` với structure hash hợp lệ được chuyển sang `PUBLISHING`.
- Chỉ publish job đã verify được chuyển version sang `PUBLISHED`.
- Retrieval không được dùng version khác `PUBLISHED` dù Qdrant payload sai.
- Job terminal không được quay lại running; retry phải tạo attempt mới theo cùng logical job contract.

## 9. Yêu cầu phi chức năng

- **An toàn:** prompt injection bị chặn trước index; LLM không có quyền publish hoặc merge.
- **Idempotency:** retry không tạo provision, job active hoặc vector trùng.
- **Quan sát:** mỗi stage cập nhật heartbeat, progress, metrics và artifact.
- **Khả năng phục hồi:** worker crash không yêu cầu xóa dữ liệu thủ công để chạy lại.
- **Tương thích:** dữ liệu/job hiện có được migration và backfill, không bị xóa.
- **Triển khai:** không thêm container hoặc dependency orchestration mới.

## 10. Chỉ số thành công

- 100% coding PR có full verification summary.
- 0 vector `STAGING` xuất hiện trong public retrieval.
- 100% document jobs có stage, heartbeat và terminal status.
- Retryable failure tự thử lại tối đa đúng 3 lần.
- 100% publish có structure-hash approval và post-publish smoke result.
- Double-click publish/reindex không tạo active job trùng.
- Coding loop dừng khi cùng failure signature xuất hiện 3 lần liên tiếp.

## 11. Test plan cấp sản phẩm

- Unit test state transitions, error taxonomy, retry/backoff và idempotency.
- API test cho expanded `JobSummary`, async publish và manual retry.
- Worker test cho crash tại extraction, chunking, embedding và publish commit.
- Retrieval test bảo đảm `STAGING`/`PUBLISHING` không được trả về.
- Security test bảo đảm unsafe document không retry và không index.
- Frontend test cho polling, reload, retry visibility và terminal states.
- CLI test cho `changed`, `full`, exit codes và failure signature.
- End-to-end test: upload → waiting approval → async publish → verified published → exact-locator query.

## 12. Thứ tự triển khai

1. **P0:** Story S1 — repository contract, verify CLI và CI.
2. **P0:** Story S2/E1-E2 — durable state và observable ingestion.
3. **P0:** Story S2/E3 — retry, stale recovery và deduplication.
4. **P0:** Story S3 — human approval và atomic publication.
5. **P1:** Story S4/E1 — admin observability và manual retry.
6. **P1:** Story S4/E2 — artifact retention và release operation.

Mỗi Epic phải được triển khai bằng TDD, có review riêng và chỉ bắt đầu Epic phụ thuộc khi acceptance criteria của Epic trước đã đạt.

## 13. Definition of Done

- Tất cả task P0 và P1 đạt acceptance criteria.
- Full harness verification trả exit code `0`.
- Backend, frontend và evaluator CI xanh.
- Migration được thử trên snapshot database có dữ liệu cũ.
- Document end-to-end loop chạy thành công và trường hợp crash/retry đã được chứng minh.
- Runbooks và public API documentation khớp behavior thực tế.
- Không còn quyết định publish hoặc merge nào được tự động hóa vượt quá human gate đã chốt.
