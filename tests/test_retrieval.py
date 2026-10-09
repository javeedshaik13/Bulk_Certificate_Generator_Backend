import io
import zipfile
import pytest


def test_certificate_and_zip_retrieval_flow(client):
    # 1. Create job with 2 valid and 1 invalid recipient
    payload = {
        "event_name": "API Design Masterclass",
        "issue_date": "2026-10-09",
        "recipients": [
            {"name": "Carol Danvers", "email": "carol@example.com"},
            {"name": "Diana Prince", "email": "diana@example.com"},
            {"name": "Malformed User", "email": "invalid-email"}
        ]
    }
    create_resp = client.post("/api/v1/certificate-jobs", json=payload)
    assert create_resp.status_code == 202
    job_id = create_resp.json()["job_id"]

    # 2. Get status and extract certificate IDs
    status_resp = client.get(f"/api/v1/certificate-jobs/{job_id}")
    assert status_resp.status_code == 200
    job_data = status_resp.json()
    assert job_data["successful_count"] == 2
    assert job_data["failed_count"] == 1

    successful_recs = [r for r in job_data["recipients"] if r["status"] == "SUCCESS"]
    failed_recs = [r for r in job_data["recipients"] if r["status"] == "FAILED"]
    assert len(successful_recs) == 2
    assert len(failed_recs) == 1

    # 3. Download individual successful certificates
    for rec in successful_recs:
        cert_id = rec["certificate_id"]
        dl_resp = client.get(f"/api/v1/certificates/{cert_id}")
        assert dl_resp.status_code == 200
        assert dl_resp.headers["content-type"] == "application/pdf"
        assert dl_resp.content.startswith(b"%PDF-")
        assert len(dl_resp.content) > 1000

    # 4. Download nonexistent certificate returns 404
    nonexistent_resp = client.get("/api/v1/certificates/CERT-NONEXISTENT")
    assert nonexistent_resp.status_code == 404

    # 5. Download ZIP archive
    zip_resp = client.get(f"/api/v1/certificate-jobs/{job_id}/zip")
    assert zip_resp.status_code == 200
    assert zip_resp.headers["content-type"] == "application/zip"

    # Verify ZIP contents
    with zipfile.ZipFile(io.BytesIO(zip_resp.content)) as zf:
        namelist = zf.namelist()
        assert len(namelist) == 2
        for name in namelist:
            assert name.endswith(".pdf")
            pdf_data = zf.read(name)
            assert pdf_data.startswith(b"%PDF-")


def test_zip_retrieval_when_all_failed_returns_404(client):
    payload = {
        "event_name": "Failed Batch",
        "issue_date": "2026-10-09",
        "recipients": [
            {"name": "Bad One", "email": "bad1"},
            {"name": "Bad Two", "email": "bad2"}
        ]
    }
    create_resp = client.post("/api/v1/certificate-jobs", json=payload)
    job_id = create_resp.json()["job_id"]

    zip_resp = client.get(f"/api/v1/certificate-jobs/{job_id}/zip")
    assert zip_resp.status_code == 404


def test_zip_retrieval_nonexistent_job_returns_404(client):
    zip_resp = client.get("/api/v1/certificate-jobs/00000000-0000-0000-0000-000000000000/zip")
    assert zip_resp.status_code == 404


def test_retrieval_cert_status_not_success_returns_404(client, db_session):
    from app.models.job import GenerationJob, JobStatus
    from app.models.recipient import CertificateRecipient, RecipientStatus
    import uuid
    from datetime import date

    job = GenerationJob(
        id=str(uuid.uuid4()),
        event_name="Test Event",
        issue_date=date(2026, 10, 9),
        status=JobStatus.PROCESSING.value,
        total_recipients=1
    )
    rec = CertificateRecipient(
        id=str(uuid.uuid4()),
        job_id=job.id,
        recipient_name="Pending User",
        recipient_email="pending@example.com",
        status=RecipientStatus.PROCESSING.value,
        certificate_id="CERT-PENDING-001"
    )
    db_session.add(job)
    db_session.add(rec)
    db_session.commit()

    resp = client.get(f"/api/v1/certificates/{rec.certificate_id}")
    assert resp.status_code == 404
    assert "not in a valid completed state" in resp.json()["message"]


def test_retrieval_cert_file_missing_on_disk_returns_404(client, db_session):
    from app.models.job import GenerationJob, JobStatus
    from app.models.recipient import CertificateRecipient, RecipientStatus
    import uuid
    from datetime import date

    job = GenerationJob(
        id=str(uuid.uuid4()),
        event_name="Ghost Event",
        issue_date=date(2026, 10, 9),
        status=JobStatus.COMPLETED.value,
        total_recipients=1
    )
    rec = CertificateRecipient(
        id=str(uuid.uuid4()),
        job_id=job.id,
        recipient_name="Ghost User",
        recipient_email="ghost@example.com",
        status=RecipientStatus.SUCCESS.value,
        certificate_id="CERT-GHOST-999",
        storage_key="nonexistent_ghost_file.pdf"
    )
    db_session.add(job)
    db_session.add(rec)
    db_session.commit()

    resp = client.get(f"/api/v1/certificates/{rec.certificate_id}")
    assert resp.status_code == 404
    assert "could not be located" in resp.json()["message"]
