import pytest

import pipeline.higgsfield_runner as hf


class FakeResult:
    def __init__(self, data):
        self.data = data


class FakeTable:
    def __init__(self, store, name):
        self.store = store
        self.name = name
        self._mode = None
        self._filters = {}
        self._payload = None
        self._single = False

    def select(self, *args):
        self._mode = "select"
        return self

    def update(self, payload):
        self._mode = "update"
        self._payload = payload
        return self

    def eq(self, col, val):
        self._filters[col] = val
        return self

    def single(self):
        self._single = True
        return self

    def execute(self):
        rows = self.store[self.name]
        matched = [r for r in rows if all(r.get(k) == v for k, v in self._filters.items())]
        if self._mode == "update":
            for r in matched:
                r.update(self._payload)
            return FakeResult(matched)
        if self._single:
            return FakeResult(matched[0] if matched else None)
        return FakeResult(matched)


class FakeSB:
    def __init__(self, episodes):
        self.store = {"cs_episodes": episodes}

    def table(self, name):
        return FakeTable(self.store, name)


def test_ensure_job_calls_submit_fn_once_then_reuses_stored_id():
    sb = FakeSB([{"id": "ep1", "higgsfield_jobs": {}}])
    calls = []

    def submit_fn():
        calls.append(1)
        return "job-123"

    first = hf.ensure_job(sb, "ep1", "narration", submit_fn)
    second = hf.ensure_job(sb, "ep1", "narration", submit_fn)

    assert first == "job-123"
    assert second == "job-123"
    assert len(calls) == 1
    assert sb.store["cs_episodes"][0]["higgsfield_jobs"]["narration"] == "job-123"


def test_get_job_result_dry_run_returns_stub_asset(monkeypatch):
    monkeypatch.setattr(type(hf.settings), "dry_run", property(lambda self: True))
    calls = []
    real_run_cli = hf.run_cli

    def spy(args):
        calls.append(args)
        return real_run_cli(args)

    monkeypatch.setattr(hf, "run_cli", spy)

    result = hf.get_job_result("job-abc")

    assert calls == [["generate", "get", "job-abc"]]
    assert result["results"]["rawUrl"] == "dry://asset"


def test_run_cli_dry_run_never_spawns_process(monkeypatch):
    monkeypatch.setattr(type(hf.settings), "dry_run", property(lambda self: True))

    def boom(*args, **kwargs):
        raise AssertionError("subprocess.run should not be called under DRY_RUN")

    monkeypatch.setattr(hf.subprocess, "run", boom)

    result = hf.run_cli(["generate-video", "--foo", "bar"])

    assert result["id"].startswith("dry-")
    assert result["results"]["rawUrl"] == "dry://asset"
