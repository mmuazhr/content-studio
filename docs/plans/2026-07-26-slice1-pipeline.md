# content-studio Slice 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Working local pipeline: Airflow research DAG → dashboard script approval → Airflow production DAG (dry-run capable) → dashboard video approval, with EP00 seeded for UAT.

**Architecture:** Airflow standalone orchestrates; Supabase is the single source of truth; FastAPI dashboard handles human approvals and triggers DAG 2 via Airflow REST API; Higgsfield CLI does generation (stubbed under DRY_RUN). Shared logic lives in a `pipeline/` package imported by DAGs, dashboard, and tests.

**Tech Stack:** Python 3.11+, apache-airflow (standalone), supabase-py, anthropic, FastAPI + Jinja2, httpx, pytest.

## Global Constraints (from spec)

- No Higgsfield credit spend unless episode `status=script_approved`; DRY_RUN=1 stubs all Higgsfield calls.
- Job IDs written to `episodes.higgsfield_jobs` BEFORE submission; re-runs reuse completed jobs (check-before-spend).
- Only legal status transitions (spec §4) may occur; illegal transition raises `IllegalTransition`.
- Claude API model for pipeline tasks: `claude-sonnet-5`. Script output validated against schema before any DB write.
- Supabase: reuse existing project; all tables prefixed `cs_`.
- All timestamps timestamptz ISO 8601. Aspect ratio 9:16 for all video generation.
- Character reference job IDs (from docs/characters.md): Naro `6f818645-197a-4b31-a9f3-a41ead837de5`, Exa `656394a8-98f3-4357-9219-0079086063f8`.

## File Structure

```
content-studio/
  requirements.txt
  .env.example                  # SUPABASE_URL, SUPABASE_KEY, ANTHROPIC_API_KEY, AIRFLOW_API_URL, AIRFLOW_API_TOKEN, DRY_RUN
  pipeline/
    __init__.py
    config.py                   # env loading, supabase client factory, DRY_RUN flag
    script_schema.py            # script JSON validation
    db.py                       # cs_* CRUD + status transition guard
    claude_tasks.py             # propose_topics, draft_script, write_caption
    higgsfield_runner.py        # CLI wrapper + dry-run stubs + idempotency
  airflow_home/                 # AIRFLOW_HOME (gitignored except dags/)
    dags/
      topic_research.py
      video_production.py
  dashboard/
    app.py                      # FastAPI app + routes
    airflow_client.py           # trigger_dag_run()
    templates/{base,queue,episode,history}.html
    static/voxel.css            # from design system
  design-system/                # pushed to Claude Design via DesignSync
    tokens.css
    previews/{colors,episode-card,approval-bar,status-timeline,script-editor}.html
  tests/
    test_script_schema.py
    test_db_transitions.py
    test_higgsfield_runner.py
    test_dashboard.py
  scripts/
    seed_ep00.py                # loads docs/episodes/ep00-intro.md content into cs_episodes
  docs/uat-checklist.md
```

---

### Task 1: Scaffold + config

**Files:** Create `requirements.txt`, `.env.example`, `pipeline/__init__.py`, `pipeline/config.py`, `.gitignore` additions.

**Interfaces — Produces:** `config.settings` object: `.supabase() -> Client`, `.dry_run: bool`, `.anthropic_key: str`, `.airflow_api_url: str`, `.airflow_api_token: str`, `.assets_root: Path`.

- [ ] Step 1: `requirements.txt`: `apache-airflow>=2.9`, `supabase>=2`, `anthropic`, `fastapi`, `uvicorn`, `jinja2`, `httpx`, `python-dotenv`, `pytest`, `python-multipart`. Install with `pip install -r requirements.txt` (use the official Airflow constraints URL for the installed Python: `pip install "apache-airflow>=2.9" --constraint https://raw.githubusercontent.com/apache/airflow/constraints-<airflow_version>/constraints-<py_version>.txt` first, then the rest).
- [ ] Step 2: `pipeline/config.py`:

```python
import os
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

class Settings:
    @property
    def dry_run(self) -> bool:
        return os.getenv("DRY_RUN", "1") == "1"   # default SAFE

    def supabase(self) -> Client:
        return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

    @property
    def anthropic_key(self) -> str: return os.environ["ANTHROPIC_API_KEY"]
    @property
    def airflow_api_url(self) -> str: return os.getenv("AIRFLOW_API_URL", "http://localhost:8080")
    @property
    def airflow_api_token(self) -> str: return os.getenv("AIRFLOW_API_TOKEN", "")
    @property
    def assets_root(self) -> Path:
        return Path(os.getenv("ASSETS_ROOT", str(Path(__file__).resolve().parent.parent / "assets")))

settings = Settings()
```

- [ ] Step 3: `.env.example` with every var above + comments; verify `python -c "from pipeline.config import settings"` runs.
- [ ] Step 4: Commit `chore: scaffold content-studio pipeline package`.

### Task 2: Supabase schema

**Files:** Migration via Supabase MCP `apply_migration` (name `cs_slice1_schema`); copy saved to `content-studio/db/migrations/001_cs_slice1_schema.sql`.

**Interfaces — Produces:** tables `cs_episodes`, `cs_approvals`, `cs_runs`.

- [ ] Step 1: Apply migration:

```sql
create type cs_episode_status as enum ('proposed','pending_script_review','script_approved','rejected','backlog','generating','pending_video_review','video_approved','posted','archived','error');
create type cs_episode_type as enum ('explainer','intro','promo');
create type cs_gate as enum ('script','video','promo');
create type cs_decision as enum ('approved','rejected','edited_then_approved');

create table cs_episodes (
  id uuid primary key default gen_random_uuid(),
  ep_number int,
  title text not null,
  topic_summary text not null default '',
  episode_type cs_episode_type not null default 'explainer',
  script jsonb not null default '[]',
  status cs_episode_status not null default 'proposed',
  rejection_note text,
  video_url text,
  caption text,
  local_path text,
  higgsfield_jobs jsonb not null default '{}',
  error_log text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create table cs_approvals (
  id uuid primary key default gen_random_uuid(),
  episode_id uuid not null references cs_episodes(id),
  gate cs_gate not null,
  decision cs_decision not null,
  note text,
  decided_at timestamptz not null default now()
);
create table cs_runs (
  id uuid primary key default gen_random_uuid(),
  dag_id text not null,
  airflow_run_id text not null,
  episode_id uuid references cs_episodes(id),
  outcome text not null default 'running',
  credits_note text,
  started_at timestamptz not null default now(),
  finished_at timestamptz
);
```

- [ ] Step 2: Verify with `list_tables` that the three `cs_` tables exist. Commit SQL copy — `feat: supabase schema for pipeline slice 1`.

### Task 3: Script schema validator (TDD)

**Files:** Create `pipeline/script_schema.py`, `tests/test_script_schema.py`.

**Interfaces — Produces:** `validate_script(script: list[dict]) -> list[dict]` (returns normalized blocks or raises `ScriptValidationError`). Block shape: `{"narration_bm": str, "visual": str, "on_screen_text": str, "sfx": str}` — 1–4 blocks, narration 10–350 chars, visual non-empty; `on_screen_text`/`sfx` may be empty strings.

- [ ] Step 1: Failing tests: valid 2-block script passes and fills missing `sfx` with `""`; empty list raises; >4 blocks raises; missing `narration_bm` raises; non-string field raises. Run `pytest tests/test_script_schema.py -v` → FAIL (module missing).
- [ ] Step 2: Implement (plain-python checks, no jsonschema dep):

```python
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
```

- [ ] Step 3: Tests pass; commit `feat: script block validator`.

### Task 4: DB layer + transition guard (TDD)

**Files:** Create `pipeline/db.py`, `tests/test_db_transitions.py`.

**Interfaces — Produces:**
- `LEGAL: dict[str, set[str]]`; `IllegalTransition(Exception)`
- `check_transition(cur: str, new: str) -> None` (raises IllegalTransition; `error` reachable from any state; `error`→`pending_script_review`/`script_approved` allowed for manual recovery)
- `set_status(sb, episode_id, new_status, **fields)` — reads current, checks, updates with `updated_at=now()`
- `insert_episode(sb, *, title, topic_summary, script, episode_type="explainer", status="pending_script_review") -> str`
- `record_approval(sb, episode_id, gate, decision, note="")`
- `record_run(sb, dag_id, airflow_run_id, episode_id=None) -> str`; `finish_run(sb, run_id, outcome, credits_note="")`
- `get_episode(sb, episode_id) -> dict`; `list_episodes(sb, status=None) -> list[dict]`; `next_ep_number(sb) -> int`

- [ ] Step 1: Failing tests for `check_transition` (pure function): legal chain passes (`proposed→pending_script_review→script_approved→generating→pending_video_review→video_approved→posted→archived`), `pending_script_review→{rejected,backlog}` pass, `proposed→generating` raises, `script_approved→video_approved` raises, `anything→error` passes, `error→script_approved` passes.
- [ ] Step 2: Implement `LEGAL` exactly from spec §4 + thin wrappers using `sb.table("cs_episodes")...`. Tests pass.
- [ ] Step 3: Commit `feat: episode state machine and db helpers`.

### Task 5: Claude agent tasks

**Files:** Create `pipeline/claude_tasks.py`, `tests/test_claude_tasks.py` (mocking `anthropic.Anthropic`).

**Interfaces — Produces:**
- `propose_topics(past_titles: list[str], rejection_notes: list[str], n=3) -> list[dict]` → `[{"title","topic_summary"}]`
- `draft_script(title: str, topic_summary: str) -> list[dict]` (validated blocks)
- `write_caption(title: str, script: list[dict]) -> str`
All use `claude-sonnet-5`, JSON-only responses parsed with one retry on parse failure, grounded in a `CHARACTER_BRIEF` constant summarizing docs/characters.md (Naro asks in BM, Exa explains, santai tone, no jargon, 2-block default ~20s).

- [ ] Step 1: Failing test: `draft_script` returns validated blocks when the (mocked) API returns a valid JSON array; raises `ScriptValidationError` after retry when it returns garbage twice.
- [ ] Step 2: Implement with `anthropic.Anthropic(api_key=settings.anthropic_key).messages.create(model="claude-sonnet-5", max_tokens=2000, messages=[...])`, prompts embedding CHARACTER_BRIEF + JSON-only instruction; `json.loads` of the text content; on failure re-ask once appending the parse error.
- [ ] Step 3: Tests pass; commit `feat: claude research, drafting and caption tasks`.

### Task 6: Higgsfield runner with dry-run + idempotency (TDD)

**Files:** Create `pipeline/higgsfield_runner.py`, `tests/test_higgsfield_runner.py`.

**Interfaces — Produces:**
- `ensure_job(sb, episode_id, slot: str, submit_fn) -> str` — slot like `"narration"`, `"block_0"`, `"assembly"`; if `higgsfield_jobs[slot]` exists, return it (NO resubmit); else call `submit_fn()` → job_id, write to `higgsfield_jobs[slot]` immediately, return.
- `run_cli(args: list[str]) -> dict` — wraps `subprocess.run(["higgsfield", *args, "--json"], ...)`; under `settings.dry_run` returns `{"id": f"dry-{uuid4().hex[:8]}", "results": {"rawUrl": "dry://asset"}}` without spawning anything.
- `generate_narration(sb, ep) -> str`, `generate_block(sb, ep, idx: int) -> str`, `assemble(sb, ep) -> str` — build CLI args (9:16, character reference job IDs from Global Constraints, narration voice from env `HF_VOICE_ID`, block prompt from `script[idx]["visual"]` + on_screen_text) and go through `ensure_job`.

- [ ] Step 1: Failing tests: with DRY_RUN, `ensure_job` calls `submit_fn` once then returns same id on second call without calling again (counting fake + dict-backed `FakeSB` stub); `run_cli` under dry-run never spawns a process (monkeypatch `subprocess.run` to raise if called).
- [ ] Step 2: Implement; tests pass.
- [ ] Step 3: Commit `feat: higgsfield runner with dry-run stubs and check-before-spend`.

### Task 7: Airflow setup + topic_research DAG

**Files:** Create `airflow_home/dags/topic_research.py`; `.gitignore` `airflow_home/*` except `dags/`.

**Interfaces — Consumes:** Tasks 4–5. **Produces:** DAG id `topic_research`.

- [ ] Step 1: Install + init: `AIRFLOW_HOME=$PWD/airflow_home airflow version`, then `airflow standalone` (first boot creates admin user; capture generated password and note the REST auth mechanism for the installed major version — consumed by Task 9).
- [ ] Step 2: DAG (TaskFlow API, `schedule=None`, `catchup=False`, tags `["content-studio"]`):

```python
from airflow.decorators import dag, task
import pendulum, sys
sys.path.insert(0, "/Users/muazhusaini/Documents/Project/content-studio")

@dag(schedule=None, start_date=pendulum.datetime(2026, 7, 1), catchup=False, tags=["content-studio"])
def topic_research():
    @task
    def fetch_context() -> dict:
        from pipeline.config import settings
        from pipeline.db import list_episodes
        sb = settings.supabase()
        eps = list_episodes(sb)
        return {"past_titles": [e["title"] for e in eps],
                "rejection_notes": [e["rejection_note"] for e in eps if e.get("rejection_note")]}

    @task
    def propose(ctx: dict) -> list[dict]:
        from pipeline.claude_tasks import propose_topics
        return propose_topics(ctx["past_titles"], ctx["rejection_notes"], n=3)

    @task
    def draft_and_save(cands: list[dict]) -> list[str]:
        from pipeline.config import settings
        from pipeline.claude_tasks import draft_script
        from pipeline.db import insert_episode
        sb = settings.supabase()
        ids = []
        for c in cands:
            script = draft_script(c["title"], c["topic_summary"])
            ids.append(insert_episode(sb, title=c["title"], topic_summary=c["topic_summary"], script=script))
        return ids

    draft_and_save(propose(fetch_context()))

topic_research()
```

- [ ] Step 3: Verify parse: `airflow dags list | grep topic_research`. Rehearsal: `airflow dags test topic_research 2026-07-26` with real ANTHROPIC_API_KEY (cheap) → rows appear `pending_script_review` (verify via Supabase `execute_sql`).
- [ ] Step 4: Commit `feat: topic_research DAG`.

### Task 8: video_production DAG

**Files:** Create `airflow_home/dags/video_production.py`.

**Interfaces — Consumes:** Tasks 4, 6. **Produces:** DAG id `video_production` accepting `dag_run.conf["episode_id"]`.

- [ ] Step 1: DAG tasks: `verify_approved` (get_episode; raise unless `script_approved`; `set_status('generating')`; `record_run`), `narration` (`generate_narration`), `blocks` (sequential `generate_block(sb, ep, i)` per script block — cheap plan, no parallelism), `assemble_video` (`assemble`), `deliver` (when not dry-run, httpx-stream final asset to `assets/episodes/ep{ep_number}/final.mp4`; `write_caption`; `set_status('pending_video_review', video_url=..., caption=..., local_path=...)`; `finish_run`). Wrap task bodies: any exception → `set_status(sb, ep_id, "error", error_log=str(exc)[:2000])`, re-raise.
- [ ] Step 2: Dry-run e2e: `scripts/seed_ep00.py --fake` inserts a synthetic `script_approved` episode; `airflow dags test video_production 2026-07-26 --conf '{"episode_id": "<id>"}'`; verify status walks to `pending_video_review` and `higgsfield_jobs` holds `narration`, `block_0`, `block_1`, `assembly` dry ids; re-run → ids unchanged (idempotency proof).
- [ ] Step 3: Commit `feat: video_production DAG with dry-run e2e`.

### Task 9: Airflow REST client

**Files:** Create `dashboard/airflow_client.py`, extend `tests/test_dashboard.py`.

**Interfaces — Produces:** `trigger_dag_run(dag_id: str, conf: dict) -> str` (returns dag_run_id; raises `AirflowTriggerError` on non-2xx).

- [ ] Step 1: Implement against the auth mechanism discovered in Task 7 (Airflow 2.x: `POST {base}/api/v1/dags/{dag_id}/dagRuns` basic auth; 3.x: bearer token from `/auth/token` then `POST {base}/api/v2/...`). Creds via `.env`. httpx, 10s timeout.
- [ ] Step 2: Unit test with `httpx.MockTransport` asserting URL, payload `{"conf": {...}}`, error raise on 403.
- [ ] Step 3: Live check: trigger `topic_research` via client; see run in Airflow UI. Commit `feat: airflow rest trigger client`.

### Task 10: Design system → Claude Design

**Files:** Create `design-system/tokens.css` + previews `colors,episode-card,approval-bar,status-timeline,script-editor`.html.

**Interfaces — Produces:** CSS custom properties consumed by `dashboard/static/voxel.css`: `--cs-bg:#f4efe6; --cs-tile:#e5dccb; --cs-ink:#23283a; --cs-naro:#6cbb5c; --cs-naro-suit:#4a7fd4; --cs-exa:#7fd8c4; --cs-accent:#e0803a; --cs-error:#d84a3a;` + `.cs-chip--<status>` for all 11 statuses, `.cs-card`, `.cs-btn{,--approve,--reject,--ghost}`, `.cs-timeline`.

- [ ] Step 1: tokens.css: palette above, chunky 4px borders, 10px radius, `box-shadow: 4px 4px 0` voxel offset, pixel-style chips. Previews each start `<!-- @dsCard group="..." -->`.
- [ ] Step 2: DesignSync: `list_projects` → `create_project` "content-studio" if absent → `finalize_plan` (writes `design-system/**`, localDir content-studio) → `write_files`.
- [ ] Step 3: Share claude.ai/design link for visual review (non-blocking; part of UAT). Commit `feat: voxel design system kit`.

### Task 11: Dashboard

**Files:** Create `dashboard/app.py`, `dashboard/templates/{base,queue,episode,history}.html`, `dashboard/static/voxel.css`, `tests/test_dashboard.py`.

**Interfaces — Consumes:** Tasks 4, 9. **Produces:** routes:
- `GET /` review queue (`pending_script_review` + `pending_video_review` + `error`)
- `GET /episode/{id}` detail: script block editor; `<video>` preview + caption when `pending_video_review`
- `POST /episode/{id}/script` — save edited blocks (validate_script; stays `pending_script_review`)
- `POST /episode/{id}/decision` — fields `gate` (`script`|`video`), `decision` (`approve`|`reject`|`backlog`), `note`. Script-approve: assign `next_ep_number`, `record_approval`, `set_status('script_approved')`, `trigger_dag_run("video_production", {"episode_id": id})`. Video-approve → `video_approved`. Reject → `rejected`+note; backlog → `backlog`. Unknown values → 400.
- `GET /history` — episodes + cs_runs.

- [ ] Step 1: Failing tests (TestClient + monkeypatched db/airflow fakes): queue lists pending episode; script-approve calls fake trigger with the episode id and writes approval; illegal decision → 400.
- [ ] Step 2: Implement (Jinja2Templates, static mount, PRG + flash query param; base.html header uses duo.png, chips per design system).
- [ ] Step 3: Tests pass; `uvicorn dashboard.app:app --port 8600`; click through with seeded data. Commit `feat: approval dashboard`.

### Task 12: EP00 seed + end-to-end + UAT handoff

**Files:** Create `scripts/seed_ep00.py`, `docs/uat-checklist.md`.

- [ ] Step 1: `seed_ep00.py`: inserts EP00 from docs/episodes/ep00-intro.md as data (title "Kenalkan Naro & Exa", type `intro`, the 2 storyboard blocks, `pending_script_review`); `--fake` inserts synthetic `script_approved` episode for Task 8.
- [ ] Step 2: Full dry-run e2e: seed EP00 → approve script in dashboard → Airflow runs video_production (DRY_RUN) → `pending_video_review` with dry asset → approve video → `video_approved`. Fix anything broken.
- [ ] Step 3: `docs/uat-checklist.md`: start commands, 8 UAT checks (queue shows EP00, edit narration, approve, Airflow UI run, preview, approve video, history, design link), pending decisions (channel handle, HF_VOICE_ID), go-live switch (`DRY_RUN=0`, `higgsfield auth login`, re-trigger EP00).
- [ ] Step 4: Commit `feat: ep00 seed and uat checklist`. Report UAT-ready.

## Self-Review (done)
- Spec coverage: schema→T2; lifecycle guard→T4; DAG1→T7; DAG2+caption→T8; gates→T11; design system→T10; error handling→T6/T8; dry-run testing→T3–T8, T11; EP00 acceptance→T12. Promo gate + posting = slice 2+ per spec. No gaps.
- Placeholder scan: all steps carry code, commands, or exact field lists; none of the forbidden patterns.
- Type consistency: `ensure_job(sb, episode_id, slot, submit_fn)` identical in T6/T8; `trigger_dag_run(dag_id, conf)` in T9/T11; status strings everywhere match the T2 enum.
