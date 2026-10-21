"""API integration tests use an isolated temporary SQLite database."""
from __future__ import annotations

import importlib.util
import os
import sys
import types
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Some minimal CI environments do not preinstall optional provider/password
# packages. Stub only import-time dependencies there; tests replace password
# helpers and the AI provider before exercising routes.
if "groq" not in sys.modules and importlib.util.find_spec("groq") is None:
    groq_stub = types.ModuleType("groq")
    class _UnusedGroqClient:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("Groq client should be mocked in API tests")
    groq_stub.Groq = _UnusedGroqClient
    sys.modules["groq"] = groq_stub

if "bcrypt" not in sys.modules and importlib.util.find_spec("bcrypt") is None:
    bcrypt_stub = types.ModuleType("bcrypt")
    bcrypt_stub.hashpw = lambda value, salt: b"test-hash"  # noqa: E731
    bcrypt_stub.gensalt = lambda: b"test-salt"  # noqa: E731
    bcrypt_stub.checkpw = lambda value, hashed: hashed == b"test-hash"  # noqa: E731
    sys.modules["bcrypt"] = bcrypt_stub

os.environ.setdefault("JWT_SECRET_KEY", "devpilot-api-tests-only-secret-long-enough-32")
os.environ.pop("ADMIN_EMAILS", None)

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import main  # noqa: E402
from database import Base  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    main._RATE_BUCKETS.clear()
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=test_engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    main.app.dependency_overrides[main.get_db] = override_get_db
    monkeypatch.setattr(main, "hash_password", lambda value: f"hash:{value}")
    monkeypatch.setattr(main, "verify_password", lambda value, hashed: hashed == f"hash:{value}")
    monkeypatch.setattr(main, "get_ai_response", lambda messages, **kwargs: "Mocked DevPilot answer")
    with TestClient(main.app) as test_client:
        yield test_client
    main.app.dependency_overrides.clear()
    test_engine.dispose()


def create_user(client: TestClient, email="developer@example.com", username="developer"):
    response = client.post("/api/auth/signup", json={
        "username": username,
        "email": email,
        "password": "correct-horse-battery",
    })
    assert response.status_code == 201, response.text
    login = client.post("/api/auth/login", json={
        "email": email,
        "password": "correct-horse-battery",
    })
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_auth_settings_and_preferences_round_trip(client):
    headers = create_user(client)
    assert client.get("/api/auth/me", headers=headers).status_code == 200
    initial = client.get("/api/settings", headers=headers)
    assert initial.status_code == 200
    assert initial.json()["response_verbosity"] == "balanced"

    saved = client.put("/api/settings/preferences", headers=headers, json={
        "response_verbosity": "detailed",
        "preferred_stack": "React + FastAPI",
        "behavior_preferences": "Explain changes before code.",
    })
    assert saved.status_code == 200, saved.text
    loaded = client.get("/api/settings", headers=headers).json()
    assert loaded["response_verbosity"] == "detailed"
    assert loaded["preferred_stack"] == "React + FastAPI"
    assert loaded["behavior_preferences"] == "Explain changes before code."


def test_preferences_reject_invalid_verbosity_and_oversized_text(client):
    headers = create_user(client)
    invalid = client.put("/api/settings/preferences", headers=headers, json={
        "response_verbosity": "unlimited",
        "preferred_stack": "",
        "behavior_preferences": "",
    })
    assert invalid.status_code == 422
    oversized = client.put("/api/settings/preferences", headers=headers, json={
        "response_verbosity": "balanced",
        "preferred_stack": "x" * 121,
        "behavior_preferences": "",
    })
    assert oversized.status_code == 422


def test_chat_uses_saved_preferences_and_persists_messages(client, monkeypatch):
    headers = create_user(client)
    client.put("/api/settings/preferences", headers=headers, json={
        "response_verbosity": "concise",
        "preferred_stack": "Laravel",
        "behavior_preferences": "Avoid adding dependencies.",
    })
    observed = {}
    def fake_response(messages, **kwargs):
        observed.update(kwargs.get("user_preferences") or {})
        return "Mocked DevPilot answer"
    monkeypatch.setattr(main, "get_ai_response", fake_response)
    response = client.post("/api/chat", headers=headers, json={"message": "Explain this API"})
    assert response.status_code == 200, response.text
    assert response.json()["message"]["content"] == "Mocked DevPilot answer"
    assert observed["response_verbosity"] == "concise"
    assert observed["preferred_stack"] == "Laravel"
    conversation_id = response.json()["conversation"]["id"]
    history = client.get(f"/api/conversations/{conversation_id}", headers=headers)
    assert history.status_code == 200
    assert [item["role"] for item in history.json()["messages"]] == ["user", "assistant"]


def test_users_cannot_upload_into_another_users_conversation(client):
    first_headers = create_user(client, "one@example.com", "userone")
    created = client.post("/api/chat", headers=first_headers, json={"message": "My private chat"})
    assert created.status_code == 200
    conversation_id = created.json()["conversation"]["id"]
    second_headers = create_user(client, "two@example.com", "usertwo")
    upload = client.post(
        "/api/files",
        headers=second_headers,
        data={"conversation_id": str(conversation_id)},
        files={"file": ("example.py", b"print('safe')", "text/plain")},
    )
    assert upload.status_code == 404


def test_feedback_admin_route_fails_closed_when_admins_not_configured(client):
    headers = create_user(client)
    response = client.get("/api/admin/feedback", headers=headers)
    assert response.status_code == 403


def test_unauthenticated_settings_and_chat_are_rejected(client):
    assert client.get("/api/settings").status_code == 401
    assert client.post("/api/chat", json={"message": "hello"}).status_code == 401


def test_request_size_guard_returns_413(client, monkeypatch):
    monkeypatch.setattr(main, "_MAX_REQUEST_BYTES", 100)
    response = client.post("/api/chat", content=b"x" * 101, headers={"Content-Type": "application/json"})
    assert response.status_code == 413


def test_sensitive_route_rate_limit_returns_429(client, monkeypatch):
    monkeypatch.setattr(main, "_RATE_LIMITS", {"/api/chat": (2, 60)})
    key = ("testclient", "/api/chat")
    main._RATE_BUCKETS.pop(key, None)
    first = client.post("/api/chat", json={"message": "hello"})
    second = client.post("/api/chat", json={"message": "hello"})
    third = client.post("/api/chat", json={"message": "hello"})
    assert first.status_code == 401
    assert second.status_code == 401
    assert third.status_code == 429
    assert "Retry-After" in third.headers
    main._RATE_BUCKETS.pop(key, None)


def test_memory_create_list_delete_and_user_isolation(client):
    first_headers = create_user(client, "memory-one@example.com", "memoryone")
    created = client.post("/api/memories", headers=first_headers, json={"memory": "Prefer concise technical answers"})
    assert created.status_code == 201, created.text
    memory_id = created.json()["memory"]["id"]
    assert len(client.get("/api/memories", headers=first_headers).json()["memories"]) == 1

    second_headers = create_user(client, "memory-two@example.com", "memorytwo")
    assert client.get("/api/memories", headers=second_headers).json()["memories"] == []
    assert client.delete(f"/api/memories/{memory_id}", headers=second_headers).status_code == 404
    assert client.delete(f"/api/memories/{memory_id}", headers=first_headers).status_code == 200
    assert client.get("/api/memories", headers=first_headers).json()["memories"] == []


def test_feedback_can_be_viewed_only_by_configured_admin(client, monkeypatch):
    headers = create_user(client)
    submitted = client.post("/api/feedback", headers=headers, json={
        "type": "feedback",
        "message": "Please add a project context panel.",
    })
    assert submitted.status_code == 201, submitted.text
    monkeypatch.setenv("ADMIN_EMAILS", "developer@example.com")
    response = client.get("/api/admin/feedback", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["items"][0]["message"] == "Please add a project context panel."


def test_chat_rejects_empty_and_overlong_inputs_without_creating_conversations(client):
    headers = create_user(client)
    empty = client.post("/api/chat", headers=headers, json={"message": " "})
    assert empty.status_code == 400
    oversized = client.post("/api/chat", headers=headers, json={"message": "x" * 20001})
    assert oversized.status_code == 422
    assert client.get("/api/conversations", headers=headers).json()["conversations"] == []


def test_file_upload_rejects_unsupported_and_invalid_utf8_without_creating_chat(client):
    headers = create_user(client)
    unsupported = client.post("/api/files", headers=headers, files={"file": ("payload.exe", b"x", "application/octet-stream")})
    assert unsupported.status_code == 400
    invalid_utf8 = client.post("/api/files", headers=headers, files={"file": ("main.py", b"\xff\xfe", "text/plain")})
    assert invalid_utf8.status_code == 400
    assert client.get("/api/conversations", headers=headers).json()["conversations"] == []


def test_file_upload_enforces_two_megabyte_limit(client):
    headers = create_user(client)
    payload = b"x" * (2 * 1024 * 1024 + 1)
    response = client.post(
        "/api/files",
        headers=headers,
        files={"file": ("large.py", payload, "text/plain")},
    )
    assert response.status_code == 413
    assert client.get("/api/conversations", headers=headers).json()["conversations"] == []
