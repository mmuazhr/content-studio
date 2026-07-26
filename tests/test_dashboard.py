from urllib.parse import urlencode

import httpx
import pytest
from fastapi.testclient import TestClient

import dashboard.app as app_module
from dashboard.airflow_client import AirflowTriggerError, trigger_dag_run
from dashboard.app import app, get_sb


def test_trigger_dag_run_posts_conf_and_returns_run_id():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = request.read().decode()
        seen["auth"] = request.headers.get("authorization", "")
        return httpx.Response(200, json={"dag_run_id": "manual__2026-07-26T00:00:00+00:00"})

    run_id = trigger_dag_run(
        "video_production",
        {"episode_id": "ep-1"},
        transport=httpx.MockTransport(handler),
    )

    assert run_id == "manual__2026-07-26T00:00:00+00:00"
    assert seen["url"].endswith("/api/v1/dags/video_production/dagRuns")
    assert seen["body"] == '{"conf": {"episode_id": "ep-1"}}'
    assert seen["auth"].startswith("Basic ")


def test_trigger_dag_run_raises_on_forbidden():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="forbidden")

    with pytest.raises(AirflowTriggerError) as excinfo:
        trigger_dag_run("video_production", {}, transport=httpx.MockTransport(handler))

    assert "403" in str(excinfo.value)


# --- fake supabase -----------------------------------------------------------


class FakeResult:
    def __init__(self, data):
        self.data = data


class FakeTable:
    def __init__(self, store, name):
        self.store = store
        self.name = name
        self._mode = "select"
        self._filters = {}
        self._payload = None
        self._single = False
        self._order = None
        self._desc = False
        self._limit = None

    def select(self, *args):
        self._mode = "select"
        return self

    def insert(self, payload):
        self._mode = "insert"
        self._payload = payload
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

    def order(self, col, desc=False):
        self._order = col
        self._desc = desc
        return self

    def limit(self, n):
        self._limit = n
        return self

    def execute(self):
        rows = self.store.setdefault(self.name, [])
        if self._mode == "insert":
            row = dict(self._payload)
            row.setdefault("id", f"{self.name}-{len(rows) + 1}")
            rows.append(row)
            return FakeResult([row])
        matched = [r for r in rows if all(r.get(k) == v for k, v in self._filters.items())]
        if self._mode == "update":
            for r in matched:
                r.update(self._payload)
            return FakeResult(matched)
        if self._order:
            matched = sorted(
                matched, key=lambda r: (r.get(self._order) is None, r.get(self._order)),
                reverse=self._desc,
            )
        if self._limit is not None:
            matched = matched[: self._limit]
        if self._single:
            return FakeResult(matched[0] if matched else None)
        return FakeResult(matched)


class FakeSB:
    def __init__(self, episodes=(), runs=()):
        self.store = {
            "cs_episodes": [dict(e) for e in episodes],
            "cs_approvals": [],
            "cs_runs": [dict(r) for r in runs],
        }

    def table(self, name):
        return FakeTable(self.store, name)


SCRIPT = [
    {
        "narration_bm": "Korang selalu dengar orang cakap pasal AI?",
        "visual": "Naro thinking on the voxel platform.",
        "on_screen_text": "AI tu apa?",
        "sfx": "lo-fi bed",
    },
    {
        "narration_bm": "Kenalkan Naro dan Exa, setiap minggu kita belajar AI.",
        "visual": "Duo shot, Naro waves and Exa presents the laptop.",
        "on_screen_text": "",
        "sfx": "",
    },
]


def episode(**overrides):
    ep = {
        "id": "ep-1",
        "ep_number": None,
        "title": "Kenalkan Naro & Exa",
        "topic_summary": "Channel intro",
        "episode_type": "intro",
        "script": [dict(b) for b in SCRIPT],
        "status": "pending_script_review",
        "rejection_note": None,
        "video_url": None,
        "caption": None,
        "local_path": None,
        "higgsfield_jobs": {},
        "error_log": None,
        "created_at": "2026-07-26T00:00:00+00:00",
        "updated_at": "2026-07-26T00:00:00+00:00",
    }
    ep.update(overrides)
    return ep


@pytest.fixture
def sb():
    fake = FakeSB([episode()])
    app.dependency_overrides[get_sb] = lambda: fake
    yield fake
    app.dependency_overrides.clear()


@pytest.fixture
def triggers(monkeypatch):
    calls = []
    monkeypatch.setattr(
        app_module, "trigger_dag_run", lambda dag_id, conf: calls.append((dag_id, conf)) or "run-1"
    )
    return calls


@pytest.fixture
def client():
    return TestClient(app)


def script_form(blocks, **extra):
    """Encode the repeated per-block fields the editor posts (httpx `data=` takes dicts only)."""
    pairs = [("narration_bm", b["narration_bm"]) for b in blocks]
    pairs += [("visual", b["visual"]) for b in blocks]
    pairs += [("on_screen_text", b["on_screen_text"]) for b in blocks]
    pairs += [("sfx", b["sfx"]) for b in blocks]
    pairs += list(extra.items())
    return urlencode(pairs)


FORM_HEADERS = {"content-type": "application/x-www-form-urlencoded"}


# --- routes ------------------------------------------------------------------


def test_queue_lists_pending_episode(client, sb):
    response = client.get("/")

    assert response.status_code == 200
    assert "Kenalkan Naro &amp; Exa" in response.text
    assert "cs-chip--pending_script_review" in response.text


def test_queue_hides_non_review_statuses(client, sb):
    sb.store["cs_episodes"][0]["status"] = "posted"

    response = client.get("/")

    assert response.status_code == 200
    assert "Kenalkan Naro" not in response.text


def test_episode_detail_renders_timeline_and_blocks(client, sb):
    response = client.get("/episode/ep-1")

    assert response.status_code == 200
    assert "cs-timeline" in response.text
    assert "is-current" in response.text
    assert "Korang selalu dengar" in response.text


def test_script_approve_triggers_production_and_records_approval(client, sb, triggers):
    response = client.post(
        "/episode/ep-1/decision",
        content=script_form(SCRIPT, gate="script", decision="approve", note=""), headers=FORM_HEADERS,
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert triggers == [("video_production", {"episode_id": "ep-1"})]
    ep = sb.store["cs_episodes"][0]
    assert ep["status"] == "script_approved"
    assert ep["ep_number"] == 0
    approval = sb.store["cs_approvals"][0]
    assert (approval["gate"], approval["decision"]) == ("script", "approved")


def test_script_approve_with_edits_records_edited_then_approved(client, sb, triggers):
    edited = [dict(b) for b in SCRIPT]
    edited[0]["narration_bm"] = "Narasi yang sudah diedit oleh manusia."

    client.post(
        "/episode/ep-1/decision",
        content=script_form(edited, gate="script", decision="approve"), headers=FORM_HEADERS,
        follow_redirects=False,
    )

    assert sb.store["cs_approvals"][0]["decision"] == "edited_then_approved"
    assert sb.store["cs_episodes"][0]["script"][0]["narration_bm"] == "Narasi yang sudah diedit oleh manusia."
    assert triggers == [("video_production", {"episode_id": "ep-1"})]


def test_script_approve_surfaces_trigger_failure_and_keeps_status(client, sb, monkeypatch):
    def boom(dag_id, conf):
        raise AirflowTriggerError("Airflow returned 403")

    monkeypatch.setattr(app_module, "trigger_dag_run", boom)

    response = client.post(
        "/episode/ep-1/decision",
        content=script_form(SCRIPT, gate="script", decision="approve"), headers=FORM_HEADERS,
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "/episode/ep-1?error=" in response.headers["location"]
    assert sb.store["cs_episodes"][0]["status"] == "script_approved"


def test_retry_trigger_route_retriggers_the_dag(client, sb, triggers):
    sb.store["cs_episodes"][0]["status"] = "script_approved"

    response = client.post("/episode/ep-1/trigger", follow_redirects=False)

    assert response.status_code == 303
    assert triggers == [("video_production", {"episode_id": "ep-1"})]


def test_retry_trigger_refuses_when_episode_is_not_approved(client, sb, triggers):
    response = client.post("/episode/ep-1/trigger", follow_redirects=False)

    assert response.status_code == 303
    assert "/episode/ep-1?error=" in response.headers["location"]
    assert triggers == []


def test_script_approved_page_offers_retry_button(client, sb):
    sb.store["cs_episodes"][0]["status"] = "script_approved"

    response = client.get("/episode/ep-1")

    assert "/episode/ep-1/trigger" in response.text
    assert "retry" in response.text.lower()


def test_video_approve_sets_video_approved(client, sb, triggers):
    sb.store["cs_episodes"][0]["status"] = "pending_video_review"

    client.post(
        "/episode/ep-1/decision",
        data={"gate": "video", "decision": "approve", "note": ""},
        follow_redirects=False,
    )

    assert sb.store["cs_episodes"][0]["status"] == "video_approved"
    assert triggers == []


def test_reject_records_note(client, sb):
    client.post(
        "/episode/ep-1/decision",
        content=script_form(SCRIPT, gate="script", decision="reject", note="topik dah pernah buat"), headers=FORM_HEADERS,
        follow_redirects=False,
    )

    ep = sb.store["cs_episodes"][0]
    assert ep["status"] == "rejected"
    assert ep["rejection_note"] == "topik dah pernah buat"


def test_backlog_moves_episode_to_backlog(client, sb):
    client.post(
        "/episode/ep-1/decision",
        content=script_form(SCRIPT, gate="script", decision="backlog"), headers=FORM_HEADERS,
        follow_redirects=False,
    )

    assert sb.store["cs_episodes"][0]["status"] == "backlog"


@pytest.mark.parametrize(
    "data",
    [
        {"gate": "promo", "decision": "approve"},
        {"gate": "script", "decision": "yolo"},
    ],
)
def test_unknown_gate_or_decision_is_400(client, sb, data):
    response = client.post("/episode/ep-1/decision", data=data)

    assert response.status_code == 400


def test_illegal_state_transition_surfaces_error_without_writing(client, sb, triggers):
    sb.store["cs_episodes"][0]["status"] = "video_approved"

    response = client.post(
        "/episode/ep-1/decision",
        data={"gate": "video", "decision": "approve"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "/episode/ep-1?error=" in response.headers["location"]
    assert sb.store["cs_episodes"][0]["status"] == "video_approved"
    assert triggers == []


def test_save_script_keeps_status_and_persists_edits(client, sb):
    edited = [dict(b) for b in SCRIPT]
    edited[1]["narration_bm"] = "Versi baharu untuk blok kedua ini."

    response = client.post(
        "/episode/ep-1/script", content=script_form(edited), headers=FORM_HEADERS, follow_redirects=False
    )

    assert response.status_code == 303
    ep = sb.store["cs_episodes"][0]
    assert ep["status"] == "pending_script_review"
    assert ep["script"][1]["narration_bm"] == "Versi baharu untuk blok kedua ini."


def test_save_script_rejects_invalid_blocks(client, sb):
    broken = [dict(b) for b in SCRIPT]
    broken[0]["narration_bm"] = "short"

    response = client.post(
        "/episode/ep-1/script", content=script_form(broken), headers=FORM_HEADERS, follow_redirects=False
    )

    assert "error=" in response.headers["location"]
    assert sb.store["cs_episodes"][0]["script"][0]["narration_bm"] == SCRIPT[0]["narration_bm"]


def test_history_lists_episodes_and_runs(client, sb):
    sb.store["cs_runs"].append(
        {
            "id": "run-1",
            "dag_id": "video_production",
            "airflow_run_id": "manual__2026",
            "outcome": "success",
            "credits_note": "dry-run: no credits spent",
            "started_at": "2026-07-26T00:00:00+00:00",
        }
    )

    response = client.get("/history")

    assert response.status_code == 200
    assert "video_production" in response.text
    assert "dry-run: no credits spent" in response.text
