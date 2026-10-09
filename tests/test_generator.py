from datetime import date
import pytest
from app.generator.pdf_engine import generate_certificate_pdf
from app.services.generator_service import sanitize_filename


def test_pdf_engine_generates_valid_pdf():
    pdf_bytes = generate_certificate_pdf(
        recipient_name="Alice Smith",
        event_name="Full Stack Development Masterclass",
        issue_date=date(2026, 10, 9),
        certificate_id="CERT-TEST-0001"
    )
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 1000
    assert pdf_bytes.startswith(b"%PDF-")


def test_pdf_engine_handles_extremely_long_names_and_events():
    long_name = "Professor Alexander Maximiliano Von Hohenzollern-Sigmaringen Jr. the Third of Bavaria"
    long_event = "Advanced Distributed Quantum Cryptography and High-Performance Cloud Orchestration Workshop 2026"
    pdf_bytes = generate_certificate_pdf(
        recipient_name=long_name,
        event_name=long_event,
        issue_date="2026-10-09",
        certificate_id="CERT-TEST-LONG"
    )
    assert pdf_bytes.startswith(b"%PDF-")
    assert len(pdf_bytes) > 1000


def test_pdf_engine_handles_super_long_boundary_strings():
    # 300 chars to test ellipsis boundary truncation
    super_long = "X" * 300
    pdf_bytes = generate_certificate_pdf(
        recipient_name=super_long,
        event_name=super_long,
        issue_date="2026-10-09",
        certificate_id="CERT-TEST-BOUNDARY"
    )
    assert pdf_bytes.startswith(b"%PDF-")


def test_pdf_engine_handles_accented_and_unicode_text():
    pdf_bytes = generate_certificate_pdf(
        recipient_name="René François Müller García",
        event_name="Séminaire d'Intelligence Artificielle & España 2026",
        issue_date="2026-10-09",
        certificate_id="CERT-TEST-UNICODE"
    )
    assert pdf_bytes.startswith(b"%PDF-")


def test_sanitize_filename():
    assert sanitize_filename("Alice Smith") == "Alice_Smith"
    assert sanitize_filename("Dr. John O'Connor, Ph.D.") == "Dr_John_OConnor_PhD"
    assert sanitize_filename("   leading and trailing   ") == "leading_and_trailing"
    assert sanitize_filename("!@#$%^&*()") == "recipient"
    assert sanitize_filename("") == "recipient"
    assert sanitize_filename("René Müller") == "René_Müller"
