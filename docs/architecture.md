# System Architecture & Technical Design

## 1. Architectural Overview
The Bulk Certificate Generator Backend follows a modular layered architecture with clean boundaries separating HTTP transport, business orchestration, PDF rendering, storage access, and relational persistence.

```
       +-------------------------------------------------------+
       |                     REST API Client                   |
       +-------------------------------------------------------+
                                  | HTTP (JSON / PDF / ZIP)
                                  v
+---------------------------------------------------------------------+
|                          FastAPI Application                         |
|  - CORS & Error Middleware                                          |
|  - Pydantic Request & Response Serialization                        |
|  - Routers: /certificate-jobs, /certificates, /health               |
+---------------------------------------------------------------------+
        |                                                  |
        v                                                  v
+------------------------------------+    +------------------------------------+
|            Job Service             |    |         Storage Service            |
| - Bulk job creation & validation   |    | - BaseStorageService (ABC)         |
| - Progress calculation from state  |    | - LocalStorageService              |
| - Status aggregation               |    | - Atomic writes & safe paths       |
+------------------------------------+    +------------------------------------+
        |                                                  ^
        v                                                  |
+------------------------------------+                     |
|         Worker / Engine            |                     |
| - Bounded concurrency queue        |---------------------+
| - Batch item isolation             | (Persists PDF files)
| - GenerationService                |
+------------------------------------+
        |                     |
        v                     v
+------------------+  +------------------------------------+
| PDF Engine       |  | Relational Persistence (SQLAlchemy)|
| - ReportLab      |  | - GenerationJob                    |
| - Dynamic sizing |  | - CertificateRecipient             |
| - Typography     |  | - SQLite / PostgreSQL (Alembic)    |
+------------------+  +------------------------------------+
```

---

## 2. Entity Relationship (ER) Model

```
+-----------------------------------------------------------------+
|                       GenerationJob                             |
+-----------------------------------------------------------------+
| PK  id                  VARCHAR(36) / UUID                     |
|     event_name          VARCHAR(255)                           |
|     issue_date          DATE                                   |
|     status              VARCHAR(32) [PENDING, PROCESSING, ...] |
|     total_recipients    INTEGER                                |
|     pending_count       INTEGER                                |
|     processing_count    INTEGER                                |
|     successful_count    INTEGER                                |
|     failed_count        INTEGER                                |
|     error_summary       TEXT (nullable)                        |
|     created_at          TIMESTAMP WITH TIME ZONE               |
|     updated_at          TIMESTAMP WITH TIME ZONE               |
|     completed_at        TIMESTAMP WITH TIME ZONE (nullable)    |
+-----------------------------------------------------------------+
                                 | 1
                                 |
                                 | 1..N
                                 v
+-----------------------------------------------------------------+
|                    CertificateRecipient                         |
+-----------------------------------------------------------------+
| PK  id                  VARCHAR(36) / UUID                     |
| FK  job_id              VARCHAR(36) -> GenerationJob.id        |
|     recipient_name      VARCHAR(255)                           |
|     recipient_email     VARCHAR(255)                           |
|     status              VARCHAR(32) [PENDING, SUCCESS, FAILED] |
|     certificate_id      VARCHAR(36) (unique, nullable)         |
|     storage_key         VARCHAR(512) (nullable)                |
|     file_size_bytes     INTEGER (nullable)                     |
|     error_code          VARCHAR(64) (nullable)                 |
|     error_message       TEXT (nullable)                        |
|     retry_count         INTEGER DEFAULT 0                      |
|     created_at          TIMESTAMP WITH TIME ZONE               |
|     updated_at          TIMESTAMP WITH TIME ZONE               |
+-----------------------------------------------------------------+
```

### Constraints & Indexes
1. `GenerationJob`:
   - Primary Key: `id` (UUIDv4)
   - Index on `(status, created_at)` for job monitoring.
2. `CertificateRecipient`:
   - Primary Key: `id` (UUIDv4)
   - Foreign Key: `job_id` referencing `GenerationJob.id` with `ON DELETE CASCADE`.
   - Unique Index: `certificate_id` (enforces strict uniqueness across certificates).
   - Index on `(job_id, status)` for fast progress calculations and aggregate counts.

---

## 3. Finite State Machine (FSM)

### Job State Machine
- `PENDING`: Initial state when job is created and persisted with all recipients.
- `PROCESSING`: Background worker picks up the job and begins processing recipients.
- `COMPLETED`: All recipients finished, and `successful_count == total_recipients`.
- `PARTIALLY_COMPLETED`: All recipients finished, with both successes and failures (`successful_count > 0` and `failed_count > 0`).
- `FAILED`: Job level failure (e.g., all recipients failed, or fatal job abort).

```
   [CREATED]
       |
       v
   [PENDING] ---------> [PROCESSING] ---------> [COMPLETED] (100% success)
                              |      ---------> [PARTIALLY_COMPLETED] (Mixed)
                              +---------------> [FAILED] (100% failure or fatal)
```

### Recipient State Machine
- `PENDING`: Enqueued, awaiting generation.
- `PROCESSING`: Acquired by worker thread / task.
- `SUCCESS`: PDF generated, stored, checksum/size validated, certificate_id assigned.
- `FAILED`: Validation error or PDF generation exception; error code and message logged. Terminal state.

---

## 4. Background Processing Strategy
To balance operational simplicity, zero external broker dependencies (like Redis/RabbitMQ), and high throughput:
1. **Database-Backed Asynchronous Task Pipeline**:
   - Jobs and recipients are committed into the relational DB first before the HTTP request returns `202 Accepted`.
   - An asynchronous task runner utilizing an `asyncio.Semaphore` (bounded concurrency) renders PDFs concurrently up to a configurable worker limit (`MAX_CONCURRENT_WORKERS = 4` default).
   - For long-running or distributed production deployments, the database status polling worker model (`SELECT ... FOR UPDATE SKIP LOCKED` or job queue table) is easily supported.
2. **Transaction Boundaries**:
   - The database transaction is closed BEFORE PDF generation begins.
   - Each recipient update (`SUCCESS` / `FAILED` + storage key) executes within an isolated lightweight database transaction upon completion.
   - Job counters are updated atomically or recalculated directly from the recipient records to guarantee zero divergence.

---

## 5. Storage Abstraction
```python
class BaseStorageService(ABC):
    @abstractmethod
    async def save_file(self, content: bytes, storage_key: str) -> str: ...
    @abstractmethod
    async def get_file(self, storage_key: str) -> bytes: ...
    @abstractmethod
    async def file_exists(self, storage_key: str) -> bool: ...
    @abstractmethod
    async def delete_file(self, storage_key: str) -> bool: ...
```
- Standard local storage uses an isolated directory (`storage/certificates/`), creates deterministic sanitized names (`{certificate_id}.pdf`), and utilizes atomic file writing (`.tmp` write followed by rename) to prevent partial file reads.
