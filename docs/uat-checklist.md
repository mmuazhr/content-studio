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
- **Narrator voice** — say the word and I'll shortlist Malay-capable Higgsfield voices; the pick goes into `.env` as `HF_VOICE_ID`.
- ~~Anthropic API key~~ — NOT needed anymore: the pipeline now uses your Claude Code
  subscription (CLI `claude -p`) automatically when no real API key is set. An API
  key in `.env` only becomes relevant when this ever runs on a machine without
  your Claude login (e.g. cloud deploy).

## Go-live (after UAT passes — spends real Higgsfield credits)
1. Install Higgsfield CLI: `curl -fsSL https://raw.githubusercontent.com/higgsfield-ai/cli/main/install.sh | sh` then `higgsfield auth login` (browser sign-in).
2. Set `HF_VOICE_ID` and the channel handle; reset EP00 if it was consumed in UAT (re-run `.venv/bin/python scripts/seed_ep00.py`).
3. Set `DRY_RUN=0` in `.env`, restart the dashboard, approve EP00 → real narration + 2 video blocks + assembly are generated and downloaded to `assets/episodes/ep0/final.mp4`.
4. Set `DRY_RUN=1` back afterwards (default-safe).

## Security debt (slice 2, before ANY deploy)
- Enable RLS + policies on cs_episodes / cs_approvals / cs_runs (currently open to anyone with the anon key; also 5 older fluent-ai tables flagged).
- Dashboard has no auth (localhost only).
