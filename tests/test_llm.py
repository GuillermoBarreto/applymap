import json
from unittest import mock

from applymap import llm


class _FakeResponse:
    def __init__(self, body):
        self._body = body

    def read(self):
        return json.dumps(self._body).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _api_body(text):
    return {"choices": [{"message": {"content": text}}]}


def test_is_configured_false_without_key(monkeypatch):
    monkeypatch.delenv("APPLYMAP_API_KEY", raising=False)
    assert llm.is_configured() is False


def test_chat_requires_key(monkeypatch):
    monkeypatch.delenv("APPLYMAP_API_KEY", raising=False)
    try:
        llm.chat("system", "user")
    except RuntimeError as exc:
        assert "APPLYMAP_API_KEY" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")


def test_chat_returns_assistant_text(monkeypatch):
    monkeypatch.setenv("APPLYMAP_API_KEY", "test-key")
    monkeypatch.setenv("APPLYMAP_API_BASE", "https://example.invalid/v1")
    with mock.patch(
        "urllib.request.urlopen", return_value=_FakeResponse(_api_body("hello there"))
    ) as fake:
        result = llm.chat("be helpful", "hi")
    assert result == "hello there"
    sent_req = fake.call_args[0][0]
    assert sent_req.full_url == "https://example.invalid/v1/chat/completions"
    assert sent_req.headers["Authorization"] == "Bearer test-key"


def test_chat_rejects_malformed_response(monkeypatch):
    monkeypatch.setenv("APPLYMAP_API_KEY", "test-key")
    with mock.patch(
        "urllib.request.urlopen", return_value=_FakeResponse({"nope": True})
    ):
        try:
            llm.chat("system", "user")
        except RuntimeError as exc:
            assert "Unexpected API response" in str(exc)
        else:
            raise AssertionError("expected RuntimeError")


def test_draft_cover_letter_never_invents(monkeypatch):
    """The prompt sent to the model must forbid inventing experience."""
    monkeypatch.setenv("APPLYMAP_API_KEY", "test-key")
    captured = {}

    def fake_chat(system, user, **kwargs):
        captured["system"] = system
        captured["user"] = user
        return "letter"

    monkeypatch.setattr(llm, "chat", fake_chat)
    profile = {"name": "Sam", "headline": "student", "skills": ["python"], "experience": []}
    llm.draft_cover_letter(profile, "python job", "Acme", "Dev")
    assert "Never invent" in captured["system"]
    # The profile's real skill must reach the model so the letter is grounded.
    assert "python" in captured["user"]
