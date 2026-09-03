import pytest

from pipeline.script_schema import ScriptValidationError, validate_script


def test_valid_two_block_script_passes_and_fills_missing_sfx():
    script = [
        {"shot": "talk", "speaker": "naro", "narration_bm": "Ini adalah narasi pertama untuk episod.", "visual": "Naro looking curious"},
        {"shot": "talk", "speaker": "exa", "narration_bm": "Ini adalah narasi kedua untuk episod.", "visual": "Exa explaining", "on_screen_text": "AI 101"},
    ]
    out = validate_script(script)
    assert len(out) == 2
    assert out[0]["sfx"] == ""
    assert out[0]["on_screen_text"] == ""
    assert out[1]["on_screen_text"] == "AI 101"


def test_empty_list_raises():
    with pytest.raises(ScriptValidationError):
        validate_script([])


def test_more_than_five_blocks_raises():
    block = {"shot": "talk", "speaker": "naro", "narration_bm": "Narasi yang cukup panjang untuk lulus.", "visual": "shot"}
    with pytest.raises(ScriptValidationError):
        validate_script([block] * 6)


def test_missing_narration_bm_raises():
    with pytest.raises(ScriptValidationError):
        validate_script([{"shot": "talk", "speaker": "naro", "visual": "shot only"}])


def test_talk_block_requires_speaker():
    with pytest.raises(ScriptValidationError, match="require speaker"):
        validate_script([{"shot": "talk", "narration_bm": "Narasi tanpa watak bercakap.", "visual": "shot"}])


def test_cutaway_has_no_speaker_or_narration():
    script = [{"shot": "cutaway", "visual": "A voxel clock stops.", "on_screen_text": ""}]

    assert validate_script(script)[0]["speaker"] == ""


def test_non_string_field_raises():
    with pytest.raises(ScriptValidationError):
        validate_script([
            {"shot": "talk", "speaker": "naro", "narration_bm": "Narasi yang cukup panjang untuk lulus.", "visual": "shot", "sfx": 123}
        ])
