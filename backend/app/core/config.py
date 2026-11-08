from pathlib import Path
import re
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    # Real environment variables win over .env files; backend/.env wins over the repo-root .env.
    model_config = SettingsConfigDict(env_file=(REPO_DIR / ".env", BACKEND_DIR / ".env"), extra="ignore",
                                     hide_input_in_errors=True)

    database_url: str = f"sqlite:///{(BACKEND_DIR / 'clavion.db').as_posix()}"
    cors_origins: str = "http://localhost:5173"
    log_level: str = "INFO"
    auth_enabled: bool = False
    auth_password_hash: SecretStr = SecretStr("")
    auth_session_seconds: int = Field(default=28_800, ge=300, le=86_400)
    auth_cookie_secure: bool = True
    auth_cookie_samesite: Literal["lax", "none"] = "lax"

    @property
    def allowed_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @model_validator(mode="after")
    def validate_security(self):
        for origin in self.allowed_origins:
            parsed = urlsplit(origin)
            if (parsed.scheme not in ("http", "https") or not parsed.hostname or "*" in origin
                    or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment):
                raise ValueError("CORS_ORIGINS must contain explicit HTTP(S) origins without paths")
        if self.auth_enabled:
            if not re.fullmatch(r"pbkdf2_sha256\$600000\$[0-9a-f]{32}\$[0-9a-f]{64}",
                                self.auth_password_hash.get_secret_value()):
                raise ValueError("AUTH_PASSWORD_HASH must be generated with python -m app.password")
            if not self.allowed_origins:
                raise ValueError("authentication requires explicit CORS_ORIGINS")
            if self.auth_cookie_samesite == "none" and not self.auth_cookie_secure:
                raise ValueError("SameSite=None requires secure cookies")
            if any(urlsplit(o).scheme != "https" for o in self.allowed_origins):
                if self.auth_cookie_secure or any(urlsplit(o).hostname not in ("localhost", "127.0.0.1", "::1")
                                                  for o in self.allowed_origins):
                    raise ValueError("HTTP origins are allowed only for local testing with secure cookies disabled")
            if not self.auth_cookie_secure and any(urlsplit(o).hostname not in ("localhost", "127.0.0.1", "::1")
                                                   for o in self.allowed_origins):
                raise ValueError("insecure cookies are allowed only for loopback frontend origins")
        return self


settings = Settings()
