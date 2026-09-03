# Director Agent

`pipeline/director.py` is the creative-control layer shared by Claude script
drafting and Higgsfield image/video generation. It keeps the pipeline's
cinematic language consistent without relying on a named filmmaker reference.

## Creative brief

The director favors:

- high-concept clarity: one question, physical action, or reveal per block;
- cause-and-effect visuals instead of exposition-heavy dialogue;
- deliberate camera movement such as a locked-off frame, measured dolly, macro
  push-in, or controlled lateral track;
- tactile practical detail, motivated lighting, controlled contrast, and
  grounded toy physics;
- short-form escalation: intriguing opening image, rising complication, and a
  clean visual payoff;
- restrained Bahasa Melayu dialogue that lets the image carry meaning.

The brief can feel cerebral and time-aware while remaining original to Naro,
Exa, and the voxel world. Time motifs are optional and must clarify the idea,
not make a short episode confusing.

## Integration points

- `draft_script()` includes `DIRECTOR_SCRIPT_GUIDANCE` so Claude writes
  storyboard visuals with camera and reveal intent.
- `generate_block()` adds `director.still_direction()` to the image prompt and
  `director.video_direction()` to the motion prompt.
- Both functions are deterministic and covered by `tests/test_director.py`, so
  the directorial layer does not add another paid model call.

To change the channel's visual grammar, edit the brief and the two shot plans
together, then run the full test suite before producing new credits-consuming
assets.

## Script format migration

The production preflight now requires v3 storyboard metadata: every `talk`
block must name `naro` or `exa`, and every `cutaway` block must omit a speaker.
Legacy drafts fail safely before asset generation; assign the shot and speaker
in the dashboard before approving them.
