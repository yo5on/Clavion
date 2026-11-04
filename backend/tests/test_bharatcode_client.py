import httpx
import pytest
from pydantic import BaseModel, SecretStr

from app.core.config import Settings
from app.services.bharatcode_client import BharatCodeClient, BharatCodeError, extract_json

KEY = "sk-test-SECRET-123"


def _client(handler) -> BharatCodeClient:
    c = BharatCodeClient(Settings(bharatcode_api_key=SecretStr(KEY), bharatcode_max_retries=0))
    c._sdk = c._sdk.with_options(http_client=httpx.Client(transport=httpx.MockTransport(handler)), max_retries=0)
    return c


def _reply(content=None, tool_calls=None, finish="stop"):
    msg = {"role": "assistant", "content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return httpx.Response(200, headers={"x-request-id": "req-1"}, json={
        "id": "x", "object": "chat.completion", "created": 0, "model": "m",
        "choices": [{"index": 0, "finish_reason": finish, "message": msg}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}})


def test_sends_bearer_auth_and_parses_response():
    seen = {}

    def handler(req: httpx.Request):
        seen["auth"] = req.headers["authorization"]
        seen["url"] = str(req.url)
        return _reply("OK")

    r = _client(handler).chat([{"role": "user", "content": "hi"}])
    assert seen["auth"] == f"Bearer {KEY}" and seen["url"].endswith("/api/model/v1/chat/completions")
    assert (r.text, r.finish_reason, r.usage["total_tokens"], r.request_id) == ("OK", "stop", 5, "req-1")


def test_parses_tool_calls():
    tc = [{"id": "c1", "type": "function", "function": {"name": "f", "arguments": '{"a": 1}'}}]
    r = _client(lambda req: _reply(None, tc, "tool_calls")).chat([{"role": "user", "content": "x"}])
    assert r.tool_calls[0].name == "f" and r.tool_calls[0].arguments == {"a": 1}


@pytest.mark.parametrize("status,kind", [(401, "invalid_credentials"), (403, "access_denied"),
                                         (402, "access_denied"), (400, "bad_request"), (503, "unavailable")])
def test_classifies_http_errors_and_redacts_key(status, kind):
    def handler(req):
        return httpx.Response(status, headers={"x-request-id": "req-9"}, json={"error": f"bad key {KEY}"})

    with pytest.raises(BharatCodeError) as ei:
        _client(handler).chat([{"role": "user", "content": "x"}])
    assert ei.value.kind == kind and ei.value.status == status and ei.value.request_id == "req-9"
    assert KEY not in str(ei.value)


def test_refuses_to_call_without_key():
    with pytest.raises(BharatCodeError) as ei:
        BharatCodeClient(Settings(bharatcode_api_key=SecretStr(""))).chat([{"role": "user", "content": "x"}])
    assert ei.value.kind == "not_configured"


def test_retries_transient_503_then_succeeds():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(503, json={"error": "busy"}) if len(calls) == 1 else _reply("OK")

    c = _client(handler)
    c._sdk = c._sdk.with_options(max_retries=2)
    assert c.chat([{"role": "user", "content": "x"}]).text == "OK" and len(calls) == 2


class Item(BaseModel):
    name: str
    amount: float


def test_chat_json_validates_and_rejects():
    ok = _client(lambda req: _reply('```json\n{"name": "Room", "amount": 4500}\n```'))
    item, _ = ok.chat_json([{"role": "user", "content": "x"}], Item)
    assert item.amount == 4500
    bad = _client(lambda req: _reply('{"name": "Room"}'))
    with pytest.raises(BharatCodeError) as ei:
        bad.chat_json([{"role": "user", "content": "x"}], Item)
    assert ei.value.kind == "invalid_output"


def test_extract_json_tolerates_prose():
    assert extract_json('Sure! {"a": {"b": 1}} hope that helps') == '{"a": {"b": 1}}'
    with pytest.raises(ValueError):
        extract_json("no json here")


def test_timeout_is_classified():
    def handler(req):
        raise httpx.ReadTimeout("slow", request=req)

    with pytest.raises(BharatCodeError) as ei:
        _client(handler).chat([{"role": "user", "content": "x"}])
    assert ei.value.kind == "timeout"


def test_exposes_bharatcode_error_code():
    body = {"error": {"message": "Coding and API use need BharatCode Lite", "type": "subscription_required",
                      "code": "subscription_required"}}
    with pytest.raises(BharatCodeError) as ei:
        _client(lambda req: httpx.Response(402, json=body)).chat([{"role": "user", "content": "x"}])
    assert (ei.value.kind, ei.value.code) == ("access_denied", "subscription_required")
