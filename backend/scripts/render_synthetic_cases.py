"""Write the six SYNTHETIC test cases as uploadable files, for manual demos of the upload workflow.

    cd backend && python -m scripts.render_synthetic_cases

Output: backend/scripts/results/synthetic_cases/<case>/{bill,policy,settlement}.pdf (case 6: bill.png is a degraded
scan and there is no policy). Every file is marked SYNTHETIC TEST DOCUMENT; none is a real claim.
"""

from pathlib import Path

from app.demo.fixtures import render_pdf
from tests.synthetic_cases import CASES
from tests.test_synthetic_cases import degraded_scan

OUT = Path(__file__).resolve().parent / "results" / "synthetic_cases"

if __name__ == "__main__":
    for name, case in CASES.items():
        folder = OUT / name
        folder.mkdir(parents=True, exist_ok=True)
        for doc_type in ("bill", "policy", "settlement"):
            text = case[doc_type]
            if text is None:
                continue
            if name.startswith("6") and doc_type == "bill":
                (folder / "bill.png").write_bytes(degraded_scan(text))
            else:
                (folder / f"{doc_type}.pdf").write_bytes(render_pdf(text))
        print(f"{case['title']}: {folder}")
