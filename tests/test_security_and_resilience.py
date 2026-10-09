import pytest
from app.models.job import JobStatus
from app.storage.local_storage import LocalStorageService


def test_health_and_readiness_probes(client):
    health_resp = client.get("/health")
    assert health_resp.status_code == 200
    assert health_resp.json()["status"] == "healthy"

    ready_resp = client.get("/ready")
    assert ready_resp.status_code == 200
    assert ready_resp.json()["status"] == "ready"
    assert ready_resp.json()["database"] == "connected"

    # Also test under /api/v1 prefix
    api_health = client.get("/api/v1/health")
    assert api_health.status_code == 200

    api_ready = client.get("/api/v1/ready")
    assert api_ready.status_code == 200


def test_path_traversal_protection(test_temp_dir):
    storage = LocalStorageService(base_dir=str(test_temp_dir / "storage_sec"))
    malicious_keys = [
        "../../etc/passwd",
        "..\\..\\windows\\system32\\calc.exe",
        "foo/../../../outside.txt",
        "C:\\Windows\\System32\\cmd.exe",
        "D:\\malicious.exe"
    ]
    for key in malicious_keys:
        with pytest.raises(ValueError, match="Security error: Invalid storage key"):
            storage._resolve_safe_path(key)


def test_storage_lifecycle_atomic_write_and_read(test_temp_dir):
    storage = LocalStorageService(base_dir=str(test_temp_dir / "storage_lifecycle"))
    test_key = "test_folder/certificate_01.pdf"
    test_bytes = b"%PDF-1.4 Mock certificate content"

    # Save
    saved_path = storage.save_file(test_bytes, test_key)
    assert storage.file_exists(test_key) is True

    # Read
    read_bytes = storage.get_file(test_key)
    assert read_bytes == test_bytes

    # Delete
    assert storage.delete_file(test_key) is True
    assert storage.file_exists(test_key) is False


def test_generator_runtime_failure_isolation(client, monkeypatch):
    """
    Simulate an unexpected PDF generator crash on one specific recipient,
    verifying that the other recipient survives and finishes successfully.
    """
    from app.services import generator_service

    original_generate = generator_service.generate_certificate_pdf

    def faulty_generate(recipient_name, event_name, issue_date, certificate_id):
        if "Flaky" in recipient_name:
            raise RuntimeError("Simulated transient rendering engine crash!")
        return original_generate(recipient_name, event_name, issue_date, certificate_id)

    monkeypatch.setattr(generator_service, "generate_certificate_pdf", faulty_generate)

    payload = {
        "event_name": "Resilience Test",
        "issue_date": "2026-10-09",
        "recipients": [
            {"name": "Solid User", "email": "solid@example.com"},
            {"name": "Flaky User", "email": "flaky@example.com"}
        ]
    }
    resp = client.post("/api/v1/certificate-jobs", json=payload)
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    status_resp = client.get(f"/api/v1/certificate-jobs/{job_id}")
    assert status_resp.status_code == 200
    data = status_resp.json()
    assert data["status"] == JobStatus.PARTIALLY_COMPLETED.value
    assert data["successful_count"] == 1
    assert data["failed_count"] == 1

    flaky_rec = next(r for r in data["recipients"] if r["recipient_name"] == "Flaky User")
    assert flaky_rec["status"] == "FAILED"
    assert flaky_rec["error_code"] == "GENERATION_FAILED"
    assert "Simulated transient rendering engine crash" in flaky_rec["error_message"]

    solid_rec = next(r for r in data["recipients"] if r["recipient_name"] == "Solid User")
    assert solid_rec["status"] == "SUCCESS"
