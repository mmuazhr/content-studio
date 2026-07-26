import json
import os
import subprocess
from uuid import uuid4

from pipeline.config import settings
from pipeline.db import get_episode

# Character reference job IDs, from docs/characters.md.
NARO_REF_JOB_ID = "6f818645-197a-4b31-a9f3-a41ead837de5"
EXA_REF_JOB_ID = "656394a8-98f3-4357-9219-0079086063f8"


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
    return json.loads(result.stdout)


def generate_narration(sb, ep) -> str:
    voice_id = os.getenv("HF_VOICE_ID", "")
    narration_text = " ".join(block["narration_bm"] for block in ep["script"])

    def submit():
        result = run_cli([
            "generate-audio",
            "--voice", voice_id,
            "--text", narration_text,
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
            "generate-video",
            "--aspect-ratio", "9:16",
            "--character-ref", NARO_REF_JOB_ID,
            "--character-ref", EXA_REF_JOB_ID,
            "--prompt", prompt,
        ])
        return result["id"]

    return ensure_job(sb, ep["id"], f"block_{idx}", submit)


def assemble(sb, ep) -> str:
    jobs = ep.get("higgsfield_jobs") or {}
    block_ids = [jobs[f"block_{i}"] for i in range(len(ep["script"]))]

    def submit():
        args = ["assemble", "--narration", jobs["narration"]]
        for block_id in block_ids:
            args += ["--block", block_id]
        result = run_cli(args)
        return result["id"]

    return ensure_job(sb, ep["id"], "assembly", submit)
