from datetime import datetime, timezone


class IllegalTransition(Exception):
    pass


LEGAL: dict = {
    "proposed": {"pending_script_review"},
    "pending_script_review": {"script_approved", "rejected", "backlog"},
    "script_approved": {"generating"},
    "generating": {"pending_video_review"},
    "pending_video_review": {"video_approved", "rejected"},
    "video_approved": {"posted"},
    "posted": {"archived"},
    "rejected": set(),
    "backlog": set(),
    "archived": set(),
    "error": {"pending_script_review", "script_approved"},
}


def check_transition(cur: str, new: str) -> None:
    if new == "error":
        return
    if new not in LEGAL.get(cur, set()):
        raise IllegalTransition(f"cannot transition {cur} -> {new}")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_episode(sb, episode_id):
    res = sb.table("cs_episodes").select("*").eq("id", episode_id).single().execute()
    return res.data


def list_episodes(sb, status=None):
    query = sb.table("cs_episodes").select("*")
    if status is not None:
        query = query.eq("status", status)
    res = query.execute()
    return res.data


def next_ep_number(sb) -> int:
    # NOTE: computed in Python because Postgres sorts NULLs FIRST on desc
    # order — the old order+limit(1) query returned NULL rows and produced
    # duplicate episode numbers (ep0 was overwritten once).
    res = sb.table("cs_episodes").select("ep_number").execute()
    numbers = [r["ep_number"] for r in (res.data or []) if r.get("ep_number") is not None]
    return (max(numbers) + 1) if numbers else 0


def insert_episode(sb, *, title, topic_summary, script, episode_type="explainer", status="pending_script_review") -> str:
    row = {
        "title": title,
        "topic_summary": topic_summary,
        "script": script,
        "episode_type": episode_type,
        "status": status,
    }
    res = sb.table("cs_episodes").insert(row).execute()
    return res.data[0]["id"]


def set_status(sb, episode_id, new_status, **fields):
    cur = get_episode(sb, episode_id)
    check_transition(cur["status"], new_status)
    update = {**fields, "status": new_status, "updated_at": _now()}
    sb.table("cs_episodes").update(update).eq("id", episode_id).execute()


def record_approval(sb, episode_id, gate, decision, note=""):
    row = {"episode_id": episode_id, "gate": gate, "decision": decision, "note": note}
    sb.table("cs_approvals").insert(row).execute()


def record_run(sb, dag_id, airflow_run_id, episode_id=None) -> str:
    row = {"dag_id": dag_id, "airflow_run_id": airflow_run_id, "episode_id": episode_id}
    res = sb.table("cs_runs").insert(row).execute()
    return res.data[0]["id"]


def finish_run(sb, run_id, outcome, credits_note=""):
    update = {"outcome": outcome, "credits_note": credits_note, "finished_at": _now()}
    sb.table("cs_runs").update(update).eq("id", run_id).execute()
