from app.services.data_processing import (
    process_confluence_data,
    process_jira_data,
    process_notion_data,
    process_slack_data,
)


def test_process_slack_data_builds_document_with_metadata():
    msgs = [
        {"text": "Gateway V2 needs an idempotency key", "user": "U123", "ts": "1700000000.000100"},
        {"user": "U999", "ts": "1700000001.000200"},  # no text -> skipped
    ]
    docs = process_slack_data(msgs, "C0ABC")

    assert len(docs) == 1
    doc = docs[0]
    assert "Gateway V2 needs an idempotency key" in doc.page_content
    assert doc.metadata["source"] == "slack"
    assert doc.metadata["channel"] == "C0ABC"
    assert doc.metadata["user"] == "U123"
    assert doc.metadata["url"] == "https://slack.com/archives/C0ABC/p1700000000000100"


def test_process_slack_data_empty_input():
    assert process_slack_data([], "C0ABC") == []


def test_process_jira_data():
    tickets = [
        {
            "key": "PAY-42",
            "summary": "Retry logic drops payments",
            "description": "Retries without idempotency key",
            "status": "Open",
            "creator": "Dana",
        }
    ]
    docs = process_jira_data(tickets)

    assert len(docs) == 1
    assert docs[0].metadata["source"] == "jira"
    assert docs[0].metadata["id"] == "PAY-42"
    assert docs[0].metadata["status"] == "Open"
    assert "PAY-42" in docs[0].page_content


def test_process_jira_data_none_description():
    tickets = [
        {"key": "PAY-1", "summary": "S", "description": None, "status": "Done", "creator": "A"}
    ]
    docs = process_jira_data(tickets)
    assert "No description" in docs[0].page_content


def test_process_confluence_data_strips_html():
    pages = [
        {
            "id": "123",
            "title": "Payment design",
            "url": "https://confluence.example.com/page/123",
            "body": "<p>Use <b>idempotency</b> keys</p>",
            "version": 3,
            "last_modified": "2026-01-01T00:00:00Z",
        }
    ]
    docs = process_confluence_data(pages)

    assert len(docs) == 1
    assert "<p>" not in docs[0].page_content
    assert "idempotency" in docs[0].page_content
    assert docs[0].metadata["source"] == "confluence"
    assert docs[0].metadata["url"].endswith("/page/123")


def test_process_confluence_data_none_body():
    pages = [{"id": "1", "title": "T", "body": None}]
    docs = process_confluence_data(pages)
    assert len(docs) == 1


def test_process_notion_data():
    pages = [
        {
            "id": "page-1",
            "title": "Runbook",
            "url": "https://notion.so/page-1",
            "content": "Step 1: rotate keys",
            "last_edited": "2026-02-01T00:00:00Z",
        }
    ]
    docs = process_notion_data(pages)

    assert len(docs) == 1
    assert docs[0].metadata["source"] == "notion"
    assert docs[0].metadata["page_id"] == "page-1"
    assert "Step 1: rotate keys" in docs[0].page_content
