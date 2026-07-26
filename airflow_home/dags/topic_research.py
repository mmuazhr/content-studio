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
