from pydantic import BaseModel
import os

class Settings(BaseModel):
    database_url: str = os.environ.get("DATABASE_URL", "postgresql://baby:change_me@db:5432/babylog")
    api_key: str = os.environ.get("API_KEY", "change_me_api")
    app_name: str = "BabyLog API"
    tz: str = "UTC"
    # NEW: feature flag to allow admin reset endpoint
    reset_enabled: bool = os.environ.get("RESET_ENABLED", "0") == "1"

settings = Settings()
