"""Live test E: tool calling. The model must call our tool, we execute it in Python, and the model must use the result.

Usage (from backend/):  python scripts/test_tool_calling.py [--model ID | --all-models]
"""

import json
import sys

from _harness import Run, Skip, parse_models, require_key
from app.services.calculations import room_rent_proportionate_deduction

TOOL = {"type": "function", "function": {
    "name": "room_rent_proportionate_deduction",
    "description": "Compute the proportionate deduction applied to associated charges when the room taken "
                   "costs more per day than the policy's room-rent limit. Returns ratio, payable and deduction in INR.",
    "parameters": {"type": "object", "additionalProperties": False,
                   "required": ["eligible_room_rent_per_day", "actual_room_rent_per_day", "associated_charges"],
                   "properties": {"eligible_room_rent_per_day": {"type": "number"},
                                  "actual_room_rent_per_day": {"type": "number"},
                                  "associated_charges": {"type": "number"}}}}}

PROMPT = ("The policy's room-rent limit is Rs 5,000 per day. The patient stayed in a Rs 6,500 per day room. "
          "Associated charges subject to proportionate deduction total Rs 75,000. "
          "Use the tool to compute the deduction, then state the deduction amount in rupees.")
EXPECTED = {"eligible_room_rent_per_day": 5000, "actual_room_rent_per_day": 6500, "associated_charges": 75000}


def main() -> int:
    models = parse_models(__doc__)
    client = require_key()
    ok = True

    for model in models:
        run = Run("test_tool_calling", model)
        state = {}

        def call():
            messages = [{"role": "user", "content": PROMPT}]
            r = client.chat(messages, model=model, tools=[TOOL], tool_choice="auto", max_tokens=4096)
            if not r.tool_calls:
                return False, f"no tool call; finish={r.finish_reason} text={r.text[:120]!r}", r
            tc = r.tool_calls[0]
            state.update(messages=messages + [r.message], call=tc)
            args_ok = tc.name == TOOL["function"]["name"] and tc.arguments is not None and all(
                float(tc.arguments.get(k, -1)) == v for k, v in EXPECTED.items())
            return args_ok, f"finish={r.finish_reason} call={tc.name}({tc.raw_arguments})", r

        def use_result():
            if "call" not in state or state["call"].arguments is None:
                raise Skip("no usable tool call from E1")
            tc = state["call"]
            out = room_rent_proportionate_deduction(**tc.arguments)  # executed by our harness, not the model
            messages = state["messages"] + [{"role": "tool", "tool_call_id": tc.id,
                                             "content": json.dumps({k: str(v) for k, v in out.items()})}]
            r = client.chat(messages, model=model, tools=[TOOL], max_tokens=4096)
            want = f"{out['deduction']:,.2f}"
            used = want in r.text or want.replace(",", "") in r.text
            return used, f"python deduction={want}; final={r.text[:200]!r}", r

        run.check("E1 model returns a tool call with correct arguments", call)
        run.check("E2 model uses the Python tool result in its answer", use_result)
        ok &= run.save()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
