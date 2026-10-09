# Assumptions & Risk Analysis

## 1. Architectural & Domain Assumptions
1. **Relational Database Engine**:
   - *Assumption*: SQLite is used by default for local development and zero-infrastructure automated testing (`sqlite:///./certificates.db`), while PostgreSQL is supported without code changes via standard `DATABASE_URL` for production deployment.
   - *Rationale*: Allows developers and reviewers to clone, test, and run the backend immediately without needing an active PostgreSQL service or external container running, while maintaining full SQLAlchemy ORM compatibility.
2. **Worker & Concurrency Model**:
   - *Assumption*: A background processing worker with an internal bounded concurrency mechanism (using `asyncio.Semaphore` / thread-pool bounded workers) satisfies the requirement of prompt response times without the operational overhead of external brokers like RabbitMQ or Redis.
   - *Rationale*: Avoids unnecessary paid infrastructure and complex multi-container orchestration for modest-to-high batch sizes (e.g. hundreds of certificates per batch), while completely decoupling HTTP request latency from PDF generation.
3. **Duplicate Recipients Policy**:
   - *Assumption*: Duplicate email addresses within a single batch submission are detected. If two recipients share the same email or identical name+email in the same batch, the second is flagged with a recipient-level failure code (`DUPLICATE_RECIPIENT_IN_BATCH`) while the first proceeds, or deduplicated transparently based on system configuration.
   - *Rationale*: Prevents accidental duplicate certificate generation and storage bloat while keeping failure isolated to the duplicate entry.
4. **Certificate Design & Predefined Template**:
   - *Assumption*: Since no external proprietary graphical certificate template was committed in the repository, a clean, high-resolution predefined template will be programmatically generated via ReportLab using professional geometric borders, typographic hierarchy, issue date, dynamic text auto-scaling, and a distinct certificate UUID watermark/identifier.
5. **Security & Authentication Scope**:
   - *Assumption*: The core assignment requirements focus on the bulk job generation lifecycle, validation, PDF engine, and file delivery. Endpoints are built with security best practices (path traversal protection, strict Pydantic payload sanitation, no stack traces leaked in error responses, CORS headers). An optional API key / Bearer auth middleware hook is structured for production deployment.

---

## 2. Risk Matrix & Mitigations

| Risk | Likelihood | Impact | Mitigation Strategy |
|---|---|---|---|
| **Memory Spike on Large Batches** (Generating hundreds of PDFs concurrently) | Medium | High | Bounded concurrency worker (e.g., maximum 4 to 8 parallel rendering tasks). Each PDF is streamed directly to disk via ReportLab canvas, not buffered in long-lived memory. |
| **Partial File Reads / Corrupted PDFs** (Worker crashes or file read during write) | Low | High | Atomic writes: write to `.tmp` file first, flush and sync, then rename atomically to `{certificate_id}.pdf`. DB record marked `SUCCESS` only after file is confirmed on disk. |
| **Database Transaction Lock / Timeout** | Medium | Medium | Never hold an open DB transaction across PDF generation. Read recipient -> release transaction -> render PDF -> open brief transaction to update status to SUCCESS or FAILED. |
| **Path Traversal Vulnerabilities** (`../` in inputs or certificate ID) | Medium | High | Enforce strict UUID format validation for `job_id` and `certificate_id`. Local storage enforces strict path resolution and verifies path stays within configured base directory. |
| **Long Recipient or Event Names Clipping** | High | Low | Dynamic font size auto-calculation in ReportLab template: if text width exceeds printable margin, font size scales down gracefully down to a readable minimum. |
| **Worker Interruption / Crash** | Low | Medium | Persisted recipient states (`PENDING`, `PROCESSING`) allow reconciliation on startup or retries. Terminal states (`SUCCESS`, `FAILED`) are idempotent. |
