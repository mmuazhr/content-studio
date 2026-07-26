import pytest

from pipeline.script_schema import validate_script, ScriptValidationError


def test_valid_two_block_script_passes_and_fills_missing_sfx():
    script = [
        {"narration_bm": "Ini adalah narasi pertama untuk episod.", "visual": "Naro looking curious"},
        {"narration_bm": "Ini adalah narasi kedua untuk episod.", "visual": "Exa explaining", "on_screen_text": "AI 101"},
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
    block = {"narration_bm": "Narasi yang cukup panjang untuk lulus.", "visual": "shot"}
    with pytest.raises(ScriptValidationError):
        validate_script([block] * 6)


def test_missing_narration_bm_raises():
    with pytest.raises(ScriptValidationError):
        validate_script([{"visual": "shot only"}])


def test_non_string_field_raises():
    with pytest.raises(ScriptValidationError):
        validate_script([
            {"narration_bm": "Narasi yang cukup panjang untuk lulus.", "visual": "shot", "sfx": 123}
        ])
