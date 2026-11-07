# Clavion — critical product audit and plan (November 2026)

This is the review that shaped this version: what was wrong, what was prioritised, what was built, and what is
still weak. It is deliberately critical.

## 1. Where the product stood

The previous version had a sound skeleton: local PDF/OCR extraction, deterministic parsers, a Decimal calculation
module, a supported / contestable / unverified classification, and a clean Apple-inspired UI. But a careful user
would quickly have found problems:

| # | Weakness | Impact |
|---|---|---|
| 1 | **Room-rent excess averaged mixed room rates.** 2 days at Rs 3,000 + 2 at Rs 7,000 against a Rs 5,000 limit averaged to Rs 5,000 and reported **no excess**; the correct figure is Rs 4,000. | Wrong money. Highest priority. |
| 2 | No provenance. A value on the review screen gave no hint of where it came from or whether it was guessed. | Users could not verify extraction, so could not trust the audit. |
| 3 | Findings explained the *what* but not the *why*: no rule identity, no conditions, no "what would change this", no next step. | Not explainable; not usable in an appeal. |
| 4 | Proportionate deductions above the recalculation were just "contestable", with no idea where the insurer's figure came from. | The most common real dispute had the weakest explanation. |
| 5 | No policy-exclusion rule; exclusions were classified as "unspecified". | Missed a common deduction type. |
| 6 | No cross-document checks (claimed vs bill, duplicates, length of stay, patient/policy mismatch, paid vs approved). | Conflicting documents passed silently. |
| 7 | The appeal letter was one block of text mixing quoted facts, calculations and persuasive wording. | Users could not tell which sentences were verified. |
| 8 | Upload validation trusted the extension; malformed PDFs could raise unhandled errors; no pixel limit on images; the same file could be uploaded as two documents. | Reliability and security gaps. |
| 9 | No way to delete a case; no record of who changed what. | Sensitive data could not be removed; corrections were untraceable. |
| 10 | Parsers missed common Indian formats: "Rs 1,500/-", "Rs 2500", per-head table letters, page totals mistaken for grand totals, multi-page bills. | Extraction failures on realistic documents. |
| 11 | README and `.env.example` still described a BharatCode/LLM integration the product no longer uses. | Misleading documentation. |

## 2. Priorities

Correctness first, then explainability, then usability. Nothing visual until the numbers were right.

1. Fix the money bugs (1) and add regression tests with hand-computed values.
2. Provenance for every extracted field (2, 10).
3. An explicit rules engine with rule IDs, conditions and traces (3, 4, 5).
4. Consistency checks that report *not checked* rather than passing when inputs are missing (6).
5. A statement-level appeal editor with typed statements (7).
6. Hardening of uploads, deletion and the audit trail (8, 9).
7. UI that exposes all of the above without a redesign.
8. Tests for every rule, parser path and security behaviour; documentation (11).

## 3. What was deliberately not built

| Idea | Why not |
|---|---|
| Any AI or LLM extraction or reasoning | Strict requirement: no external or paid AI, and no "fake AI". Every conclusion must trace to a rule. |
| "Likelihood of success" score | There is no data to calibrate it. A number would be invented. |
| Regulatory citations (IRDAI circulars, ombudsman rules) | Clavion cannot verify that a quoted regulation is current and applies to the policy. Quoting it wrongly would be an unsupported legal claim. |
| Auto-classifying bill lines into "associated charges" with fuzzy ML | Category comes from transparent keyword rules and is shown and editable. |
| Generic dashboard charts | Replaced the breakdown chart with a reconciliation that ties every rupee to a deduction. |
| Accounts / multi-user auth | Out of scope for a local-first tool; documented that it must not be run as a shared server. |
| Encryption at rest | SQLite with `secure_delete`; real at-rest encryption needs key management the product cannot do properly yet. |

## 4. Remaining limitations

- **Parsers are pattern-based.** They handle the layouts in the synthetic suite and common Indian variants, but a
  sufficiently unusual bill or letter will extract partially. The review screen marks what was missed; it does not
  fix it.
- **No real-document evaluation.** All test documents are synthetic. Accuracy on real insurer letters is unmeasured.
- **Category assignment is keyword-based.** A line like "Medicines and consumables" gets one category. The
  proportionate rule depends on these categories; users should check them.
- **Proportionate deduction with more than one room rate** is left as *needs clarification* — the policy wording
  rarely says which rate applies.
- **Room-category limits** ("single private room") cannot be converted to a rupee limit without the hospital's
  tariff.
- **Conditional co-pay** (age, zone, network hospital) is not evaluated; the finding says so.
- **OCR** of poor scans can misread digits. Low confidence is reported, but a confident misread is possible.
- Amounts in server-generated text use international digit grouping (130,940.50), while the UI uses Indian grouping
  (1,30,940.50).
