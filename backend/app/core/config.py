from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    # Real environment variables win over .env files; backend/.env wins over the repo-root .env.
    model_config = SettingsConfigDict(env_file=(REPO_DIR / ".env", BACKEND_DIR / ".env"), extra="ignore")

    database_url: str = f"sqlite:///{(BACKEND_DIR / 'clavion.db').as_posix()}"
    cors_origins: str = "http://localhost:5173"
    log_level: str = "INFO"


settings = Settings()
