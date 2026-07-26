# content-studio — Agentic Content Pipeline: Design Spec

Date: 2026-07-26
Status: Approved in brainstorm (sections 1–3); pending final user review of this doc.
Owner: Muaz. Orchestrating assistant: Claude.

## 1. Goal

An automated, agent-driven content pipeline for a Malay-language AI explainer
TikTok channel fronted by two voxel mascots — **Naro** (green alien, curious
learner) and **Exa** (mint-teal robot, AI expert; see `docs/characters.md`).

End-state chain: topic research → script/storyboard → video production →
TikTok posting → engagement checking → own-digital-product promotion — with
**human-in-the-loop approval gates** and a **dashboard** where Muaz reviews,
approves, and watches progress.

Constraints that shaped the design:
- Higgsfield subscription is the cheapest tier → **no credit is ever spent
  before a human approval**; no experimental generations.
- Muaz wants to **learn Apache Airflow hands-on** → Airflow is the
  orchestrator, run bare (pip + `airflow standalone`), not hidden in Docker.
- Start local, deploy later → all state in Supabase so re-homing the dashboard
  or Airflow later requires no schema change.

## 2. Decisions (locked)

| Decision | Choice |
|---|---|
| Monetization | Own digital products (course/ebook/templates, Malay) — promo episode type designed now, built last |
| Topic sourcing | Agent proposes 2–3 fully-drafted candidates per research run; Muaz approves/edits/rejects |
| Stack | Airflow (local, pip, standalone) + Supabase + FastAPI dashboard + Claude API + Higgsfield CLI |
| Triggering v1 | Manual DAG triggers (learning mode); scheduling enabled later by adding `schedule` to the DAG |
| Slice 1 scope | Research → approved video. Posting is manual in slice 1 |
| Dashboard UI | Built from a voxel/character-themed design system created on Claude Design (via DesignSync) |

## 3. Architecture

Six components, single-purpose, communicating only through Supabase (and
Airflow's REST API for triggers):

1. **Airflow** (`content-studio/airflow/`, DAGs in `airflow/dags/`) —
   orchestration + execution monitoring via its own UI (localhost:8080).
2. **Supabase** — single source of truth for domain state (episodes,
   approvals, runs). Airflow tasks and the dashboard both read/write it; they
   never call each other directly, except the dashboard triggering DAG runs
   via Airflow's REST API.
3. **Dashboard** (FastAPI + Jinja templates, job-agent pattern, localhost) —
   human decisions only: review scripts, edit, approve/reject, preview
   videos, trigger production, view history. Not an execution monitor.
4. **Agent tasks** — Python operators calling the Claude API for topic
   research and Malay script drafting, grounded in `docs/characters.md` and
   the episode block template.
5. **Higgsfield CLI** — narration + video block generation + assembly,
   called headlessly from Airflow tasks after one-time `higgsfield auth login`.
   Canonical character references (job IDs in `docs/characters.md`) are passed
   to every generation.
6. **Design system** — claude.ai/design project holding the voxel-themed UI
   kit; the dashboard implements those components.

Cost firewall property: everything before the script-approval gate costs ~zero
(Claude API pennies). Higgsfield credits are touched only after script
approval. Nothing goes public in slice 1.

## 4. Data model (Supabase)

### `episodes`
| Column | Type | Notes |
|---|---|---|
| `id` | uuid pk | |
| `ep_number` | int, nullable | assigned at script approval |
| `title` | text | |
| `topic_summary` | text | 1–2 sentence angle/hook rationale |
| `episode_type` | enum | `explainer` \| `intro` \| `promo` |
| `script` | jsonb | array of blocks: `{narration_bm, visual, on_screen_text, sfx}` |
| `status` | enum | see lifecycle below |
| `rejection_note` | text, nullable | feeds next research run |
| `video_url` | text, nullable | final asset URL |
| `caption` | text, nullable | TikTok caption + hashtags, generated at deliver |
| `local_path` | text, nullable | `assets/episodes/epNN/` |
| `higgsfield_jobs` | jsonb | `{narration: id, blocks: [ids], assembly: id}` — written **before** submission for idempotency |
| `created_at` / `updated_at` | timestamptz | ISO 8601 |

Status lifecycle (only these transitions are legal, enforced in code):
`proposed → pending_script_review → (script_approved | rejected | backlog)`
`script_approved → generating → pending_video_review → (video_approved | rejected)`
`video_approved → posted → archived`; any state → `error` (with log excerpt).

### `approvals`
`id`, `episode_id` fk, `gate` (`script` | `video` | `promo`), `decision`
(`approved` | `rejected` | `edited_then_approved`), `note`, `decided_at`.
Append-only audit trail; every dashboard decision writes one row.

### `runs`
`id`, `dag_id`, `airflow_run_id`, `episode_id` nullable fk, `outcome`,
`credits_note` (text summary of Higgsfield spend), `started_at`, `finished_at`.
Lets the dashboard show history without querying Airflow.

## 5. DAGs

### DAG 1 — `topic_research` (manual trigger; later `@weekly`)
1. `fetch_context` — past episodes + rejection notes from Supabase; character
   bible from repo.
2. `propose_topics` — Claude API → 2–3 candidates (Malay AI-explainer angles,
   hook-first, no repeats).
3. `draft_scripts` — Claude API → full block-format script per candidate,
   validated against the script JSON schema before save.
4. `save_candidates` — insert episodes with `status=pending_script_review`.
DAG terminates; it never waits on a human.

### DAG 2 — `video_production` (triggered per episode via REST, conf `{episode_id}`)
1. `verify_approved` — hard-fail unless `status=script_approved` (cost firewall).
2. `generate_narration` — Higgsfield CLI, the channel's fixed Malay narrator
   voice (voice ID stored in config after one-time selection).
3. `generate_blocks` — one generation per script block, passing Naro/Exa
   canonical reference job IDs; 9:16.
4. `assemble` — stitch blocks + narration (Higgsfield explainer assembly).
5. `deliver` — download to `assets/episodes/epNN/`, generate the TikTok
   caption + hashtags via Claude API (stored in `episodes.caption`), set
   `status=pending_video_review`, write `runs` row.

### HITL gates
- **Gate 1 (script)**: dashboard list of `pending_script_review` episodes →
  inline block editor → Approve & produce / Reject / Backlog. Approve writes
  `approvals` row, sets `script_approved`, then triggers DAG 2 via Airflow
  REST API. (Chosen over a waiting sensor task: idle sensors clutter a local
  scheduler; REST trigger also teaches a real integration pattern.)
- **Gate 2 (video)**: dashboard shows the assembled video + generated TikTok
  caption → Approve (→ `video_approved`, manual posting in slice 1) or Reject
  with note (→ `rejected`; re-generation is a NEW conscious trigger, never
  automatic).
- **Gate 3 (promo — designed, built last)**: any `episode_type=promo` requires
  an additional explicit confirmation step before production AND before
  posting, showing product claims for review.

## 6. Dashboard & design system

Design system project on claude.ai/design (pushed via DesignSync tool),
themed after the characters:
- Palette: warm cream `#f4efe6` background, beige voxel-tile surfaces,
  Naro green + jumpsuit blue, Exa mint-teal, dark pixel-ink text.
- Voxel language: chunky corners, cube accents, pixel-style status chips;
  character renders as state illustrations (Naro thinking = awaiting review,
  duo celebrating = video approved).
- Components: episode card, script-block editor, approval bar, video preview
  card, pipeline status timeline (7 voxel steps), run-history row.
Flow: push kit → Muaz reviews at claude.ai/design → approved kit becomes the
dashboard CSS/templates.

Dashboard pages (slice 1): Review queue (gate 1), Production/preview (gate 2),
History (episodes + runs). Localhost only; Supabase auth added at deploy time.

## 7. Error handling

- Transient failures (network/API hiccups): Airflow retries 2× with backoff.
- Higgsfield tasks: **check-before-spend idempotency** — job IDs are written
  to `episodes.higgsfield_jobs` before submission; a re-run reuses completed
  jobs instead of resubmitting. Generation tasks are never blind-retried.
- Any task failure → episode `status=error` + log excerpt visible in
  dashboard. No silent failures; no auto-recovery that costs credits.
- Claude API outputs validated against the script JSON schema before any
  Supabase write; malformed output fails the task, not the state.

## 8. Testing

- `DRY_RUN=1` env stubs all Higgsfield calls (fake job IDs, sample assets) —
  full `airflow dags test` rehearsals cost zero credits.
- Unit tests: script schema validator; status-transition guard (illegal moves
  raise); idempotency check (existing job ID → no resubmit).
- Dashboard: approve→REST-trigger path tested against Airflow in dry-run.
- First live run = EP00 (script already exists in `docs/episodes/ep00-intro.md`):
  seeded into Supabase as a pre-approved candidate, reviewed in the real
  dashboard, produced by the real DAG 2 — doubles as the pipeline's
  end-to-end acceptance test.

## 9. Build order

Slice 1 (this spec):
1. Supabase schema + migrations (+ status-transition guard)
2. Airflow standalone setup + DAG 1 with dry-run mode (hands-on Airflow learning)
3. Design system on Claude Design → visual approval
4. Dashboard (review queue, approve/trigger, preview, history)
5. DAG 2 dry-run end-to-end → one real run: EP00

Slice 2+: TikTok publishing DAG (Higgsfield tiktok tools / CLI), engagement
metrics DAG, promo gate build-out, dashboard deploy + auth, scheduled research,
virality-predictor pre-post scoring.

## 10. Decisions pending (needed during slice 1, not blockers to start)

1. Channel handle/name — required for EP00 end-card text before production.
2. Malay narrator voice — one-time pick from Higgsfield voices; stored in
   config and reused for all episodes.
