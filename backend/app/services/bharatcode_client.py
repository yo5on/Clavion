"""BharatCode client.

BharatCode documents an OpenAI-compatible API (https://bharatcode.ai/build): Bearer auth, POST /chat/completions,
GET /models. We use the official `openai` SDK pointed at that base URL; it handles Bearer auth and retries
transient failures (connection errors, 408/409/429/5xx) with exponential backoff, up to `max_retries`.
"""

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, TypeVar

import httpx
import openai
import truststore
from pydantic import BaseModel, ValidationError

from ..core.config import Settings, settings

# Use the OS certificate store: some Windows/corporate networks intercept TLS and certifi rejects it.
truststore.inject_into_ssl()

log = logging.getLogger("clavion.bharatcode")
T = TypeVar("T", bound=BaseModel)


class BharatCodeError(RuntimeError):
    """kind is one of: not_configured, invalid_credentials, access_denied, bad_request, not_found,
    rate_limited, unavailable, timeout, connection, http_error, invalid_output."""

    def __init__(self, kind: str, message: str, status: int | None = None, request_id: str | None = None,
                 code: str | None = None):
        super().__init__(f"[{kind}] {message}")
        # code is BharatCode's own error.code, e.g. "invalid_credentials" (401) or "subscription_required" (402)
        self.kind, self.status, self.request_id, self.code = kind, status, request_id, code


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict | None  # None when the model sent arguments that are not valid JSON
    raw_arguments: str


@dataclass
class ChatResult:
    text: str
    finish_reason: str | None
    tool_calls: list[ToolCall]
    usage: dict[str, Any]
    latency_s: float
    model: str
    request_id: str | None
    message: dict = field(repr=False)  # assistant message, ready to append to a follow-up `messages` list


_STATUS_KINDS = {400: "bad_request", 401: "invalid_credentials", 402: "access_denied", 403: "access_denied",
                 404: "not_found", 429: "rate_limited"}


def _redact(text: str, secret: str) -> str:
    return text.replace(secret, "***") if secret else text


class BharatCodeClient:
    def __init__(self, cfg: Settings = settings):
        self.cfg = cfg
        self._key = cfg.bharatcode_api_key.get_secret_value()
        self._sdk = openai.OpenAI(
            api_key=self._key or "unset",  # SDK requires a value; we refuse to call without a real key below
            base_url=cfg.bharatcode_base_url,
            timeout=httpx.Timeout(cfg.bharatcode_request_timeout, connect=cfg.bharatcode_connect_timeout),
            max_retries=cfg.bharatcode_max_retries,
        )

    def _translate(self, e: Exception) -> BharatCodeError:
        if isinstance(e, openai.APITimeoutError):
            return BharatCodeError("timeout", "request timed out")
        if isinstance(e, openai.APIConnectionError):
            return BharatCodeError("connection", f"could not reach {self.cfg.bharatcode_base_url}")
        if isinstance(e, openai.APIStatusError):
            status = e.status_code
            kind = _STATUS_KINDS.get(status, "unavailable" if status >= 500 else "http_error")
            body = _redact(e.response.text[:500], self._key)
            code = e.body.get("code") if isinstance(e.body, dict) else None  # SDK unwraps {"error": {...}}
            return BharatCodeError(kind, f"HTTP {status}: {body}", status, e.response.headers.get("x-request-id"), code)
        return BharatCodeError("http_error", _redact(f"{type(e).__name__}: {e}", self._key))

    def chat(self, messages: list[dict], *, model: str | None = None, max_tokens: int = 4096,
             tools: list[dict] | None = None, tool_choice: str | dict | None = None,
             response_format: dict | None = None, temperature: float | None = None) -> ChatResult:
        if not self._key:
            raise BharatCodeError("not_configured", "BHARATCODE_API_KEY is not set")
        model = model or self.cfg.bharatcode_model
        kwargs: dict[str, Any] = {"model": model, "messages": messages, "max_tokens": max_tokens}
        for k, v in {"tools": tools, "tool_choice": tool_choice, "response_format": response_format,
                     "temperature": temperature}.items():
            if v is not None:
                kwargs[k] = v

        t0 = time.perf_counter()
        try:
            raw = self._sdk.chat.completions.with_raw_response.create(**kwargs)
            resp = raw.parse()
        except Exception as e:
            err = self._translate(e)
            log.warning("chat failed model=%s kind=%s code=%s status=%s request_id=%s",
                        model, err.kind, err.code, err.status, err.request_id)
            raise err from None
        latency = time.perf_counter() - t0

        if not resp.choices:
            raise BharatCodeError("invalid_output", "response has no choices", request_id=raw.headers.get("x-request-id"))
        choice = resp.choices[0]
        msg = choice.message
        calls = []
        for c in msg.tool_calls or []:
            try:
                args = json.loads(c.function.arguments or "{}")
            except json.JSONDecodeError:
                args = None
            calls.append(ToolCall(c.id, c.function.name, args, c.function.arguments or ""))
        usage = resp.usage.model_dump(exclude_none=True) if resp.usage else {}
        result = ChatResult(
            text=(msg.content or "").strip(), finish_reason=choice.finish_reason, tool_calls=calls, usage=usage,
            latency_s=round(latency, 2), model=model, request_id=raw.headers.get("x-request-id"),
            message=msg.model_dump(exclude_none=True),
        )
        log.info("chat ok model=%s finish=%s tokens=%s latency=%.2fs request_id=%s",
                 model, result.finish_reason, usage.get("total_tokens"), latency, result.request_id)
        if result.finish_reason == "length":
            log.warning("output truncated at max_tokens=%s (reasoning counts toward the budget)", max_tokens)
        return result

    def chat_json(self, messages: list[dict], schema: type[T], *, json_mode: bool = True, **kw) -> tuple[T, ChatResult]:
        """Chat expecting a JSON object matching `schema`. Raises BharatCodeError(kind='invalid_output') otherwise."""
        result = self.chat(messages, response_format={"type": "json_object"} if json_mode else None, **kw)
        try:
            return schema.model_validate_json(extract_json(result.text)), result
        except (ValidationError, ValueError) as e:
            raise BharatCodeError("invalid_output", f"{schema.__name__} validation failed: {str(e)[:400]}",
                                  request_id=result.request_id) from None

    def list_models(self) -> list[dict]:
        """GET /models. The catalog is public; the key is sent when present."""
        headers = {"Authorization": f"Bearer {self._key}"} if self._key else {}
        try:
            r = httpx.get(f"{self.cfg.bharatcode_base_url}/models", headers=headers,
                          timeout=httpx.Timeout(20, connect=self.cfg.bharatcode_connect_timeout))
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise BharatCodeError(_STATUS_KINDS.get(e.response.status_code, "http_error"),
                                  f"HTTP {e.response.status_code}", e.response.status_code) from None
        except httpx.HTTPError as e:
            raise BharatCodeError("connection", type(e).__name__) from None
        return r.json().get("data", [])

    def ping(self) -> str:
        return self.chat([{"role": "user", "content": "Reply with exactly: OK"}], max_tokens=1024).text


def extract_json(text: str) -> str:
    """Return the JSON object in a model reply, tolerating ```json fences or surrounding prose."""
    if m := re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S):
        return m.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        raise ValueError("no JSON object in reply")
    return text[start:end + 1]
