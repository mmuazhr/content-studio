class ScriptValidationError(ValueError): ...

REQUIRED = ("narration_bm", "visual")
OPTIONAL = ("on_screen_text", "sfx")


def validate_script(script):
    if not isinstance(script, list) or not (1 <= len(script) <= 4):
        raise ScriptValidationError("script must be a list of 1-4 blocks")
    out = []
    for i, b in enumerate(script):
        if not isinstance(b, dict):
            raise ScriptValidationError(f"block {i} not an object")
        blk = {}
        for k in REQUIRED:
            v = b.get(k)
            if not isinstance(v, str) or not v.strip():
                raise ScriptValidationError(f"block {i} missing {k}")
            blk[k] = v.strip()
        if not (10 <= len(blk["narration_bm"]) <= 350):
            raise ScriptValidationError(f"block {i} narration length out of range")
        for k in OPTIONAL:
            v = b.get(k, "")
            if not isinstance(v, str):
                raise ScriptValidationError(f"block {i} {k} must be string")
            blk[k] = v.strip()
        out.append(blk)
    return out
