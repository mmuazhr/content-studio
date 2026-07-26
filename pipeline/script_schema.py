class ScriptValidationError(ValueError): ...

REQUIRED = ("narration_bm", "visual")
OPTIONAL = ("on_screen_text", "sfx")
SPEAKERS = ("", "naro", "exa")  # "" = off-screen narrator
SHOTS = ("talk", "cutaway")  # cutaway = silent concept-visualization insert


def validate_script(script):
    if not isinstance(script, list) or not (1 <= len(script) <= 4):
        raise ScriptValidationError("script must be a list of 1-4 blocks")
    out = []
    for i, b in enumerate(script):
        if not isinstance(b, dict):
            raise ScriptValidationError(f"block {i} not an object")
        blk = {}
        shot = b.get("shot", "talk")
        if not isinstance(shot, str) or shot.strip().lower() not in SHOTS:
            raise ScriptValidationError(f"block {i} shot must be one of {SHOTS}")
        blk["shot"] = shot.strip().lower()
        cutaway = blk["shot"] == "cutaway"
        for k in REQUIRED:
            v = b.get(k, "")
            if not isinstance(v, str):
                raise ScriptValidationError(f"block {i} {k} must be string")
            if not v.strip() and not (cutaway and k == "narration_bm"):
                raise ScriptValidationError(f"block {i} missing {k}")
            blk[k] = v.strip()
        if cutaway:
            if b.get("speaker", "").strip():
                raise ScriptValidationError(f"block {i} cutaway must have no speaker")
        elif not (10 <= len(blk["narration_bm"]) <= 350):
            raise ScriptValidationError(f"block {i} narration length out of range")
        for k in OPTIONAL:
            v = b.get(k, "")
            if not isinstance(v, str):
                raise ScriptValidationError(f"block {i} {k} must be string")
            blk[k] = v.strip()
        speaker = b.get("speaker", "")
        if not isinstance(speaker, str) or speaker.strip().lower() not in SPEAKERS:
            raise ScriptValidationError(
                f"block {i} speaker must be one of {SPEAKERS}"
            )
        blk["speaker"] = speaker.strip().lower()
        out.append(blk)
    return out
