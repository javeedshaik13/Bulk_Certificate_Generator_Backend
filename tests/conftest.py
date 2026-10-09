import os
import shutil
import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.database import get_db
from app.main import app
from app.models.base import Base
from app.storage.local_storage import LocalStorageService


@pytest.fixture(scope="session")
def test_temp_dir():
    temp_dir = tempfile.mkdtemp(prefix="test_cert_storage_")
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture(scope="session")
def test_db_path(test_temp_dir):
    return test_temp_dir / "test_certificates.db"


@pytest.fixture(scope="session")
def test_engine(test_db_path):
    engine = create_engine(
        f"sqlite:///{test_db_path}",
        connect_args={"check_same_thread": False, "timeout": 30.0}
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session(test_engine):
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(test_engine, test_temp_dir, monkeypatch):
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    # Monkeypatch storage service to use isolated temp directory
    test_storage = LocalStorageService(base_dir=str(test_temp_dir / "certs"))
    monkeypatch.setattr("app.storage.local_storage.storage_service", test_storage)
    monkeypatch.setattr("app.services.generator_service.storage_service", test_storage)
    monkeypatch.setattr("app.services.job_service.storage_service", test_storage)
    monkeypatch.setattr("app.api.v1.certificates.storage_service", test_storage)

    # Monkeypatch SessionLocal in job_service so background tasks use test database
    monkeypatch.setattr("app.services.job_service.SessionLocal", TestingSessionLocal)

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
