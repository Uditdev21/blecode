import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient

from config import get_settings
from database import DatabaseManager, get_db
from main import app

TEST_API_KEY = "test_tronn_secret_token_123"
AUTH_HEADERS = {"token": TEST_API_KEY}


@pytest.fixture(autouse=True)
def setup_test_environment(monkeypatch):
    """Create an isolated test DB and test API token for each test."""
    temp_dir = tempfile.mkdtemp()
    temp_db_path = os.path.join(temp_dir, "test_db.json")

    # Set test API key in settings
    monkeypatch.setenv("API_KEY", TEST_API_KEY)
    monkeypatch.setenv("DB_PATH", temp_db_path)
    get_settings.cache_clear()

    test_manager = DatabaseManager(db_path=temp_db_path)
    app.dependency_overrides[get_db] = lambda: test_manager

    yield test_manager

    # Teardown
    test_manager.close()
    app.dependency_overrides.clear()
    get_settings.cache_clear()
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def client():
    return TestClient(app)


def test_public_root_and_health(client):
    """Root and health endpoints should be public and reflect Tronn product branding."""
    root_res = client.get("/")
    assert root_res.status_code == 200
    body = root_res.json()
    assert body["status"] == "healthy"
    assert body["developer"] == "Tronn"
    assert "endpoints" in body

    health_res = client.get("/health")
    assert health_res.status_code == 200
    assert health_res.json()["status"] == "ok"
    assert health_res.json()["developer"] == "Tronn"


def test_authentication_required(client):
    """Data endpoints should reject requests missing the 'token' header with 401."""
    # POST without token
    res1 = client.post("/api/v1/data", json={"sample": "data"})
    assert res1.status_code == 401
    assert "Missing 'token' authentication header" in res1.json()["detail"]

    # GET latest without token
    res2 = client.get("/api/v1/data/latest")
    assert res2.status_code == 401

    # GET sync without token
    res3 = client.get("/api/v1/data/sync")
    assert res3.status_code == 401

    # DELETE without token
    res4 = client.delete("/api/v1/data/1")
    assert res4.status_code == 401

    # Export without token
    res5 = client.get("/api/v1/data/export")
    assert res5.status_code == 401

    # Invalid token
    res6 = client.get("/api/v1/data/latest", headers={"token": "wrong_key"})
    assert res6.status_code == 401
    assert "Invalid API token provided" in res6.json()["detail"]


def test_save_payload_and_get_latest(client):
    # Initially database is empty
    empty_latest = client.get("/api/v1/data/latest", headers=AUTH_HEADERS)
    assert empty_latest.status_code == 404

    # Post 1st payload
    payload1 = {"device_id": "tronn-sensor-01", "temperature": 23.5, "humidity": 60}
    res1 = client.post("/api/v1/data", json=payload1, headers=AUTH_HEADERS)
    assert res1.status_code == 201
    body1 = res1.json()
    assert body1["developer"] == "Tronn"
    data1 = body1["data"]
    assert data1["id"] == 1
    assert data1["device_id"] == "tronn-sensor-01"
    assert data1["temperature"] == 23.5
    assert "created_at" in data1

    # Check latest
    latest_res = client.get("/api/v1/data/latest", headers=AUTH_HEADERS)
    assert latest_res.status_code == 200
    assert latest_res.json()["developer"] == "Tronn"
    assert latest_res.json()["data"]["id"] == 1
    assert latest_res.json()["data"]["temperature"] == 23.5

    # Post 2nd payload
    payload2 = {"device_id": "tronn-sensor-02", "temperature": 28.1, "humidity": 45}
    res2 = client.post("/api/v1/data", json=payload2, headers=AUTH_HEADERS)
    assert res2.status_code == 201
    data2 = res2.json()["data"]
    assert data2["id"] == 2

    # Check latest is now 2nd payload
    latest_res2 = client.get("/api/v1/data/latest", headers=AUTH_HEADERS)
    assert latest_res2.status_code == 200
    assert latest_res2.json()["data"]["id"] == 2
    assert latest_res2.json()["data"]["device_id"] == "tronn-sensor-02"


def test_sync_all_records(client):
    for i in range(1, 4):
        client.post("/api/v1/data", json={"metric": f"val_{i}", "step": i}, headers=AUTH_HEADERS)

    res = client.get("/api/v1/data/sync", headers=AUTH_HEADERS)
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "success"
    assert body["developer"] == "Tronn"
    assert body["total"] == 3
    assert body["count"] == 3
    assert len(body["data"]) == 3
    assert body["data"][0]["step"] == 1
    assert body["data"][2]["step"] == 3


def test_sync_after_id(client):
    for i in range(1, 6):
        client.post("/api/v1/data", json={"count": i}, headers=AUTH_HEADERS)

    # Sync records after ID 3
    res = client.get("/api/v1/data/sync?after_id=3", headers=AUTH_HEADERS)
    assert res.status_code == 200
    body = res.json()
    assert body["count"] == 2
    assert body["total"] == 2
    assert [d["id"] for d in body["data"]] == [4, 5]


def test_pluck_fields(client):
    client.post("/api/v1/data", json={"a": 1, "b": 2, "c": 3, "d": 4}, headers=AUTH_HEADERS)
    client.post("/api/v1/data", json={"a": 10, "b": 20, "c": 30, "d": 40}, headers=AUTH_HEADERS)

    # Pluck only fields 'a' and 'c'
    res = client.get("/api/v1/data/sync?fields=a,c", headers=AUTH_HEADERS)
    assert res.status_code == 200
    body = res.json()
    assert body["count"] == 2
    for item in body["data"]:
        assert "a" in item
        assert "c" in item
        assert "b" not in item
        assert "d" not in item


def test_pluck_specific_ids(client):
    for i in range(1, 6):
        client.post("/api/v1/data", json={"item": f"item_{i}"}, headers=AUTH_HEADERS)

    # Pluck specific IDs: 2 and 4
    res = client.get("/api/v1/data/sync?ids=2,4", headers=AUTH_HEADERS)
    assert res.status_code == 200
    body = res.json()
    assert body["count"] == 2
    assert [d["id"] for d in body["data"]] == [2, 4]


def test_pagination_limit_offset(client):
    for i in range(1, 11):
        client.post("/api/v1/data", json={"num": i}, headers=AUTH_HEADERS)

    # Page 1: limit 3, offset 0
    res1 = client.get("/api/v1/data/sync?limit=3&offset=0", headers=AUTH_HEADERS)
    assert res1.status_code == 200
    data1 = res1.json()["data"]
    assert len(data1) == 3
    assert [d["num"] for d in data1] == [1, 2, 3]

    # Page 2: limit 3, offset 3
    res2 = client.get("/api/v1/data/sync?limit=3&offset=3", headers=AUTH_HEADERS)
    assert res2.status_code == 200
    data2 = res2.json()["data"]
    assert len(data2) == 3
    assert [d["num"] for d in data2] == [4, 5, 6]


def test_get_by_id(client):
    res = client.post("/api/v1/data", json={"name": "test_record"}, headers=AUTH_HEADERS)
    doc_id = res.json()["data"]["id"]

    get_res = client.get(f"/api/v1/data/{doc_id}", headers=AUTH_HEADERS)
    assert get_res.status_code == 200
    assert get_res.json()["data"]["name"] == "test_record"

    not_found = client.get("/api/v1/data/9999", headers=AUTH_HEADERS)
    assert not_found.status_code == 404


def test_delete_by_id(client):
    res = client.post("/api/v1/data", json={"name": "to_be_deleted"}, headers=AUTH_HEADERS)
    doc_id = res.json()["data"]["id"]

    del_res = client.delete(f"/api/v1/data/{doc_id}", headers=AUTH_HEADERS)
    assert del_res.status_code == 200
    del_body = del_res.json()
    assert del_body["status"] == "success"
    assert del_body["deleted_count"] == 1

    # Verify record is gone
    get_res = client.get(f"/api/v1/data/{doc_id}", headers=AUTH_HEADERS)
    assert get_res.status_code == 404

    # Second delete should return 404
    del_again = client.delete(f"/api/v1/data/{doc_id}", headers=AUTH_HEADERS)
    assert del_again.status_code == 404


def test_delete_all_records(client):
    for i in range(5):
        client.post("/api/v1/data", json={"item": i}, headers=AUTH_HEADERS)

    # Purge all
    del_all = client.delete("/api/v1/data", headers=AUTH_HEADERS)
    assert del_all.status_code == 200
    assert del_all.json()["deleted_count"] == 5

    # Check sync is empty
    sync_res = client.get("/api/v1/data/sync", headers=AUTH_HEADERS)
    assert sync_res.status_code == 200
    assert sync_res.json()["count"] == 0
    assert sync_res.json()["total"] == 0


def test_export_db_file(client):
    # Insert some data first
    client.post("/api/v1/data", json={"node": "alpha", "val": 100}, headers=AUTH_HEADERS)

    # Export DB file
    export_res = client.get("/api/v1/data/export", headers=AUTH_HEADERS)
    assert export_res.status_code == 200
    assert "application/json" in export_res.headers.get("content-type", "")

    # Parse exported file content
    file_content = json.loads(export_res.text)
    assert "records" in file_content or "_default" in file_content
    # The record should be present in file
    assert "alpha" in export_res.text


def test_sync_since_timestamp(client):
    payload_old = {"created_at": "2026-01-01T10:00:00Z", "tag": "old"}
    payload_new = {"created_at": "2026-08-24T12:00:00Z", "tag": "new"}
    client.post("/api/v1/data", json=payload_old, headers=AUTH_HEADERS)
    client.post("/api/v1/data", json=payload_new, headers=AUTH_HEADERS)

    res = client.get("/api/v1/data/sync?since=2026-06-01T00:00:00Z", headers=AUTH_HEADERS)
    assert res.status_code == 200
    body = res.json()
    assert body["count"] == 1
    assert body["data"][0]["tag"] == "new"


def test_invalid_input_validation(client):
    invalid_ids = client.get("/api/v1/data/sync?ids=abc,def", headers=AUTH_HEADERS)
    assert invalid_ids.status_code == 400

    invalid_offset = client.get("/api/v1/data/sync?offset=-1", headers=AUTH_HEADERS)
    assert invalid_offset.status_code == 422
