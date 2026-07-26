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


# duo-v2: coral Exa + chest name tags (canon since 2026-07-26, job ff2361ae)
DUO_REF = "duo-v2.png"

# Higgsfield job types (CLI surface: `higgsfield generate create <job_type>`),
# verified against the live CLI on 2026-07-26. Block pipeline: a Nano Banana
# still (character refs, 2cr) animated by Kling 3.0 via start_image (15cr,
# sound off) — cheaper and more character-faithful than direct text-to-video.
AUDIO_JOB_TYPE = os.getenv("HF_AUDIO_JOB", "text2speech_v2")
TTS_VARIANT = os.getenv("HF_TTS_VARIANT", "elevenlabs")
STILL_JOB_TYPE = os.getenv("HF_STILL_JOB", "nano_banana_2")
# Format v3 (2026-07-26): talk blocks use veo3_1 (audio ALWAYS native — the Lite
# tier silently dropped audio on a full run); cutaway concept inserts use the
# cheap Lite tier with audio off.
TALK_JOB_TYPE = os.getenv("HF_TALK_JOB", "veo3_1")
CUTAWAY_JOB_TYPE = os.getenv("HF_CUTAWAY_JOB", "veo3_1_lite")
TALK_SECONDS = 8
CUTAWAY_SECONDS = 4

# Explicit feature lock — the drift run produced a domeless, five-antenna Naro.
CHARACTER_LOCK = (
    "Characters must match the reference image EXACTLY: Naro is the green voxel "
    "alien inside his round transparent glass dome helmet, exactly ONE antenna, "
    "blue jumpsuit with a white NARO chest name tag. Exa is the coral-orange "
    "voxel robot with a pale TV-screen face, one antenna, a white EXA chest name "
    "tag, grey voxel laptop. No extra antennas, no glowing parts, no invented "
    "accessories, no color changes."
)

# Prompt templates hardened per Veo/Kling prompting research (2026-07-26):
# one speaker per clip, colon dialogue syntax, tone adjectives, motion-only
# for image-to-video, explicit no-subtitles (Veo burns captions otherwise).
CHAR_VOICE = {
    "naro": (
        "Naro, the small green voxel alien in the glass dome helmet, looks at "
        "the camera and speaks with a curious, excited child-like voice"
    ),
    "exa": (
        "Exa, the coral-orange voxel robot with the TV-screen face, looks at the "
        "camera and speaks with a warm, cheerful child-like voice with a "
        "slight friendly robotic chirp"
    ),
}


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
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"higgsfield CLI failed ({result.returncode}): {result.stderr[-600:]}"
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


def episode_dir(ep) -> str:
    """Collision-proof per-episode folder: number + id prefix."""
    n = ep.get("ep_number")
    prefix = f"ep{n:02d}-" if n is not None else ""
    return f"{prefix}{ep['id'][:8]}"


def generate_block(sb, ep, idx: int) -> str:
    block = ep["script"][idx]
    scene = block["visual"]  # on-screen text is rendered by ffmpeg, never baked
    shot = block.get("shot", "talk")
    speaker = block.get("speaker", "")

    if shot == "cutaway":
        still_prompt = (
            f"{scene}. Chunky voxel toy diorama visualizing this concept as a "
            "physical miniature scene, cube-built props, matte clay-plastic "
            "render, soft studio lighting, beige voxel tile platform, warm "
            f"cream background, clean composition. {CHARACTER_LOCK} No text "
            "anywhere in the image."
        )
    else:
        still_prompt = (
            f"{scene}. Chunky voxel toy diorama, cube-built figures, matte "
            "clay-plastic render, soft studio lighting, beige voxel tile "
            "platform, warm cream background, clean centered composition, "
            f"generous headroom. {CHARACTER_LOCK} No text anywhere in the image."
        )

    def submit_still():
        result = run_cli([
            "generate", "create", STILL_JOB_TYPE,
            "--prompt", still_prompt,
            "--image-references", _ref(DUO_REF),
            "--aspect_ratio", "9:16",
            "--wait",
        ])
        return result["id"]

    still_id = ensure_job(sb, ep["id"], f"block_{idx}_still", submit_still)

    def submit_video():
        if settings.dry_run:
            return run_cli(["dry-video"])["id"]
        # Job IDs are rejected as media inputs by this CLI version (sent
        # untyped) — download the still and pass a local file path instead.
        work = settings.assets_root / "episodes" / episode_dir(ep) / "work"
        work.mkdir(parents=True, exist_ok=True)
        still_path = work / f"still_{idx}.png"
        _download_asset(result_url(get_job_result(still_id)), still_path)
        if shot == "cutaway":
            args = [
                "generate", "create", CUTAWAY_JOB_TYPE,
                "--prompt", (
                    f"Bring this concept diorama to life: {scene}. Gentle "
                    "stop-motion toy animation, playful motion, slow camera "
                    "push-in. No subtitles, no captions, no text on screen."
                ),
                "--start-image", str(still_path),
                "--aspect_ratio", "9:16",
                "--duration", str(CUTAWAY_SECONDS),
                "--generate_audio", "false",
                "--wait",
            ]
        else:
            line = block["narration_bm"]
            args = [
                "generate", "create", TALK_JOB_TYPE,
                "--prompt", (
                    f'{CHAR_VOICE[speaker]}, speaking TO the audience, saying '
                    f'in Bahasa Melayu: "{line}". The character\'s mouth '
                    "movement matches the words; the other character reacts "
                    "(nods, tilts, listens). Gentle stop-motion toy animation, "
                    "subtle idle bobbing, slow camera push-in. Soft cheerful "
                    "room ambience. No subtitles, no captions, no text on "
                    "screen."
                ),
                "--start-image", str(still_path),
                "--aspect_ratio", "9:16",
                "--duration", str(TALK_SECONDS),
                "--wait",
            ]
            if "lite" in TALK_JOB_TYPE:
                # veo3_1 has always-on native audio (no param); the Lite tier
                # exposes generate_audio and DEFAULTS TO OFF — force it on.
                args[-1:-1] = ["--generate_audio", "true"]
        return run_cli(args)["id"]

    return ensure_job(sb, ep["id"], f"block_{idx}", submit_video)


def assemble(sb, ep) -> str:
    jobs = ep.get("higgsfield_jobs") or {}
    block_ids = [jobs[f"block_{i}"] for i in range(len(ep["script"]))]

    def submit():
        if settings.dry_run:
            return run_cli(["assemble-dry"])["id"]
        # No assembly workflow exists on the Higgsfield CLI (verified
        # 2026-07-26): stitch locally with ffmpeg.
        outdir = settings.assets_root / "episodes" / episode_dir(ep)
        work = outdir / "work"
        work.mkdir(parents=True, exist_ok=True)

        script = ep["script"]
        block_paths, durations = [], []
        for i, block_id in enumerate(block_ids):
            path = work / f"block_{i}.mp4"
            _download_asset(result_url(get_job_result(block_id)), path)
            blk = script[i]
            is_talk = blk.get("shot", "talk") == "talk" and blk.get("speaker")
            if is_talk and not _has_audio(path):
                # Fail loudly — never ship a silent talking block again.
                raise RuntimeError(
                    f"block {i} is a talking block but came back with NO audio "
                    f"(job {block_id}) — regenerate before assembling"
                )
            # Normalize EVERY block to one audio format (48k stereo AAC) —
            # the concat demuxer cannot switch stream params mid-stream, and a
            # mismatched silent track corrupted all audio after the cutaway.
            norm = work / f"block_{i}_norm.mp4"
            if _has_audio(path):
                _ffmpeg(["-i", str(path), "-c:v", "copy",
                         "-c:a", "aac", "-ar", "48000", "-ac", "2", str(norm)])
            else:
                _ffmpeg(["-i", str(path), "-f", "lavfi",
                         "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
                         "-shortest", "-c:v", "copy",
                         "-c:a", "aac", "-ar", "48000", "-ac", "2", str(norm)])
            block_paths.append(norm)
            durations.append(_video_duration(norm))

        listfile = work / "concat.txt"
        listfile.write_text("".join(f"file '{p}'\n" for p in block_paths))
        base = work / "base.mp4"
        _ffmpeg(["-f", "concat", "-safe", "0", "-i", str(listfile),
                 "-c:v", "libx264", "-pix_fmt", "yuv420p",
                 "-c:a", "aac", str(base)])

        final = outdir / "final.mp4"
        overlays = _make_overlays(script, work, _video_size(base), durations)
        if overlays:
            args = ["-i", str(base)]
            for png, _, _ in overlays:
                args += ["-i", str(png)]
            chain, prev = [], "0:v"
            for n, (_, start, end) in enumerate(overlays, 1):
                out = f"v{n}"
                chain.append(
                    f"[{prev}][{n}:v]overlay=0:0:enable='between(t,{start},{end})'[{out}]"
                )
                prev = out
            _ffmpeg(args + ["-filter_complex", ";".join(chain),
                            "-map", f"[{prev}]", "-map", "0:a?",
                            "-c:v", "libx264", "-pix_fmt", "yuv420p",
                            "-c:a", "copy", str(final)])
        else:
            _ffmpeg(["-i", str(base), "-c", "copy", str(final)])
        return f"local:{final}"

    return ensure_job(sb, ep["id"], "assembly", submit)


OVERLAY_FONT = "/System/Library/Fonts/Supplemental/Courier New Bold.ttf"


def _video_size(path) -> tuple:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    ).stdout.strip().split(",")
    return int(out[0]), int(out[1])


def _video_duration(path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    ).stdout.strip()
    return float(out)


def _has_audio(path) -> bool:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a",
         "-show_entries", "stream=codec_name", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    ).stdout.strip()
    return bool(out)


def _make_overlays(script: list, work, size: tuple, durations: list) -> list:
    """Render each block's on_screen_text as a transparent PNG (voxel style:
    ink text on a cream box, bottom third) — composited via ffmpeg's core
    `overlay` filter, since this ffmpeg build lacks drawtext. Timing windows
    come from the blocks' REAL durations (models often return shorter clips
    than requested). Returns [(png_path, start_s, end_s)]."""
    from PIL import Image, ImageDraw, ImageFont

    width, height = size
    starts, t = [], 0.0
    for d in durations:
        starts.append(t)
        t += d
    overlays = []
    for i, block in enumerate(script):
        text = (block.get("on_screen_text") or "").strip()
        text = "".join(ch for ch in text if ord(ch) < 0x2190).strip()
        if not text:
            continue
        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        font = ImageFont.truetype(OVERLAY_FONT, max(30, width // 16))
        # naive 2-line wrap when too wide for safe margins
        lines = [text]
        if draw.textlength(text, font=font) > width * 0.84 and " " in text:
            mid = len(text) // 2
            split = text.rfind(" ", 0, mid) if text.rfind(" ", 0, mid) > 0 else text.find(" ", mid)
            lines = [text[:split].strip(), text[split:].strip()]
        line_h = font.size + 10
        box_h = line_h * len(lines) + 36
        y0 = int(height * 0.74)
        draw.rounded_rectangle(
            [int(width * 0.05), y0, int(width * 0.95), y0 + box_h],
            radius=14, fill=(244, 239, 230, 235), outline=(35, 40, 58, 255), width=4,
        )
        for n, line in enumerate(lines):
            tw = draw.textlength(line, font=font)
            draw.text(((width - tw) / 2, y0 + 18 + n * line_h), line,
                      font=font, fill=(35, 40, 58, 255))
        png = work / f"overlay_{i}.png"
        img.save(png)
        overlays.append((png, round(starts[i], 2), round(starts[i] + durations[i], 2)))
    return overlays


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
