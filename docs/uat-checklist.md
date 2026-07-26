# content-studio Slice 1 — UAT Checklist

Everything below runs locally. DRY_RUN=1 is set — **zero Higgsfield credits** are
spent during UAT. The full path was already machine-verified end-to-end on
2026-07-26 with a probe episode (since archived); EP00 is seeded and waiting for
your review.

## Start the stack (if not already running)

```bash
cd ~/Documents/Project/content-studio
sh scripts/start-airflow.sh          # Airflow UI: http://localhost:8080 (user: admin,
                                     #   password: airflow_home/standalone_admin_password.txt)
.venv/bin/uvicorn dashboard.app:app --port 8600   # Dashboard: http://localhost:8600
```

macOS notes (already baked into start-airflow.sh — for awareness):
- `OS_ACTIVITY_MODE=disable` — without it every Airflow worker segfaults (macOS os_log is not fork-safe).
- `execute_tasks_new_python_interpreter = True` in airflow_home/airflow.cfg — scheduler-run tasks hang in forked children without it.
- `auth_backends = ...basic_auth,...session` in airflow.cfg — REST triggers 403 without it.
- airflow.cfg is gitignored: if you ever delete airflow_home, re-apply the two cfg lines above.

## The 8 checks

1. **Queue** — open http://localhost:8600 → EP00 "Kenalkan Naro & Exa" is the only item, chip `pending_script_review`.
2. **Edit** — open the episode, tweak a narration line (e.g. change "Korang" phrasing), Save → page reloads with your edit kept.
3. **Approve script** — click Approve & produce → status flips to `script_approved`, then `generating` within ~30s.
4. **Airflow UI** — http://localhost:8080 → DAG `video_production` shows a running/success manual run (this was triggered by your click, via REST).
5. **Preview** — when status hits `pending_video_review` (~1 min in dry-run): episode page shows the (stub) video URL + generated caption. In dry-run the "video" is `dry://asset/...` — a placeholder, not a playable file.
6. **Approve video** — click Approve → `video_approved`. That's the slice-1 finish line (posting is manual by design).
7. **History** — /history lists EP00 + the runs with outcomes and "dry-run: no credits spent".
8. **Design system** — claude.ai/design → project "content-studio": voxel tokens, episode card, approval bar, timeline, script editor.

## Decisions still needed from you
- **Channel handle** — for EP00's end-card text (docs/episodes/ep00-intro.md Block 2) before the REAL production run.
- **Narrator voice** — provisional pick is **Hana** (already in `.env`). Listen to
  these previews (30s total) and swap `HF_VOICE_ID` if another fits BM narration
  better:
  - Hana (f): https://d1xarpci4ikg0w.cloudfront.net/audio_voice_preset/preview/3a978518-1fae-451e-bc30-08cb35b0d79f.mp3 — id `c25f78a0-714e-42af-8da3-a399cef94968`
  - Naomi (f): https://cdn.higgsfield.ai/audio_voice/bfe496ad-1296-441e-9ba6-02cfe4761eb3.wav — id `caeba733-3c17-43db-863e-69c7025512cd`
  - Leo (m): https://d1xarpci4ikg0w.cloudfront.net/audio_voice_preset/preview/65169043-8bf9-403e-84e4-0eb6262026fd.mp3 — id `73a45c18-0c56-4642-a61e-f6b303f8ded1`
  - Marcus (m): https://cdn.higgsfield.ai/audio_voice/cd7a989c-89ba-43c8-bc02-44a8c429825f.wav — id `6f98d3dd-324f-4845-8c28-c1d1647a06cd`
- ~~Anthropic API key~~ — NOT needed anymore: the pipeline now uses your Claude Code
  subscription (CLI `claude -p`) automatically when no real API key is set. An API
  key in `.env` only becomes relevant when this ever runs on a machine without
  your Claude login (e.g. cloud deploy).

## Go-live (spends real Higgsfield credits)
All prerequisites are DONE (2026-07-26): CLI installed + authed, workspace selected
(starter plan, 186 credits), job surfaces verified live, ffmpeg installed for local
assembly. Verified pipeline per block: Nano Banana still with Naro/Exa references
(2cr) → Kling 3.0 animates it via start_image, 10s, sound off (15cr); narration via
text2speech_v2/elevenlabs (~0.2cr). **EP00 total ≈ 35 credits.**

Remaining:
1. Confirm `HF_VOICE_ID` (provisional: Hana — previews above) + channel handle.
2. Set `DRY_RUN=0` in `.env`, restart the dashboard, approve EP00 in the queue →
   `assets/episodes/ep0/final.mp4`.
3. Set `DRY_RUN=1` back afterwards (default-safe).

## Security debt (slice 2, before ANY deploy)
- Enable RLS + policies on cs_episodes / cs_approvals / cs_runs (currently open to anyone with the anon key; also 5 older fluent-ai tables flagged).
- Dashboard has no auth (localhost only).
