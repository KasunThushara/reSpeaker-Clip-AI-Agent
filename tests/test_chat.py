import pytest
from app import create_app


@pytest.fixture
def client():
    app = create_app()
    return app.test_client()


def test_health_endpoint(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.get_json() == {"status": "ok"}


def test_chat_requires_text(client):
    r = client.post("/api/chat", json={})
    assert r.status_code == 400
    assert "error" in r.get_json()


def test_chat_returns_response(client):
    r = client.post("/api/chat", json={"text": "Say hello in one word."})
    assert r.status_code == 200
    data = r.get_json()
    assert "response" in data
    assert "conversation_id" in data
    assert len(data["response"]) > 0


def test_chat_creates_conversation(client):
    r = client.post("/api/chat", json={"text": "Hi"})
    data = r.get_json()
    assert len(data["conversation_id"]) > 0


def test_chat_reuses_conversation(client):
    cid = "test-convo-123"
    client.post("/api/chat", json={"text": "First message", "conversation_id": cid})
    r = client.post("/api/chat", json={"text": "Second message", "conversation_id": cid})
    assert r.status_code == 200
    assert r.get_json()["conversation_id"] == cid
