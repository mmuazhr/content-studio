"""Seed EP00 into cs_episodes.

    python scripts/seed_ep00.py           # real EP00, pending_script_review
    python scripts/seed_ep00.py --fake    # synthetic script_approved probe for DAG dry-runs

Content mirrors docs/episodes/ep00-intro.md (2 blocks, ~20s; the optional
block 3 CTA tail is deliberately left out).
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.config import settings
from pipeline.db import insert_episode
from pipeline.script_schema import validate_script

EP00_TITLE = "Kenalkan Naro & Exa"
EP00_SUMMARY = (
    "Channel + character intro: Naro asks what AI actually is, Exa introduces "
    "the duo and the weekly Bahasa Melayu AI explainer format."
)
EP00_SCRIPT = [
    {
        "narration_bm": (
            "Korang selalu dengar orang cakap pasal AI... tapi tak berapa "
            "faham benda tu sebenarnya apa?"
        ),
        "visual": (
            "Naro alone on the voxel platform, thinking pose, voxel question mark "
            "above his dome helmet (pose 5 from alien sheet). Camera slowly pushes "
            "in. At ~7s Exa slides in from the right holding his laptop, screen-face "
            "lights up."
        ),
        "on_screen_text": "AI tu... apa sebenarnya? 🤔",
        "sfx": 'Soft lo-fi/chiptune bed, "pop" when Exa slides in.',
    },
    {
        "narration_bm": (
            "Kenalkan — Naro dan Exa! Setiap minggu kitorang terangkan AI dalam "
            "Bahasa Melayu. Simple, santai, takde jargon. Jom belajar sama-sama!"
        ),
        "visual": (
            "Duo shot (canonical duo.png framing, recomposed for 9:16): Naro waves, "
            "Exa presents laptop. End on both in celebrate pose with voxel confetti "
            "(pose 4 on both sheets)."
        ),
        "on_screen_text": 'Naro 👽 + Exa 🤖 → end card: "Follow untuk belajar AI!"',
        "sfx": 'Bed continues, confetti "burst" at the end.',
    },
]

FAKE_TITLE = "FAKE dry-run probe"
FAKE_SUMMARY = "Synthetic episode used to rehearse video_production under DRY_RUN=1."
FAKE_SCRIPT = [
    {
        "narration_bm": "Blok satu untuk ujian dry-run sahaja.",
        "visual": "Naro waves on the voxel platform.",
        "on_screen_text": "",
        "sfx": "",
    },
    {
        "narration_bm": "Blok dua untuk ujian dry-run sahaja.",
        "visual": "Exa presents the laptop.",
        "on_screen_text": "",
        "sfx": "",
    },
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fake",
        action="store_true",
        help="insert a synthetic script_approved episode instead of EP00",
    )
    args = parser.parse_args()

    sb = settings.supabase()
    if args.fake:
        episode_id = insert_episode(
            sb,
            title=FAKE_TITLE,
            topic_summary=FAKE_SUMMARY,
            script=validate_script(FAKE_SCRIPT),
            status="script_approved",
        )
    else:
        episode_id = insert_episode(
            sb,
            title=EP00_TITLE,
            topic_summary=EP00_SUMMARY,
            script=validate_script(EP00_SCRIPT),
            episode_type="intro",
            status="pending_script_review",
        )
    print(episode_id)


if __name__ == "__main__":
    main()
