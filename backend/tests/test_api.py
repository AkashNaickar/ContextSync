
import pytest
from fastapi.testclient import TestClient

from app import main


class FakeRAGService:
    async def explain_code(self, code_snippet, file_path, line_numbers):
        return f"explained:{file_path}"

    async def get_context_objects(self, code_snippet):
        return [
            {
                "source": "slack",
                "title_or_user": "dana",
                "url": "https://slack.com/archives/C1/p1",
                "content_summary": "needs idempotency key",
                "relevance_score": 0.9,
                "related_code_files": [],
            }
        ]

    async def get_context_stats_batch(self, snippets):
        return [{"slack_count": 1, "jira_count": 2, "open_jira_count": 1} for _ in snippets]

    async def chat_with_gemini(self, message, history=None, context=None):
        return f"reply:{message}"

    def add_documents(self, documents):
        pass


class FakeIntegrationService:
    def fetch_channel_history(self, channel_id, limit=50):
        return []

    def search_jira_tickets(self, jql, limit=50):
        return []

    def search_confluence_pages(self, cql, limit=10):
        return []

    def search_notion_pages(self, query="", limit=10):
        return []


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(main, "RAGService", FakeRAGService)
    monkeypatch.setattr(main, "IntegrationService", FakeIntegrationService)
    with TestClient(main.app) as c:
        yield c


def test_root_returns_ok(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "ContextSync" in resp.json()["message"]


def test_explain_endpoint(client):
    resp = client.post(
        "/explain",
        json={"code_snippet": "def f(): pass", "file_path": "a.py", "line_numbers": "1"},
    )
    assert resp.status_code == 200
    assert resp.json()["markdown"] == "explained:a.py"


def test_context_retrieve_endpoint(client):
    resp = client.post(
        "/context/retrieve",
        json={"code_snippet": "def f(): pass", "file_path": "a.py", "line_numbers": "1"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["source"] == "slack"
    assert body[0]["relevance_score"] == 0.9


def test_context_stats_endpoint(client):
    resp = client.post("/context/stats", json={"snippets": ["x", "y"]})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    assert body[0]["slack_count"] == 1
    assert body[0]["open_jira_count"] == 1


def test_chat_endpoint(client):
    resp = client.post("/chat", json={"message": "hello"})
    assert resp.status_code == 200
    assert resp.json()["reply"] == "reply:hello"


def test_ingest_webhook_accepts_payload(client):
    resp = client.post("/context/ingest", json={"type": "message", "text": "hi"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "received"


def test_manual_sync_with_no_new_data(client):
    resp = client.post("/context/sync")
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"
    assert resp.json()["items_synced"] == 0


def test_validation_error_returns_422(client):
    resp = client.post("/explain", json={"code_snippet": "x"})
    assert resp.status_code == 422

