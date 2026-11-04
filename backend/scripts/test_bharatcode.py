"""Live tests A (auth), B (basic inference), C (structured JSON) and the text bill-extraction experiment.

Usage (from backend/):  python scripts/test_bharatcode.py [--model ID | --all-models]
"""

import sys

from pydantic import BaseModel, SecretStr

from _harness import Run, parse_models, require_key
from app.core.config import settings
from app.schemas.bill import EXTRACTION_INSTRUCTIONS, HospitalBill
from app.services.bharatcode_client import BharatCodeClient, BharatCodeError
import synthetic_bill


class DeductionNote(BaseModel):
    item: str
    amount: float
    reason: str
    contestable: bool


JSON_PROMPT = ('A settlement letter says: "Non-medical consumables (gloves, masks) Rs 1,500 deducted as not payable." '
               'Return a JSON object with keys item (string), amount (number), reason (string), '
               'contestable (boolean, false if the reason is a standard policy exclusion). Return only JSON.')


def main() -> int:
    models = parse_models(__doc__)
    client = require_key()
    ok = True

    # A2 is model-independent: what does the API return for a bad key? Run once.
    run = Run("test_bharatcode", "invalid-key-probe")

    def bad_key():
        bogus = BharatCodeClient(settings.model_copy(update={"bharatcode_api_key": SecretStr("clavion-invalid-key-test"),
                                                             "bharatcode_max_retries": 0}))
        try:
            bogus.chat([{"role": "user", "content": "hi"}], max_tokens=16)
        except BharatCodeError as e:
            return e.kind == "invalid_credentials", f"API returned kind={e.kind} HTTP {e.status}: {e}", None
        return False, "API ACCEPTED an invalid key", None

    run.check("A2 invalid key is rejected distinctly", bad_key)
    run.save()

    for model in models:
        run = Run("test_bharatcode", model)

        def auth():
            r = client.chat([{"role": "user", "content": "Reply with exactly: OK"}], model=model, max_tokens=1024)
            return True, f"key accepted for {model}; reply={r.text[:30]!r}", r

        def basic():
            r = client.chat([{"role": "user", "content":
                              "In two sentences, explain what a room-rent sub-limit is in Indian health insurance."}],
                            model=model, max_tokens=4096)
            good = r.finish_reason == "stop" and len(r.text) > 40 and "room" in r.text.lower()
            return good, f"finish={r.finish_reason} reply={r.text[:160]!r}", r

        def json_check(json_mode: bool):
            def fn():
                note, r = client.chat_json([{"role": "user", "content": JSON_PROMPT}], DeductionNote,
                                           json_mode=json_mode, model=model, max_tokens=4096)
                good = note.amount == 1500 and "glove" in note.item.lower()
                return good, f"validated={note.model_dump()}", r
            return fn

        def extract_text():
            bill, r = client.chat_json([{"role": "system", "content": EXTRACTION_INSTRUCTIONS},
                                        {"role": "user", "content": synthetic_bill.as_text()}],
                                       HospitalBill, model=model, max_tokens=8192)
            issues, diffs = bill.arithmetic_issues(), synthetic_bill.compare(bill)
            detail = (f"{len(bill.line_items)} items, total={bill.total_amount}; python arithmetic issues={issues}; "
                      f"ground-truth diffs={diffs}")
            return not issues and not diffs, detail, r

        run.check("A  authentication", auth)
        run.check("B  basic inference", basic)
        run.check("C1 JSON with response_format=json_object + Pydantic", json_check(True))
        run.check("C2 JSON via prompt only + Pydantic", json_check(False))
        run.check("F  synthetic bill extraction (text) + Python validation", extract_text)
        ok &= run.save()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
