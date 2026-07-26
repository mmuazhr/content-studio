"""Human approval gates for the content-studio pipeline.

Two gates: script (approve -> assign ep number, trigger video_production) and
video (approve -> video_approved). Supabase is the source of truth; every status
change goes through pipeline.db.set_status so illegal transitions are rejected.
"""
from pathlib import Path
from urllib.parse import quote

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from dashboard.airflow_client import AirflowTriggerError, trigger_dag_run
from pipeline.config import settings
from pipeline.db import (
    IllegalTransition,
    _now,
    get_episode,
    list_episodes,
    next_ep_number,
    record_approval,
    set_status,
)
from pipeline.script_schema import ScriptValidationError, validate_script

BASE_DIR = Path(__file__).resolve().parent
QUEUE_STATUSES = (
    "pending_script_review",
    "script_approved",
    "generating",
    "pending_video_review",
    "error",
)
GATES = ("script", "video")
DECISIONS = ("approve", "reject", "backlog")
TRIGGERABLE_STATUSES = ("script_approved", "generating")
TIMELINE = (
    "proposed",
    "pending_script_review",
    "script_approved",
    "generating",
    "pending_video_review",
    "video_approved",
    "posted",
)

app = FastAPI(title="content-studio approvals")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.mount("/assets", StaticFiles(directory=str(settings.assets_root)), name="assets")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.globals["TIMELINE"] = TIMELINE


def get_sb():
    """Supabase client dependency — overridden with a fake in tests."""
    return settings.supabase()


def _redirect(path: str, *, msg: str = "", error: str = "") -> RedirectResponse:
    params = []
    if msg:
        params.append(f"msg={quote(msg)}")
    if error:
        params.append(f"error={quote(error)}")
    url = f"{path}?{'&'.join(params)}" if params else path
    return RedirectResponse(url, status_code=303)


def _blocks_from_form(form) -> list:
    """Rebuild script blocks from the parallel per-field lists the editor posts."""
    narrations = form.getlist("narration_bm")
    visuals = form.getlist("visual")
    on_screen = form.getlist("on_screen_text")
    sfx = form.getlist("sfx")
    return [
        {
            "narration_bm": narrations[i],
            "visual": visuals[i] if i < len(visuals) else "",
            "on_screen_text": on_screen[i] if i < len(on_screen) else "",
            "sfx": sfx[i] if i < len(sfx) else "",
        }
        for i in range(len(narrations))
    ]


def _save_script(sb, episode_id: str, blocks: list) -> None:
    # Status is unchanged (stays pending_script_review), so this bypasses set_status.
    sb.table("cs_episodes").update({"script": blocks, "updated_at": _now()}).eq(
        "id", episode_id
    ).execute()


def _asset_src(ep: dict) -> str:
    """Browser-playable URL for the episode video, or "" when there isn't one."""
    local_path = ep.get("local_path") or ""
    if local_path:
        try:
            rel = Path(local_path).resolve().relative_to(settings.assets_root.resolve())
        except ValueError:
            return ""
        return f"/assets/{rel}"
    url = ep.get("video_url") or ""
    return url if url.startswith("http") else ""


@app.get("/")
def queue(request: Request, sb=Depends(get_sb)):
    episodes = [e for e in list_episodes(sb) if e["status"] in QUEUE_STATUSES]
    episodes.sort(key=lambda e: (QUEUE_STATUSES.index(e["status"]), e.get("created_at") or ""))
    return templates.TemplateResponse(
        request, "queue.html", {"episodes": episodes, "queue_statuses": QUEUE_STATUSES}
    )


@app.get("/episode/{episode_id}")
def episode_detail(episode_id: str, request: Request, sb=Depends(get_sb)):
    ep = get_episode(sb, episode_id)
    if not ep:
        raise HTTPException(status_code=404, detail="episode not found")
    return templates.TemplateResponse(
        request, "episode.html", {"ep": ep, "asset_src": _asset_src(ep)}
    )


@app.post("/episode/{episode_id}/script")
async def save_script(episode_id: str, request: Request, sb=Depends(get_sb)):
    form = await request.form()
    try:
        blocks = validate_script(_blocks_from_form(form))
    except ScriptValidationError as exc:
        return _redirect(f"/episode/{episode_id}", error=str(exc))
    _save_script(sb, episode_id, blocks)
    return _redirect(f"/episode/{episode_id}", msg="Script saved")


@app.post("/episode/{episode_id}/decision")
async def decide(
    episode_id: str,
    request: Request,
    gate: str = Form(...),
    decision: str = Form(...),
    note: str = Form(""),
    sb=Depends(get_sb),
):
    if gate not in GATES or decision not in DECISIONS:
        raise HTTPException(status_code=400, detail=f"unknown gate/decision: {gate}/{decision}")
    ep = get_episode(sb, episode_id)
    if not ep:
        raise HTTPException(status_code=404, detail="episode not found")

    edited = False
    if gate == "script":
        form = await request.form()
        posted = _blocks_from_form(form)
        if posted:
            try:
                blocks = validate_script(posted)
            except ScriptValidationError as exc:
                return _redirect(f"/episode/{episode_id}", error=str(exc))
            try:
                stored = validate_script(ep.get("script") or [])
            except ScriptValidationError:
                stored = ep.get("script")
            if blocks != stored:
                _save_script(sb, episode_id, blocks)
                edited = True

    return await _apply_decision(sb, ep, episode_id, gate, decision, note, edited)


@app.get("/api/status")
def api_status(sb=Depends(get_sb)):
    """Live status feed polled by the frontend (5s): status + generation
    progress (done vs expected job slots) per episode."""
    episodes = []
    for e in list_episodes(sb):
        script = e.get("script") or []
        talking = bool(script) and all(b.get("speaker") for b in script)
        expected = len(script) * 2 + 1 + (0 if talking else 1)
        episodes.append({
            "id": e["id"],
            "status": e["status"],
            "done": len(e.get("higgsfield_jobs") or {}),
            "expected": expected,
        })
    return {"episodes": episodes}


async def _apply_decision(sb, ep, episode_id, gate, decision, note, edited):
    try:
        if decision == "reject":
            record_approval(sb, episode_id, gate, "rejected", note=note)
            set_status(sb, episode_id, "rejected", rejection_note=note)
            return _redirect("/", msg=f"Rejected: {ep['title']}")
        if decision == "backlog":
            record_approval(sb, episode_id, gate, "rejected", note=note)
            set_status(sb, episode_id, "backlog", rejection_note=note)
            return _redirect("/", msg=f"Backlogged: {ep['title']}")
        if gate == "video":
            record_approval(sb, episode_id, gate, "approved", note=note)
            set_status(sb, episode_id, "video_approved")
            return _redirect("/", msg=f"Video approved: {ep['title']}")

        # Script approve: number it, record, promote, then hand off to Airflow.
        ep_number = ep.get("ep_number")
        if ep_number is None:
            ep_number = next_ep_number(sb)
        record_approval(
            sb, episode_id, gate, "edited_then_approved" if edited else "approved", note=note
        )
        set_status(sb, episode_id, "script_approved", ep_number=ep_number)
    except IllegalTransition as exc:
        return _redirect(f"/episode/{episode_id}", error=str(exc))

    return _trigger_production(episode_id, ep["title"])


@app.post("/episode/{episode_id}/trigger")
def retry_trigger(episode_id: str, sb=Depends(get_sb)):
    """Retry a failed hand-off. Safe to repeat: verify_approved skips non-approved episodes."""
    ep = get_episode(sb, episode_id)
    if not ep:
        raise HTTPException(status_code=404, detail="episode not found")
    if ep["status"] not in TRIGGERABLE_STATUSES:
        return _redirect(
            f"/episode/{episode_id}",
            error=f"nothing to trigger: episode is {ep['status']}",
        )
    return _trigger_production(episode_id, ep["title"])


def _trigger_production(episode_id: str, title: str) -> RedirectResponse:
    try:
        trigger_dag_run("video_production", {"episode_id": episode_id})
    except AirflowTriggerError as exc:
        return _redirect(
            f"/episode/{episode_id}",
            error=f"Script approved, but the Airflow trigger failed: {exc}",
        )
    return _redirect("/", msg=f"Script approved, generating: {title}")


@app.get("/history")
def history(request: Request, sb=Depends(get_sb)):
    episodes = list_episodes(sb)
    episodes.sort(key=lambda e: e.get("created_at") or "", reverse=True)
    runs = sb.table("cs_runs").select("*").order("started_at", desc=True).execute().data or []
    return templates.TemplateResponse(
        request, "history.html", {"episodes": episodes, "runs": runs}
    )
