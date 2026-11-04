from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    bharatcode_api_key: str = ""
    bharatcode_base_url: str = "https://bharatcode.ai/api/model/v1"
    bharatcode_model: str = "qwen-3.8-27b"
    llm_timeout_seconds: float = 120.0

    database_url: str = f"sqlite:///{(BACKEND_DIR / 'clavion.db').as_posix()}"
    cors_origins: str = "http://localhost:5173"
    log_level: str = "INFO"

    @property
    def llm_configured(self) -> bool:
        return bool(self.bharatcode_api_key)


settings = Settings()
