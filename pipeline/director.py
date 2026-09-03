"""Directorial guidance shared by script and video generation.

The director is deliberately expressed as reusable production constraints
instead of a named-filmmaker imitation. It gives the creative model and the
video model the same visual grammar: high-concept clarity, deliberate camera
movement, tactile practical detail, controlled contrast, and a visual payoff.
"""
from dataclasses import dataclass

DIRECTOR_SCRIPT_GUIDANCE = """\
DIRECTOR'S PASS — cerebral, practical short-film language:
- Build each block around one clear question, physical action, or reveal.
- Write visuals as cause and effect: show what changes and why it matters.
- Use a deliberate camera choice (locked-off, measured dolly, macro push-in,
  or controlled lateral track), never random handheld movement.
- Prefer tactile practical detail: miniature props, visible surfaces, grounded
  physics, and motivated lighting over generic digital spectacle.
- Shape the short with an intriguing opening image, rising complication, and a
  clean visual payoff. Use a clock, repeated motion, match cut, or other time
  motif only when it clarifies the idea; chronology must stay easy to follow.
- Keep dialogue restrained and conversational. Let the image carry meaning;
  do not turn the characters into exposition machines.
- Keep the original voxel palette, mascot designs, Bahasa Melayu audience, and
  one dominant visual idea per block. Do not reference or imitate any named
  filmmaker.
"""

_SUPPORTED_SHOTS = {"talk", "cutaway"}


@dataclass(frozen=True)
class DirectorAgent:
    """Compile a consistent cinematic shot plan for each pipeline stage."""

    def _validate_shot(self, shot: str) -> None:
        if shot not in _SUPPORTED_SHOTS:
            raise ValueError(f"unsupported shot type: {shot}")

    def still_direction(self, shot: str) -> str:
        """Return image-generation direction for one storyboard block."""
        self._validate_shot(shot)
        if shot == "cutaway":
            composition = (
                "Compose a macro insert of one physical metaphor, with a clear "
                "before-and-after relationship and one readable focal prop."
            )
        else:
            composition = (
                "Frame both mascots in a layered mid-shot: the speaker is the "
                "visual anchor, the listener's reaction remains readable, and "
                "one practical prop supports the beat."
            )
        return (
            "Director's still plan: "
            f"{composition} Use a low eye-level 35mm-equivalent perspective, "
            "strong silhouettes, generous negative space, controlled depth, "
            "directional key light with a warm practical accent, deep but "
            "legible shadows, and tactile miniature-set surfaces."
        )

    def video_direction(self, shot: str, duration: int) -> str:
        """Return motion, pacing, and edit direction for one video block."""
        self._validate_shot(shot)
        if duration <= 0:
            raise ValueError("duration must be positive")
        if shot == "cutaway":
            beat = (
                "Make one continuous insert: begin on the complete metaphor, "
                "use a slow macro push-in or measured lateral track, show one "
                "physical cause-and-effect change, and end on the reveal."
            )
        else:
            beat = (
                "Make one continuous performance shot: begin on a visual "
                "question, use a measured push-in, let the speaker perform one "
                "concrete action, keep the listener's reaction visible, and end "
                "on a small visual reveal."
            )
        return (
            f"Director's motion plan ({duration}s): {beat} Keep motion "
            "precise and motivated, with grounded toy physics, subtle idle "
            "movement, restrained high-contrast lighting, and a tactile "
            "practical feel. Cut only on a meaningful beat; no whip pans, "
            "random handheld shake, floating CGI, or visual clutter."
        )


director = DirectorAgent()
