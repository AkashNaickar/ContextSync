import pytest
from pydantic import ValidationError

from app.models import ChatRequest, ContextObject, ExplainRequest, StatsObject


def test_explain_request_requires_all_fields():
    with pytest.raises(ValidationError):
        ExplainRequest(code_snippet="x")
    req = ExplainRequest(code_snippet="x", file_path="a.py", line_numbers="1-2")
    assert req.file_path == "a.py"


def test_context_object_defaults():
    obj = ContextObject(
        source="jira",
        title_or_user="PAY-1",
        content_summary="s",
    )
    assert obj.url is None
    assert obj.relevance_score == 0.0
    assert obj.related_code_files == []


def test_stats_object_fields():
    s = StatsObject(slack_count=1, jira_count=2, open_jira_count=1)
    assert s.jira_count == 2


def test_chat_request_defaults():
    req = ChatRequest(message="hi")
    assert req.history == []
    assert req.context is None
