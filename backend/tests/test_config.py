import importlib

from app import main


def test_slack_channel_id_comes_from_env(monkeypatch):
    monkeypatch.setenv("SLACK_CHANNEL_ID", "C0TEST")
    importlib.reload(main)
    assert main.SLACK_CHANNEL_ID == "C0TEST"

    monkeypatch.delenv("SLACK_CHANNEL_ID")
    importlib.reload(main)
    assert main.SLACK_CHANNEL_ID == ""
