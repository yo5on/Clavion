"""BharatCode client. The API is OpenAI-compatible (see BharatCode.txt), so we use the official SDK."""

import logging

import httpx
import truststore
from openai import OpenAI

from .config import settings

# Use the OS certificate store: some Windows/corporate networks intercept TLS and certifi rejects it.
truststore.inject_into_ssl()

log = logging.getLogger("clavion.llm")


class LLMNotConfigured(RuntimeError):
    pass


def get_client() -> OpenAI:
    if not settings.llm_configured:
        raise LLMNotConfigured("BHARATCODE_API_KEY is not set")
    return OpenAI(
        api_key=settings.bharatcode_api_key,
        base_url=settings.bharatcode_base_url,
        timeout=settings.llm_timeout_seconds,
        max_retries=3,  # the API returns 503 when busy; the SDK retries 5xx with backoff
    )


def list_models() -> list[dict]:
    """GET /models. Public endpoint; sends the key when present so access tiers are reflected."""
    headers = {"Authorization": f"Bearer {settings.bharatcode_api_key}"} if settings.llm_configured else {}
    r = httpx.get(f"{settings.bharatcode_base_url}/models", headers=headers, timeout=20)
    r.raise_for_status()
    return r.json().get("data", [])


def ping() -> str:
    """Smallest live inference call, used by the LLM health check."""
    resp = get_client().chat.completions.create(
        model=settings.bharatcode_model,
        messages=[{"role": "user", "content": "Reply with exactly: OK"}],
        max_tokens=512,  # reasoning tokens count against this budget
    )
    log.info("ping ok model=%s usage=%s", settings.bharatcode_model, resp.usage)
    return (resp.choices[0].message.content or "").strip()
