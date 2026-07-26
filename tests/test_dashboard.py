import httpx
import pytest

from dashboard.airflow_client import AirflowTriggerError, trigger_dag_run


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
