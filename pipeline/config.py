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
