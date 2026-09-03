import dashboard.app as app_module
from pipeline.script_schema import validate_script


class RepeatedForm:
    def __init__(self, **fields):
        self.fields = fields

    def getlist(self, name):
        return self.fields.get(name, [])


def test_editor_form_round_trip_preserves_shot_and_speaker_metadata():
    form = RepeatedForm(
        narration_bm=["Naro bertanya apa itu AI hari ini.", ""],
        visual=["Naro bertanya di pentas.", "Puzzle pieces form the wrong answer."],
        on_screen_text=["", ""],
        sfx=["", "pop"],
        shot=["talk", "cutaway"],
        speaker=["naro", ""],
    )

    blocks = app_module._blocks_from_form(form)

    assert blocks[0]["shot"] == "talk"
    assert blocks[0]["speaker"] == "naro"
    assert blocks[1]["shot"] == "cutaway"
    assert blocks[1]["speaker"] == ""
    assert validate_script(blocks) == blocks
