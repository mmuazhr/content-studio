# Content Studio

Automated video pipeline for the **Naro & Exa** mascot channel: an Airflow
DAG turns a topic into a scripted, narrated, animated episode, a human
approves it from a dashboard, and Supabase tracks every episode's state
end-to-end.

## Pipeline

1. **Topic research** (`topic_research` DAG) — proposes and scores episode
   topics.
2. **Script generation** (`pipeline/claude_tasks.py`) — Claude writes the
   episode script against `pipeline/script_schema.py`.
3. **Asset generation** (`pipeline/higgsfield_runner.py`) — stills and talking
   clips for Naro & Exa via Higgsfield.
4. **Video production** (`video_production` DAG) — assembles narration +
   generated clips into a final cut, tracked through Supabase-backed state
   transitions (`pipeline/db.py`).
5. **Human approval** — the dashboard (`dashboard/app.py`, FastAPI) shows
   pending episodes for review before publish.

State for each episode lives in Supabase (`cs_*` tables); Airflow orchestrates
the DAGs, the dashboard is the human-in-the-loop gate.

## Setup

```bash
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
cp .env.example .env   # fill in Supabase, Anthropic, Airflow, Higgsfield creds
```

### Run the dashboard

```bash
./.venv/bin/uvicorn dashboard.app:app --reload
```

### Run Airflow (DAG scheduler + trigger API)

```bash
./scripts/start-airflow.sh
# DAGs: topic_research, video_production — trigger from the Airflow UI
# or via AIRFLOW_API_URL from the dashboard
```

Set `DRY_RUN=1` (default) to stub Higgsfield calls with no credit spend;
`DRY_RUN=0` goes live.

## Project layout

```
content-studio/
├─ pipeline/          claude_tasks.py · higgsfield_runner.py · db.py · script_schema.py
├─ dashboard/          FastAPI approval UI (app.py)
├─ airflow_home/dags/  topic_research.py · video_production.py
├─ assets/             episodes/ (final cuts) · mascot-concepts/
├─ design-system/      brand tokens + previews
├─ scripts/            seed_ep00.py · start-airflow.sh
└─ docs/                specs/ · plans/ · episodes/
```

## Tests

```bash
./.venv/bin/pytest
```

Covers Claude task generation, script schema validation, DB state
transitions, the Higgsfield runner, and the dashboard.
