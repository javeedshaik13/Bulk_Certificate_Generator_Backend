# Requirements & Requirements Traceability Matrix (RTM)

## 1. Project Overview
The Bulk Certificate Generator Backend is a production-conscious RESTful service designed to process, generate, and distribute bulk digital certificates using a predefined PDF template. It is engineered with robust data validation, failure isolation, asynchronous job-based batch processing, comprehensive relational data persistence, and secure file delivery.

---

## 2. Scope & Requirement Classification

### Mandatory Requirements
- **REQ-01: Framework & Runtime**: Python 3.12+ using FastAPI, Pydantic v2, SQLAlchemy 2.0, and a relational database.
- **REQ-02: Bulk Job Creation (`POST /api/v1/certificate-jobs`)**:
  - Accept certificate-level metadata (`event_name`, `issue_date`) and a list of `recipients` (`name`, `email`).
  - Validate request payload; reject malformed requests with standard HTTP 422/400 errors.
  - Return unique `job_id` and HTTP 202 Accepted without blocking HTTP client during rendering.
- **REQ-03: Job Status & Progress Tracking (`GET /api/v1/certificate-jobs/{job_id}`)**:
  - Return `job_id`, status (`PENDING`, `PROCESSING`, `COMPLETED`, `PARTIALLY_COMPLETED`, `FAILED`), total count, pending count, processing count, successful count, failed count.
  - Return creation and completion timestamps.
  - Include detailed per-recipient records with individual failure codes and messages.
  - Counters must strictly derive from persisted recipient states.
- **REQ-04: Certificate Generation Engine**:
  - Predefined, visually professional PDF template rendered using ReportLab.
  - Dynamic recipient name, event name, issue date, and unique certificate identifier.
  - Handling of long text strings (dynamic font scaling / wrapping) without layout clipping.
  - Atomic file write to avoid corrupted or partially-written PDF files.
- **REQ-05: Single Certificate Retrieval (`GET /api/v1/certificates/{certificate_id}`)**:
  - Stream or serve certificate PDF with appropriate MIME type (`application/pdf`) and content-disposition headers.
  - Return standard 404 for nonexistent or failed certificates.
- **REQ-06: Failure Isolation**:
  - Recipient-level failure (e.g. malformed email or PDF rendering failure) must not abort the batch.
  - Surviving recipients must continue to be processed and marked succeeded.
  - Failure code and sanitized error message persisted per recipient.
- **REQ-07: Relational Data Persistence & Schema Migrations**:
  - SQLAlchemy models for `GenerationJob` and `CertificateRecipient`.
  - Database schema migrations managed via Alembic.
  - Supported relational DB: SQLite for local zero-dependency development/testing and PostgreSQL for production via connection string.
- **REQ-08: Storage Abstraction**:
  - Storage layer decoupling disk operations (`LocalStorageService`) to allow zero-code-change cloud storage extension (e.g., S3/GCS).
  - Safe path sanitization preventing path traversal attacks.
- **REQ-09: Automated Test Suite**:
  - Automated testing using `pytest` and `httpx.AsyncClient` / `TestClient`.
  - Full coverage of job submission, polling, individual retrieval, failure isolation, validation, boundary checks.

### Optional / Enhancements (Evaluated & Included)
- **OPT-01: Bulk ZIP Download (`GET /api/v1/certificate-jobs/{job_id}/zip`)**: Stream/generate a ZIP archive containing all successful PDFs for a completed job.
- **OPT-02: Health & Readiness Probes (`GET /api/v1/health` & `/api/v1/ready`)**: Standardized liveness and database-connectivity readiness probes.
- **OPT-03: Duplicate Recipient Policy**: Explicit policy configurable in job submission (e.g. allow deduplication or mark duplicates with a dedicated failure code).

---

## 3. Requirements Traceability Matrix (RTM)

| Requirement ID | Exact Requirement | Proposed Implementation | Relevant File / Module | Verification Method | Status |
|---|---|---|---|---|---|
| **REQ-01** | Python FastAPI + SQLAlchemy + Relational DB | FastAPI app, SQLAlchemy 2.0 ORM, Alembic migrations, Pydantic v2 schemas | `app/main.py`, `app/core/database.py`, `alembic/` | App boots, Alembic runs migrations clean | Planned |
| **REQ-02** | Bulk generation job creation endpoint | `POST /api/v1/certificate-jobs` accepting payload, persisting job + recipients, spawning async worker, returning 202 | `app/api/v1/jobs.py`, `app/services/job_service.py` | API unit & integration test with valid/invalid payloads | Planned |
| **REQ-03** | Job status and progress tracking | `GET /api/v1/certificate-jobs/{job_id}` reporting live counts, timestamps, recipient list with errors | `app/api/v1/jobs.py`, `app/services/job_service.py` | Poll job endpoint during and after completion, verify exact counts | Planned |
| **REQ-04** | Predefined PDF Certificate Template | ReportLab canvas rendering elegant border, typography, auto-scaling name, issue date, unique ID | `app/generator/pdf_engine.py`, `app/generator/template.py` | Generate real PDF, verify non-empty bytes, valid PDF header, text inspection | Planned |
| **REQ-05** | Individual certificate retrieval | `GET /api/v1/certificates/{certificate_id}` returning PDF file stream with safe headers | `app/api/v1/certificates.py`, `app/storage/local_storage.py` | Download generated PDF via HTTP, verify Content-Type and binary body | Planned |
| **REQ-06** | Recipient-level failure isolation | Try-catch per recipient during execution; record failure reason, commit state, continue remaining | `app/services/generator_service.py` | Inject malformed recipient in batch of 5; verify 4 succeed, 1 fails, job partially completed | Planned |
| **REQ-07** | Relational data model & migrations | `GenerationJob` & `CertificateRecipient` models with foreign keys, indexes, status enums | `app/models/job.py`, `app/models/recipient.py` | Alembic upgrade head; schema inspected in SQLite/Postgres | Planned |
| **REQ-08** | Storage abstraction & safe paths | `BaseStorageService` ABC and `LocalStorageService` with UUID storage keys & safe path joins | `app/storage/base.py`, `app/storage/local_storage.py` | Path traversal unit tests (`../../etc/passwd`), atomic file writes | Planned |
| **REQ-09** | Automated testing | pytest suite covering happy paths, failure isolation, validation, retrieval, concurrency | `tests/test_api_jobs.py`, `tests/test_generator.py`, `tests/test_retrieval.py` | Run `pytest -v --cov=app` with 100% test pass rate | Planned |
| **OPT-01** | Bulk ZIP archive retrieval | `GET /api/v1/certificate-jobs/{job_id}/zip` streaming or serving ZIP of all successful PDFs | `app/api/v1/jobs.py`, `app/services/job_service.py` | Request ZIP, extract in memory, verify contained PDFs match successful count | Planned |
| **OPT-02** | Health check endpoints | `GET /api/v1/health` and `GET /api/v1/ready` checking DB liveness | `app/api/v1/health.py` | Automated tests verify 200 OK and DB connection check | Planned |
