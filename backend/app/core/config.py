from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = BACKEND_DIR.parent

OFFICIAL_BASE_URL = "https://bharatcode.ai/api/model/v1"  # https://bharatcode.ai/build


class Settings(BaseSettings):
    # Real environment variables win over .env files; backend/.env wins over the repo-root .env.
    model_config = SettingsConfigDict(env_file=(REPO_DIR / ".env", BACKEND_DIR / ".env"), extra="ignore")

    bharatcode_api_key: SecretStr = SecretStr("")  # SecretStr keeps it out of repr/logs/serialisation
    bharatcode_base_url: str = OFFICIAL_BASE_URL
    bharatcode_model: str = "qwen-3.8-27b"
    bharatcode_connect_timeout: float = 10.0
    bharatcode_request_timeout: float = 180.0  # requests may queue on shared capacity
    bharatcode_max_retries: int = 2

    database_url: str = f"sqlite:///{(BACKEND_DIR / 'clavion.db').as_posix()}"
    cors_origins: str = "http://localhost:5173"
    log_level: str = "INFO"

    @field_validator("bharatcode_base_url", mode="before")
    @classmethod
    def _default_base_url(cls, v: str) -> str:
        return (v or OFFICIAL_BASE_URL).rstrip("/")

    @property
    def llm_configured(self) -> bool:
        return bool(self.bharatcode_api_key.get_secret_value())


settings = Settings()
