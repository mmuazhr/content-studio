from airflow.decorators import dag, task
from airflow.exceptions import AirflowSkipException
from airflow.operators.python import get_current_context
from contextlib import contextmanager
import pendulum, sys
sys.path.insert(0, "/Users/muazhusaini/Documents/Project/content-studio")

DAG_ID = "video_production"


@contextmanager
def _episode_guard(sb, episode_id):
    """Any failure inside the generation body parks the episode in `error`."""
    from pipeline.db import set_status
    try:
        yield
    except AirflowSkipException:
        raise
    except Exception as exc:
        set_status(sb, episode_id, "error", error_log=str(exc)[:2000])
        raise


def _assembly_asset_url(assembly_job_id: str) -> str:
    from pipeline.higgsfield_runner import get_job_result
    return get_job_result(assembly_job_id)["results"]["rawUrl"]


def _download(url: str, ep: dict) -> str:
    import httpx
    from pipeline.config import settings
    ep_key = ep.get("ep_number")
    ep_key = f"ep{ep_key}" if ep_key is not None else ep["id"]
    target = settings.assets_root / "episodes" / ep_key / "final.mp4"
    target.parent.mkdir(parents=True, exist_ok=True)
    with httpx.stream("GET", url, timeout=300, follow_redirects=True) as response:
        response.raise_for_status()
        with open(target, "wb") as fh:
            for chunk in response.iter_bytes():
                fh.write(chunk)
    return str(target)


@dag(schedule=None, start_date=pendulum.datetime(2026, 7, 1), catchup=False, tags=["content-studio"])
def video_production():
    @task
    def verify_approved() -> dict:
        from pipeline.config import settings
        from pipeline.db import get_episode, record_run, set_status
        ctx = get_current_context()
        conf = ctx["dag_run"].conf or {}
        episode_id = conf.get("episode_id")
        if not episode_id:
            raise ValueError("dag_run.conf must supply episode_id")
        sb = settings.supabase()
        ep = get_episode(sb, episode_id)
        if ep["status"] != "script_approved":
            # Not an episode error — a redundant trigger. Spend nothing, touch nothing.
            raise AirflowSkipException(
                f"episode {episode_id} is {ep['status']}, not script_approved"
            )
        run_id = record_run(sb, DAG_ID, ctx["run_id"], episode_id=episode_id)
        with _episode_guard(sb, episode_id):
            set_status(sb, episode_id, "generating")
        return {"episode_id": episode_id, "run_id": run_id}

    @task
    def narration(ref: dict) -> dict:
        from pipeline.config import settings
        from pipeline.db import get_episode
        from pipeline.higgsfield_runner import generate_narration
        sb = settings.supabase()
        with _episode_guard(sb, ref["episode_id"]):
            generate_narration(sb, get_episode(sb, ref["episode_id"]))
        return ref

    @task
    def blocks(ref: dict) -> dict:
        from pipeline.config import settings
        from pipeline.db import get_episode
        from pipeline.higgsfield_runner import generate_block
        sb = settings.supabase()
        with _episode_guard(sb, ref["episode_id"]):
            ep = get_episode(sb, ref["episode_id"])
            for idx in range(len(ep["script"])):
                generate_block(sb, ep, idx)
        return ref

    @task
    def assemble_video(ref: dict) -> dict:
        from pipeline.config import settings
        from pipeline.db import get_episode
        from pipeline.higgsfield_runner import assemble
        sb = settings.supabase()
        with _episode_guard(sb, ref["episode_id"]):
            assemble(sb, get_episode(sb, ref["episode_id"]))
        return ref

    @task
    def deliver(ref: dict) -> str:
        from pipeline.config import settings
        from pipeline.claude_tasks import write_caption
        from pipeline.db import finish_run, get_episode, set_status
        sb = settings.supabase()
        episode_id = ref["episode_id"]
        with _episode_guard(sb, episode_id):
            ep = get_episode(sb, episode_id)
            assembly_job = (ep.get("higgsfield_jobs") or {})["assembly"]
            if settings.dry_run:
                video_url = f"dry://asset/{assembly_job}"
                local_path = ""
                caption = f"[dry-run] {ep['title']}"
                credits_note = "dry-run: no credits spent"
            else:
                video_url = _assembly_asset_url(assembly_job)
                local_path = _download(video_url, ep)
                caption = write_caption(ep["title"], ep["script"])
                credits_note = ""
            set_status(
                sb,
                episode_id,
                "pending_video_review",
                video_url=video_url,
                caption=caption,
                local_path=local_path,
            )
            finish_run(sb, ref["run_id"], "success", credits_note=credits_note)
        return episode_id

    deliver(assemble_video(blocks(narration(verify_approved()))))


video_production()
