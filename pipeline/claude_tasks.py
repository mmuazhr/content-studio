import json
import os
import shutil
import subprocess

import anthropic

from pipeline.config import settings
from pipeline.script_schema import validate_script, ScriptValidationError

MODEL = "claude-sonnet-5"
# CLI fallback rides the user's Claude subscription (no API key needed).
CLI_MODEL = "sonnet"
CLI_FALLBACK_PATH = os.path.expanduser("~/.local/bin/claude")

CHARACTER_BRIEF = """\
Channel: Malay-language (Bahasa Melayu) AI explainer duo, voxel/pixel-block toy
style. Naro (green voxel alien) is the curious learner — he asks the
questions the audience would ask, in Bahasa Melayu. Exa (mint-teal voxel
robot) is the AI expert — she explains and demos, santai (relaxed, friendly)
tone, no jargon, short plain-language sentences.

Episodes are CONVERSATIONS between Naro and Exa. Each block is ONE character
speaking ONE short line (max ~2 sentences, speakable in 8 seconds) — the
"speaker" field says who ("naro" or "exa"). Alternate speakers so it feels
like a real back-and-forth: typically Naro asks or reacts, Exa explains.
Both characters are visible in every block's scene; the non-speaking one
listens, nods, or reacts. Default 2-4 blocks (~16-32 seconds)."""


def _extract_json_array(text: str) -> str:
    """Models sometimes wrap JSON in markdown fences or prose — cut to the
    outermost JSON array before parsing."""
    start, end = text.find("["), text.rfind("]")
    if start != -1 and end > start:
        return text[start:end + 1]
    return text.strip()


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=settings.anthropic_key)


def _cli_path():
    """Path to the Claude Code CLI, or None. Used when no real API key is set."""
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if key and key != "REPLACE_ME":
        return None
    found = shutil.which("claude")
    if found:
        return found
    if os.path.exists(CLI_FALLBACK_PATH):
        return CLI_FALLBACK_PATH
    return None


def _call_cli(cli: str, prompt: str) -> str:
    # The CLI prefers ANTHROPIC_API_KEY over the claude.ai login if set —
    # strip the placeholder so the subscription auth is used.
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    result = subprocess.run(
        [cli, "-p", prompt, "--model", CLI_MODEL],
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(f"claude CLI failed: {result.stderr[:500]}")
    return result.stdout.strip()


def _call(prompt: str, max_tokens: int = 2000) -> str:
    cli = _cli_path()
    if cli:
        return _call_cli(cli, prompt)
    client = _client()
    message = client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def _call_with_retry(prompt: str, parse_fn, max_tokens: int = 2000):
    text = _call(prompt, max_tokens=max_tokens)
    try:
        return parse_fn(text)
    except Exception as exc:
        retry_prompt = (
            f"{prompt}\n\nYour previous response could not be parsed "
            f"({exc}). Respond again with ONLY valid JSON, no other text."
        )
        text = _call(retry_prompt, max_tokens=max_tokens)
        return parse_fn(text)


def propose_topics(past_titles: list, rejection_notes: list, n: int = 3) -> list:
    prompt = (
        f"{CHARACTER_BRIEF}\n\n"
        f"Past episode titles (do not repeat): {past_titles}\n"
        f"Rejection notes from past drafts (avoid these issues): {rejection_notes}\n\n"
        f"Propose {n} new episode topic candidates as a JSON array of objects "
        'with keys "title" and "topic_summary" (a 1-2 sentence angle/hook). '
        "Respond with ONLY the JSON array, no other text."
    )

    def parse(text: str) -> list:
        try:
            data = json.loads(_extract_json_array(text))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON: {exc}") from exc
        if not isinstance(data, list) or not data:
            raise ValueError("expected a non-empty JSON array")
        return data

    return _call_with_retry(prompt, parse)


def draft_script(title: str, topic_summary: str) -> list:
    prompt = (
        f"{CHARACTER_BRIEF}\n\n"
        f"Episode title: {title}\n"
        f"Topic summary: {topic_summary}\n\n"
        "Write the script as a JSON array of 1-4 blocks. Each block is an "
        'object with keys "speaker" ("naro" or "exa" — who says this line), '
        '"narration_bm" (that character\'s spoken line in Bahasa Melayu, one '
        "short line speakable in 8 seconds, 10-350 characters), "
        '"visual" (shot description: both characters visible, what the '
        "speaker does, how the listener reacts), "
        '"on_screen_text" (short keyword text or empty), "sfx". '
        "Alternate speakers like a conversation. "
        "Respond with ONLY the JSON array, no other text."
    )

    def parse(text: str) -> list:
        try:
            data = json.loads(_extract_json_array(text))
        except json.JSONDecodeError as exc:
            raise ScriptValidationError(f"invalid JSON: {exc}") from exc
        return validate_script(data)

    return _call_with_retry(prompt, parse)


def write_caption(title: str, script: list) -> str:
    prompt = (
        f"{CHARACTER_BRIEF}\n\n"
        f"Episode title: {title}\n"
        f"Script: {json.dumps(script, ensure_ascii=False)}\n\n"
        "Write a short TikTok caption (with hashtags) in Bahasa Melayu for "
        "this episode. Respond with ONLY the caption text, no other "
        "commentary."
    )
    return _call(prompt, max_tokens=300).strip()
