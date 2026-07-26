"""Trigger Airflow DAG runs from the dashboard.

Airflow 2.9 standalone exposes the stable REST API at /api/v1 with basic auth
(`auth_backends` includes `basic_auth`); credentials come from AIRFLOW_USER /
AIRFLOW_PASSWORD in .env.
"""
import os

import httpx

from pipeline.config import settings

TIMEOUT_SECONDS = 10


class AirflowTriggerError(RuntimeError):
    pass


def trigger_dag_run(dag_id: str, conf: dict, *, transport=None) -> str:
    """POST a new dag run and return its dag_run_id.

    `transport` is a test seam for httpx.MockTransport; production calls omit it.
    """
    url = f"{settings.airflow_api_url.rstrip('/')}/api/v1/dags/{dag_id}/dagRuns"
    auth = (os.getenv("AIRFLOW_USER", ""), os.getenv("AIRFLOW_PASSWORD", ""))
    try:
        with httpx.Client(timeout=TIMEOUT_SECONDS, transport=transport) as client:
            response = client.post(url, json={"conf": conf}, auth=auth)
    except httpx.HTTPError as exc:
        raise AirflowTriggerError(f"could not reach Airflow at {url}: {exc}") from exc
    if response.status_code >= 300:
        raise AirflowTriggerError(
            f"Airflow returned {response.status_code} for {dag_id}: {response.text[:500]}"
        )
    return response.json()["dag_run_id"]
