import json

import pytest

import pipeline.claude_tasks as claude_tasks
from pipeline.script_schema import ScriptValidationError


class FakeContentBlock:
    def __init__(self, text):
        self.text = text


class FakeMessage:
    def __init__(self, text):
        self.content = [FakeContentBlock(text)]


class FakeMessages:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        text = self._responses.pop(0)
        return FakeMessage(text)


class FakeClient:
    def __init__(self, responses):
        self.messages = FakeMessages(responses)


def _install_fake_client(monkeypatch, responses):
    fake_client = FakeClient(responses)
    monkeypatch.setattr(
        claude_tasks.anthropic, "Anthropic", lambda **kwargs: fake_client
    )
    monkeypatch.setattr(
        type(claude_tasks.settings), "anthropic_key", property(lambda self: "test-key")
    )
    # A real key routes to the SDK path; without this the CLI fallback would win.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    return fake_client


VALID_SCRIPT = json.dumps([
    {
        "narration_bm": "Naro tertanya-tanya apakah itu AI hari ini.",
        "visual": "Naro looking curious at Exa",
    },
    {
        "narration_bm": "Exa menjawab dengan tenang dan mudah faham.",
        "visual": "Exa gesturing",
        "on_screen_text": "AI = Kecerdasan Buatan",
    },
])


def test_draft_script_returns_validated_blocks_on_valid_json(monkeypatch):
    fake_client = _install_fake_client(monkeypatch, [VALID_SCRIPT])
    blocks = claude_tasks.draft_script(
        "Apa itu AI?", "Pengenalan ringkas kepada AI untuk pemula."
    )
    assert len(blocks) == 2
    assert blocks[0]["sfx"] == ""
    assert blocks[1]["on_screen_text"] == "AI = Kecerdasan Buatan"
    assert len(fake_client.messages.calls) == 1


def test_draft_script_raises_after_retry_on_garbage_twice(monkeypatch):
    _install_fake_client(monkeypatch, ["not json", "still not json"])
    with pytest.raises(ScriptValidationError):
        claude_tasks.draft_script(
            "Apa itu AI?", "Pengenalan ringkas kepada AI untuk pemula."
        )


class FakeCompleted:
    def __init__(self, stdout, returncode=0, stderr=""):
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr


def test_draft_script_uses_cli_when_no_api_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "REPLACE_ME")
    monkeypatch.setattr(claude_tasks.shutil, "which", lambda name: "/fake/claude")
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return FakeCompleted(VALID_SCRIPT)

    monkeypatch.setattr(claude_tasks.subprocess, "run", fake_run)
    blocks = claude_tasks.draft_script(
        "Apa itu AI?", "Pengenalan ringkas kepada AI untuk pemula."
    )
    assert len(blocks) == 2
    assert calls[0][0] == "/fake/claude"
    assert calls[0][1] == "-p"


def test_cli_failure_raises(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(claude_tasks.shutil, "which", lambda name: "/fake/claude")
    monkeypatch.setattr(
        claude_tasks.subprocess,
        "run",
        lambda cmd, **kwargs: FakeCompleted("", returncode=1, stderr="not logged in"),
    )
    with pytest.raises(RuntimeError):
        claude_tasks._call("hello")
