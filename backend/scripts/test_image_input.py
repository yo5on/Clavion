"""Live test D: image input. A colour sanity check, then extraction from a SYNTHETIC hospital bill image.

Usage (from backend/):  python scripts/test_image_input.py [--model ID | --all-models]
"""

import base64
import sys
import tempfile
from pathlib import Path

from PIL import Image

from _harness import Run, parse_models, require_key
from app.schemas.bill import EXTRACTION_INSTRUCTIONS, HospitalBill
import synthetic_bill


def data_url(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


def main() -> int:
    models = parse_models(__doc__)
    client = require_key()
    tmp = Path(tempfile.mkdtemp(prefix="clavion-img-"))
    red = tmp / "red.png"
    Image.new("RGB", (64, 64), (220, 20, 20)).save(red)
    bill_png = synthetic_bill.render_png(tmp / "synthetic_bill.png")
    print(f"synthetic bill image: {bill_png} ({bill_png.stat().st_size // 1024} KB)")
    ok = True

    for model in models:
        run = Run("test_image_input", model)

        def colour():
            r = client.chat([{"role": "user", "content": [
                {"type": "text", "text": "What single colour fills this image? Answer with one word."},
                {"type": "image_url", "image_url": {"url": data_url(red)}}]}], model=model, max_tokens=2048)
            return "red" in r.text.lower(), f"reply={r.text[:40]!r}", r

        def bill():
            b, r = client.chat_json([{"role": "system", "content": EXTRACTION_INSTRUCTIONS}, {"role": "user", "content": [
                {"type": "text", "text": "Extract this hospital bill."},
                {"type": "image_url", "image_url": {"url": data_url(bill_png)}}]}],
                HospitalBill, model=model, max_tokens=8192)
            issues, diffs = b.arithmetic_issues(), synthetic_bill.compare(b)
            detail = (f"{len(b.line_items)} items, total={b.total_amount}; python arithmetic issues={issues}; "
                      f"ground-truth diffs={diffs}")
            return not issues and not diffs, detail, r

        run.check("D1 image input: colour sanity check", colour)
        run.check("D2 image input: synthetic bill extraction + Python validation", bill)
        ok &= run.save()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
