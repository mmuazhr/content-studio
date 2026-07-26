import json
import os
import subprocess
from uuid import uuid4

from pipeline.config import settings
from pipeline.db import get_episode

# Canonical character reference IMAGES (docs/characters.md). Local paths — the
# CLI auto-uploads them as typed media_inputs; MCP-era job IDs are rejected by
# the server when passed from the CLI (verified live 2026-07-26).
def _ref(path: str) -> str:
    return str(settings.assets_root / "mascot-concepts" / path)


NARO_REF = "alien-a.png"
EXA_REF = "robot-b.png"

# Higgsfield job types (CLI surface: `higgsfield generate create <job_type>`),
# verified against the live CLI on 2026-07-26. Block pipeline: a Nano Banana
# still (character refs, 2cr) animated by Kling 3.0 via start_image (15cr,
# sound off) — cheaper and more character-faithful than direct text-to-video.
AUDIO_JOB_TYPE = os.getenv("HF_AUDIO_JOB", "text2speech_v2")
TTS_VARIANT = os.getenv("HF_TTS_VARIANT", "elevenlabs")
STILL_JOB_TYPE = os.getenv("HF_STILL_JOB", "nano_banana_2")
VIDEO_JOB_TYPE = os.getenv("HF_VIDEO_JOB", "kling3_0")


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
    """Resolve a submitted job to its result payload."""
    return run_cli(["generate", "get", job_id])


def result_url(payload: dict) -> str:
    """Asset URL across payload shapes: live CLI uses `result_url`, dry stubs
    use `results.rawUrl`."""
    url = payload.get("result_url") or (payload.get("results") or {}).get("rawUrl")
    if not url:
        raise RuntimeError(f"no result url in job payload: {list(payload.keys())}")
    return url


def generate_narration(sb, ep) -> str:
    voice_id = os.getenv("HF_VOICE_ID", "")
    narration_text = " ".join(block["narration_bm"] for block in ep["script"])

    def submit():
        result = run_cli([
            "generate", "create", AUDIO_JOB_TYPE,
            "--prompt", narration_text,
            "--variant", TTS_VARIANT,
            "--voice_id", voice_id,
            "--voice_type", "preset",
            "--wait",
        ])
        return result["id"]

    return ensure_job(sb, ep["id"], "narration", submit)


def generate_block(sb, ep, idx: int) -> str:
    block = ep["script"][idx]
    scene = block["visual"]
    if block.get("on_screen_text"):
        scene = f"{scene} | on-screen text: {block['on_screen_text']}"

    def submit_still():
        result = run_cli([
            "generate", "create", STILL_JOB_TYPE,
            "--prompt", (
                f"{scene}. Same exact voxel toy style as the reference images: "
                "chunky cube-built characters, matte clay-plastic render, soft "
                "studio lighting, beige voxel tile platform, warm cream background."
            ),
            "--image-references", _ref(NARO_REF),
            "--image-references", _ref(EXA_REF),
            "--aspect_ratio", "9:16",
            "--wait",
        ])
        return result["id"]

    still_id = ensure_job(sb, ep["id"], f"block_{idx}_still", submit_still)

    def submit_video():
        result = run_cli([
            "generate", "create", VIDEO_JOB_TYPE,
            "--prompt", f"Gentle toy-stop-motion style animation: {scene}. Subtle idle motion, slow camera push-in.",
            "--start-image", still_id,
            "--aspect_ratio", "9:16",
            "--duration", "10",
            "--sound", "off",
            "--wait",
        ])
        return result["id"]

    return ensure_job(sb, ep["id"], f"block_{idx}", submit_video)


def assemble(sb, ep) -> str:
    jobs = ep.get("higgsfield_jobs") or {}
    block_ids = [jobs[f"block_{i}"] for i in range(len(ep["script"]))]

    def submit():
        if settings.dry_run:
            return run_cli(["assemble-dry"])["id"]
        # No assembly workflow exists on the Higgsfield CLI (verified
        # 2026-07-26): stitch locally with ffmpeg — concat sound-off blocks,
        # overlay the narration track.
        ep_key = f"ep{ep['ep_number']}" if ep.get("ep_number") is not None else ep["id"]
        outdir = settings.assets_root / "episodes" / ep_key
        work = outdir / "work"
        work.mkdir(parents=True, exist_ok=True)

        narration_path = work / "narration.mp3"
        _download_asset(result_url(get_job_result(jobs["narration"])), narration_path)
        block_paths = []
        for i, block_id in enumerate(block_ids):
            path = work / f"block_{i}.mp4"
            _download_asset(result_url(get_job_result(block_id)), path)
            block_paths.append(path)

        listfile = work / "concat.txt"
        listfile.write_text("".join(f"file '{p}'\n" for p in block_paths))
        concat = work / "video_noaudio.mp4"
        _ffmpeg(["-f", "concat", "-safe", "0", "-i", str(listfile),
                 "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", str(concat)])
        final = outdir / "final.mp4"
        _ffmpeg(["-i", str(concat), "-i", str(narration_path),
                 "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac",
                 "-shortest", str(final)])
        return f"local:{final}"

    return ensure_job(sb, ep["id"], "assembly", submit)


def _download_asset(url: str, dest) -> None:
    import httpx

    with httpx.stream("GET", url, timeout=300, follow_redirects=True) as response:
        response.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in response.iter_bytes():
                fh.write(chunk)


def _ffmpeg(args: list) -> None:
    result = subprocess.run(
        ["ffmpeg", "-y", *args], capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr[-800:]}")
