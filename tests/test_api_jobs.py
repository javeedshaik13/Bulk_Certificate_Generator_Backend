import pytest
from app.models.job import JobStatus
from app.models.recipient import RecipientStatus


def test_create_bulk_job_happy_path(client):
    payload = {
        "event_name": "Cloud Native Architecture 2026",
        "issue_date": "2026-10-09",
        "recipients": [
            {"name": "Alice Anderson", "email": "alice@example.com"},
            {"name": "Bob Builder", "email": "bob@example.com"}
        ]
    }
    response = client.post("/api/v1/certificate-jobs", json=payload)
    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert data["status"] in [JobStatus.PENDING.value, JobStatus.COMPLETED.value]
    assert data["total_recipients"] == 2
    assert "status_url" in data

    job_id = data["job_id"]
    status_resp = client.get(f"/api/v1/certificate-jobs/{job_id}")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["id"] == job_id
    assert status_data["status"] == JobStatus.COMPLETED.value
    assert status_data["successful_count"] == 2
    assert status_data["failed_count"] == 0
    assert status_data["pending_count"] == 0
    assert status_data["processing_count"] == 0
    assert status_data["completed_at"] is not None
    assert len(status_data["recipients"]) == 2
    for rec in status_data["recipients"]:
        assert rec["status"] == RecipientStatus.SUCCESS.value
        assert rec["certificate_id"] is not None
        assert rec["download_url"] is not None


def test_create_bulk_job_validation_empty_recipients(client):
    payload = {
        "event_name": "Workshop",
        "issue_date": "2026-10-09",
        "recipients": []
    }
    response = client.post("/api/v1/certificate-jobs", json=payload)
    assert response.status_code == 422
    data = response.json()
    assert data["error_code"] == "VALIDATION_ERROR"


def test_create_bulk_job_validation_blank_event_name(client):
    payload = {
        "event_name": "   ",
        "issue_date": "2026-10-09",
        "recipients": [{"name": "Test User", "email": "test@example.com"}]
    }
    response = client.post("/api/v1/certificate-jobs", json=payload)
    assert response.status_code == 422
    data = response.json()
    assert data["error_code"] == "VALIDATION_ERROR"


def test_create_bulk_job_validation_invalid_date(client):
    payload = {
        "event_name": "Workshop",
        "issue_date": "not-a-valid-date",
        "recipients": [{"name": "Test User", "email": "test@example.com"}]
    }
    response = client.post("/api/v1/certificate-jobs", json=payload)
    assert response.status_code == 422


def test_failure_isolation_with_mixed_batch(client):
    payload = {
        "event_name": "Data Engineering Bootcamp",
        "issue_date": "2026-10-09",
        "recipients": [
            {"name": "Valid Recipient", "email": "valid@example.com"},
            {"name": "Bad Email Recipient", "email": "not-an-email"},
            {"name": "   ", "email": "blankname@example.com"},
            {"name": "Duplicate Recipient", "email": "valid@example.com"}
        ]
    }
    response = client.post("/api/v1/certificate-jobs", json=payload)
    assert response.status_code == 202
    job_id = response.json()["job_id"]

    status_resp = client.get(f"/api/v1/certificate-jobs/{job_id}")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["status"] == JobStatus.PARTIALLY_COMPLETED.value
    assert status_data["total_recipients"] == 4
    assert status_data["successful_count"] == 1
    assert status_data["failed_count"] == 3

    errors_by_code = {r["error_code"] for r in status_data["recipients"] if r["error_code"]}
    assert "INVALID_EMAIL" in errors_by_code
    assert "INVALID_NAME" in errors_by_code
    assert "DUPLICATE_RECIPIENT_IN_BATCH" in errors_by_code


def test_all_recipients_invalid_results_in_failed_job(client):
    payload = {
        "event_name": "Failed Workshop",
        "issue_date": "2026-10-09",
        "recipients": [
            {"name": "Invalid One", "email": "no-at-sign"},
            {"name": "", "email": "empty-name@example.com"}
        ]
    }
    response = client.post("/api/v1/certificate-jobs", json=payload)
    assert response.status_code == 202
    job_id = response.json()["job_id"]

    status_resp = client.get(f"/api/v1/certificate-jobs/{job_id}")
    assert status_resp.status_code == 200
    data = status_resp.json()
    assert data["status"] == JobStatus.FAILED.value
    assert data["successful_count"] == 0
    assert data["failed_count"] == 2
    assert data["completed_at"] is not None


def test_duplicate_policy_allow(client):
    payload = {
        "event_name": "Dual Track Certificate",
        "issue_date": "2026-10-09",
        "duplicate_policy": "allow",
        "recipients": [
            {"name": "Same Person Track A", "email": "shared@example.com"},
            {"name": "Same Person Track B", "email": "shared@example.com"}
        ]
    }
    response = client.post("/api/v1/certificate-jobs", json=payload)
    assert response.status_code == 202
    job_id = response.json()["job_id"]

    status_resp = client.get(f"/api/v1/certificate-jobs/{job_id}")
    data = status_resp.json()
    assert data["status"] == JobStatus.COMPLETED.value
    assert data["successful_count"] == 2
    assert data["failed_count"] == 0


def test_duplicate_policy_deduplicate(client):
    payload = {
        "event_name": "Deduplicated Workshop",
        "issue_date": "2026-10-09",
        "duplicate_policy": "deduplicate",
        "recipients": [
            {"name": "First Entry", "email": "unique@example.com"},
            {"name": "Second Entry", "email": "unique@example.com"}
        ]
    }
    response = client.post("/api/v1/certificate-jobs", json=payload)
    assert response.status_code == 202
    job_id = response.json()["job_id"]

    status_resp = client.get(f"/api/v1/certificate-jobs/{job_id}")
    data = status_resp.json()
    assert data["status"] == JobStatus.PARTIALLY_COMPLETED.value
    assert data["successful_count"] == 1
    assert data["failed_count"] == 1
    error_codes = [r["error_code"] for r in data["recipients"] if r["error_code"]]
    assert "DEDUPLICATED" in error_codes


def test_get_nonexistent_job_returns_404(client):
    response = client.get("/api/v1/certificate-jobs/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


def test_root_endpoint(client):
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert "app" in data


def test_exceeds_max_recipients_limit(client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "MAX_RECIPIENTS_PER_JOB", 2)

    payload = {
        "event_name": "Overloaded Workshop",
        "issue_date": "2026-10-09",
        "recipients": [
            {"name": f"User {i}", "email": f"user{i}@example.com"}
            for i in range(3)
        ]
    }
    response = client.post("/api/v1/certificate-jobs", json=payload)
    assert response.status_code == 422
    assert "maximum allowed limit" in response.text
