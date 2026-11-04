"""BharatCode feasibility probe. Verifies, against the live API, the capabilities Clavion depends on.

Usage (from backend/):  python scripts/check_bharatcode.py [--model qwen-3.8-27b]
Needs BHARATCODE_API_KEY in backend/.env or the environment. Prints PASS/FAIL per capability; never prints the key.
"""

import argparse
import base64
import json
import struct
import sys
import time
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import llm  # noqa: E402  (also injects the OS trust store)
from app.config import settings  # noqa: E402


def solid_png(rgb: tuple[int, int, int], size: int = 32) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    raw = b"".join(b"\x00" + bytes(rgb) * size for _ in range(size))
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def run(name, fn):
    t = time.perf_counter()
    try:
        ok, detail = fn()
    except Exception as e:
        ok, detail = False, f"{type(e).__name__}: {str(e)[:200]}"
    print(f"[{'PASS' if ok else 'FAIL'}] {name} ({time.perf_counter() - t:.1f}s) {detail}")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=settings.bharatcode_model)
    model = ap.parse_args().model
    try:
        client = llm.get_client()
    except llm.LLMNotConfigured as e:
        print(f"[SKIP] {e}. Add it to backend/.env and rerun.")
        return 2
    print(f"base_url={settings.bharatcode_base_url} model={model}")

    def text():
        r = client.chat.completions.create(model=model, max_tokens=512,
                                           messages=[{"role": "user", "content": "Reply with exactly: OK"}])
        out = (r.choices[0].message.content or "").strip()
        return "OK" in out, f"reply={out[:40]!r} usage={r.usage.total_tokens if r.usage else '?'}"

    def json_mode():
        r = client.chat.completions.create(
            model=model, max_tokens=1024, response_format={"type": "json_object"},
            messages=[{"role": "user", "content": 'Return JSON {"item": "Room rent", "amount": 4500} and nothing else.'}])
        data = json.loads(r.choices[0].message.content or "")
        return data.get("amount") == 4500, f"parsed={data}"

    def image():
        url = "data:image/png;base64," + base64.b64encode(solid_png((220, 20, 20))).decode()
        r = client.chat.completions.create(model=model, max_tokens=512, messages=[{"role": "user", "content": [
            {"type": "text", "text": "What single colour fills this image? Answer with one word."},
            {"type": "image_url", "image_url": {"url": url}}]}])
        out = (r.choices[0].message.content or "").strip().lower()
        return "red" in out, f"reply={out[:40]!r}"

    def tools():
        tool = {"type": "function", "function": {
            "name": "calculate_proportionate_deduction",
            "description": "Compute room-rent proportionate deduction.",
            "parameters": {"type": "object", "required": ["eligible_room_rent", "actual_room_rent"], "properties": {
                "eligible_room_rent": {"type": "number"}, "actual_room_rent": {"type": "number"}}}}}
        r = client.chat.completions.create(model=model, max_tokens=1024, tools=[tool], tool_choice="auto", messages=[
            {"role": "user", "content": "Policy allows room rent of 5000/day; patient stayed in a 8000/day room. "
                                        "Use the tool to compute the proportionate deduction."}])
        calls = r.choices[0].message.tool_calls or []
        if not calls:
            return False, "model did not call the tool"
        args = json.loads(calls[0].function.arguments)
        return calls[0].function.name == tool["function"]["name"], f"args={args}"

    results = [run("text completion", text), run("JSON mode", json_mode),
               run("image input", image), run("tool calling", tools)]
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
