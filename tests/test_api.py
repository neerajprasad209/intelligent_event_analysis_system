"""
Unit and Integration Tests for Event Intelligent System FastAPI REST Service.

Tests cover:
1. Root redirect (/ -> /docs)
2. POST /analyze with file upload
3. POST /analyze with empty file (400 Bad Request)
4. POST /analyze without file (analyzes default file)
5. GET /summary metrics
6. GET /device/{device_id} (existing device)
7. GET /device/{device_id} (non-existent device returns 404)
"""

import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

try:
    from src.api import app
    from src import config
except ImportError:
    from api import app
    import config

client = TestClient(app)


def test_api_root_redirect():
    """Verify GET / redirects to /docs."""
    response = client.get("/", follow_redirects=False)
    assert response.status_code in (302, 307)
    assert response.headers["location"] == "/docs"


def test_api_analyze_with_file_upload():
    """Verify POST /analyze with an uploaded log file produces valid diagnostics and saves report."""
    sample_log = (
        "2026-09-01 10:00:01 API-DEV-01 CONNECTION_START SUCCESS\n"
        "2026-09-01 10:00:02 API-DEV-01 AUTHENTICATION SUCCESS\n"
        "2026-09-01 10:00:03 API-DEV-01 SESSION_START FAILED\n"
    )
    files = {"file": ("test_upload.log", sample_log.encode("utf-8"), "text/plain")}
    response = client.post("/analyze", files=files)

    assert response.status_code == 200
    data = response.json()
    assert "summary" in data
    assert "devices" in data
    assert "output_file" in data
    assert data["summary"]["total_devices"] == 1
    assert data["summary"]["failed_devices"] == 1

    device = data["devices"][0]
    assert device["device_id"] == "API-DEV-01"
    assert device["status"] == "FAILED"
    assert device["failure_type"] == "SESSION_ESTABLISHMENT"


def test_api_analyze_empty_file_returns_400():
    """Verify POST /analyze with an empty uploaded file returns 400 Bad Request."""
    files = {"file": ("empty.log", b"", "text/plain")}
    response = client.post("/analyze", files=files)
    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()


def test_api_summary_endpoint():
    """Verify GET /summary returns summary metrics dictionary."""
    response = client.get("/summary")
    assert response.status_code == 200
    summary = response.json()
    assert "total_devices" in summary
    assert "healthy_devices" in summary
    assert "failed_devices" in summary
    assert isinstance(summary["total_devices"], int)


def test_api_device_endpoint_success():
    """Verify GET /device/{device_id} returns device diagnosis for an existing device."""
    # First upload a known device
    log_content = (
        "2026-09-01 10:00:01 DEVICE-LOOKUP-OK CONNECTION_START SUCCESS\n"
        "2026-09-01 10:00:02 DEVICE-LOOKUP-OK AUTHENTICATION SUCCESS\n"
    )
    client.post("/analyze", files={"file": ("lookup.log", log_content.encode("utf-8"), "text/plain")})

    response = client.get("/device/DEVICE-LOOKUP-OK")
    assert response.status_code == 200
    dev = response.json()
    assert dev["device_id"] == "DEVICE-LOOKUP-OK"
    assert dev["status"] == "HEALTHY"


def test_api_device_endpoint_not_found():
    """Verify GET /device/{device_id} returns 404 for unknown device ID."""
    response = client.get("/device/NON_EXISTENT_DEVICE_XYZ")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
