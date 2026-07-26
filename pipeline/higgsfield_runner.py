import json
import os
import subprocess
from uuid import uuid4

from pipeline.config import settings
from pipeline.db import get_episode

# Character reference job IDs, from docs/characters.md.
NARO_REF_JOB_ID = "6f818645-197a-4b31-a9f3-a41ead837de5"
EXA_REF_JOB_ID = "656394a8-98f3-4357-9219-0079086063f8"

# Higgsfield job types (CLI surface: `higgsfield generate create <job_type>`).
# Overridable via env; verify params with `higgsfield model get <jst>` after login.
AUDIO_JOB_TYPE = os.getenv("HF_AUDIO_JOB", "text2speech_v2")
VIDEO_JOB_TYPE = os.getenv("HF_VIDEO_JOB", "seedance_2_0")


def ensure_job(sb, episode_id, slot: str, submit_fn) -> str:
    ep = get_episode(sb, episode_id)
    jobs = dict(ep.get("higgsfield_jobs") or {})
    if slot in jobs:
        return jobs[slot]
    job_id = submit_fn()
    jobs[slot] = job_id
    sb.table("cs_episodes").update({"higgsfield_jobs": jobs}).eq("id", episode_id).execute()
    return job_id


def run_cli(args: list) -> dict:
    if settings.dry_run:
        return {"id": f"dry-{uuid4().hex[:8]}", "results": {"rawUrl": "dry://asset"}}
    result = subprocess.run(
        ["higgsfield", *args, "--json"],
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(result.stdout)
    # `--wait --json` prints the final job object array; normalize to one dict.
    if isinstance(payload, list):
        payload = payload[0]
    return payload


def get_job_result(job_id: str) -> dict:
    """Resolve a submitted job to its result payload (`results.rawUrl` is the asset)."""
    return run_cli(["generate", "get", job_id])


def generate_narration(sb, ep) -> str:
    voice_id = os.getenv("HF_VOICE_ID", "")
    narration_text = " ".join(block["narration_bm"] for block in ep["script"])

    def submit():
        result = run_cli([
            "generate", "create", AUDIO_JOB_TYPE,
            "--prompt", narration_text,
            "--voice_id", voice_id,
            "--voice_type", "preset",
            "--wait",
        ])
        return result["id"]

    return ensure_job(sb, ep["id"], "narration", submit)


def generate_block(sb, ep, idx: int) -> str:
    block = ep["script"][idx]
    prompt = block["visual"]
    if block.get("on_screen_text"):
        prompt = f"{prompt} | on-screen text: {block['on_screen_text']}"

    def submit():
        result = run_cli([
            "generate", "create", VIDEO_JOB_TYPE,
            "--prompt", prompt,
            "--image-references", NARO_REF_JOB_ID,
            "--image-references", EXA_REF_JOB_ID,
            "--aspect_ratio", "9:16",
            "--duration", "10",
            "--wait",
        ])
        return result["id"]

    return ensure_job(sb, ep["id"], f"block_{idx}", submit)


def assemble(sb, ep) -> str:
    jobs = ep.get("higgsfield_jobs") or {}
    block_ids = [jobs[f"block_{i}"] for i in range(len(ep["script"]))]

    def submit():
        if not settings.dry_run:
            # The stitching surface (explainer workflow vs local ffmpeg) can only
            # be verified against a logged-in CLI — finalized at first live run.
            # See docs/uat-checklist.md go-live section.
            raise RuntimeError(
                "live assembly surface not yet verified: run "
                "`higgsfield workflow list` after login and wire this call "
                f"(blocks: {block_ids}, narration: {jobs.get('narration')})"
            )
        return run_cli(["assemble-dry"])["id"]

    return ensure_job(sb, ep["id"], "assembly", submit)
