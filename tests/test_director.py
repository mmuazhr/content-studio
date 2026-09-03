import pytest

from pipeline import claude_tasks
from pipeline.director import DIRECTOR_SCRIPT_GUIDANCE, director


def test_script_guidance_sets_cerebral_practical_visual_language():
    assert "cause and effect" in DIRECTOR_SCRIPT_GUIDANCE
    assert "measured dolly" in DIRECTOR_SCRIPT_GUIDANCE
    assert "tactile practical detail" in DIRECTOR_SCRIPT_GUIDANCE
    assert "filmmaker" in DIRECTOR_SCRIPT_GUIDANCE


@pytest.mark.parametrize("shot", ["talk", "cutaway"])
def test_still_direction_is_shot_specific_and_cinematic(shot):
    direction = director.still_direction(shot)

    assert "Director's still plan" in direction
    assert "tactile miniature-set surfaces" in direction
    if shot == "cutaway":
        assert "physical metaphor" in direction
    else:
        assert "both mascots" in direction


def test_video_direction_requires_positive_duration_and_known_shot():
    direction = director.video_direction("talk", 8)

    assert "Director's motion plan (8s)" in direction
    assert "one continuous performance shot" in direction
    with pytest.raises(ValueError):
        director.video_direction("talk", 0)
    with pytest.raises(ValueError):
        director.video_direction("montage", 4)


def test_draft_script_includes_the_director_pass(monkeypatch):
    captured = {}

    def fake_retry(prompt, parse_fn, max_tokens=2000):
        captured["prompt"] = prompt
        return parse_fn(
            '[{"narration_bm": "Naro menerangkan satu perkara mudah hari ini.", '
            '"visual": "Naro points at a practical prop."}]'
        )

    monkeypatch.setattr(claude_tasks, "_call_with_retry", fake_retry)

    claude_tasks.draft_script("Apa itu AI?", "Pengenalan ringkas untuk pemula.")

    assert DIRECTOR_SCRIPT_GUIDANCE in captured["prompt"]
