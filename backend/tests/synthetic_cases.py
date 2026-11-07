"""Six SYNTHETIC claim cases for testing Clavion's local pipeline. Not real claims: every name, number, hospital,
insurer and policy is invented, and every document carries the SYNTHETIC marker.

Each case gives the three documents as text (rendered to PDF or a degraded image by the tests), the values the
parser should extract, and the audit result worked out by hand. The hand calculations are in the comments; the
tests compare the engine against these numbers, never against its own output.
"""

from decimal import Decimal as D

POLICY_HEAD = "*** SYNTHETIC TEST DOCUMENT - NOT A REAL POLICY ***"
BILL_HEAD = "*** SYNTHETIC TEST DOCUMENT - NOT A REAL BILL ***"
LETTER_HEAD = "*** SYNTHETIC TEST DOCUMENT - NOT A REAL SETTLEMENT LETTER ***"


def bill(hospital, number, patient, lines, total):
    rows = [f"{i:>2}. {d:<40} {q:>2} x {D(r):>10,.2f} = {D(a):>11,.2f}" for i, (d, q, r, a) in enumerate(lines, 1)]
    return "\n".join([BILL_HEAD, hospital, "FINAL IN-PATIENT BILL", f"Bill No: {number}    Bill Date: 03-Sep-2026",
                      f"Patient Name: {patient}", "", *rows, "", f"    GRAND TOTAL (Rs)  {total}"])


def letter(insurer, claim_no, policy_no, patient, hospital, claimed, deductions, total, approved):
    rows = [f"{i}. {d}  Rs {a}" for i, (d, a) in enumerate(deductions, 1)]
    out = [LETTER_HEAD, insurer, "CLAIM SETTLEMENT LETTER", f"Claim No: {claim_no}", f"Policy No: {policy_no}",
           f"Patient Name: {patient}", f"Hospital: {hospital}", "", f"Amount Claimed: Rs {claimed}", "",
           "Deductions:", *rows, ""]
    if total:
        out.append(f"Total Deductions: Rs {total}")
    if approved:
        out.append(f"Amount Approved: Rs {approved}")
    return "\n".join(out)


CASES = {}

# ------------------------------------------------------------------ 1. straightforward, no significant deductions
# Masks are listed in clause 6.1 and billed at 150.00 -> deduction supported. 15,100.75 - 150.00 = 14,950.75.
CASES["1_straightforward"] = dict(
    title="SYNTHETIC 1 - Straightforward claim",
    policy=f"""{POLICY_HEAD}
Arogya Basic Cover - Policy Wording
Policy No: ABC/2026/10001
Sum Insured: Rs 3,00,000

1. Scope of Cover
Reasonable and customary hospitalisation expenses are payable.

3.1 Room Rent
Room rent is payable up to 1% of the Sum Insured per day.

6.1 Non-payable Items
The following items are not payable under this policy:
- Gloves
- Masks
- Attendant charges
""",
    bill=bill("Lotus Community Hospital", "LCH/2026/0457", "Ravi Menon", [
        ("Room rent - General ward", 3, "2500.00", "7500.00"),
        ("Doctor consultation", 3, "800.00", "2400.00"),
        ("Pharmacy", 1, "3250.75", "3250.75"),
        ("Laboratory investigations", 4, "450.00", "1800.00"),
        ("Masks", 2, "75.00", "150.00")], "15,100.75"),
    settlement=letter("Kaveri General Insurance Ltd", "KGI/CL/2026/3301", "ABC/2026/10001", "Ravi Menon",
                      "Lotus Community Hospital", "15,100.75",
                      [("Non-payable items - Masks (Clause 6.1)", "150.00")], "150.00", "14,950.75"),
    extracted=dict(bill_total=D("15100.75"), lines=5, room_limit=D("3000.00"), claimed=D("15100.75"),
                   approved=D("14950.75"), deductions=1),
    expected=dict(statuses=["supported"], supported=[D("150.00")], contestable=[D("0.00")],
                  basis=["policy_list"], total=D("150.00"), contestable_total=D("0.00"),
                  unverified_total=D("0.00"), supported_total=D("150.00"), missing=[]),
)

# ------------------------------------------------------------------ 2. room-rent proportionate deduction
# Limit: min(1% x 4,00,000, Rs 4,000) = 4,000/day. Room billed 8,000/day x 5 days.
#  1 room rent excess (8,000 - 4,000) x 5 = 20,000.00                                     supported
#  2 ratio 4,000 / 8,000 = 0.5. Clause 3.3 excludes pharmacy and diagnostics, so associated charges are
#    surgeon 60,000 + OT 25,000 + nursing 5,000 = 90,000 -> deduction 45,000.00.
#    Insurer also proportioned pharmacy 15,000 + lab 8,000: 1,13,000 x 0.5 = 56,500.00 -> 11,500.00 contestable
CASES["2_room_rent_proportionate"] = dict(
    title="SYNTHETIC 2 - Room-rent proportionate deduction",
    policy=f"""{POLICY_HEAD}
Suvidha Health Shield - Policy Wording
Policy No: SHS/2026/20002
Sum Insured: Rs 4,00,000

3.1 Room Rent
Room rent, boarding and nursing expenses are payable up to 1% of the Sum Insured per day,
subject to a maximum of Rs 4,000 per day.

3.3 Proportionate Deduction
If the Insured Person occupies a room with rent higher than the eligible room rent, the associated
medical expenses shall be payable in the same proportion as the eligible room rent bears to the actual room rent.
Proportionate deduction shall not apply to pharmacy, consumables, implants and diagnostics.
""",
    bill=bill("Meridian Surgical Hospital", "MSH/2026/7781", "Kiran Rao", [
        ("Room rent - Deluxe room", 5, "8000.00", "40000.00"),
        ("Surgeon fee - Hernia repair", 1, "60000.00", "60000.00"),
        ("Operation theatre charges", 1, "25000.00", "25000.00"),
        ("Nursing charges", 5, "1000.00", "5000.00"),
        ("Pharmacy and medicines", 1, "15000.00", "15000.00"),
        ("Laboratory investigations", 1, "8000.00", "8000.00")], "1,53,000.00"),
    settlement=letter("Narmada Health Insurance Co Ltd", "NHI/2026/88120", "SHS/2026/20002", "Kiran Rao",
                      "Meridian Surgical Hospital", "1,53,000.00",
                      [("Room rent above eligible limit (Clause 3.1)", "20,000.00"),
                       ("Proportionate deduction on associated charges (Clause 3.3)", "56,500.00")],
                      "76,500.00", "76,500.00"),
    extracted=dict(bill_total=D("153000.00"), lines=6, room_limit=D("4000.00"), claimed=D("153000.00"),
                   approved=D("76500.00"), deductions=2),
    expected=dict(statuses=["supported", "contestable"], supported=[D("20000.00"), D("45000.00")],
                  contestable=[D("0.00"), D("11500.00")], basis=["recalculated", "recalculated"],
                  total=D("76500.00"), contestable_total=D("11500.00"), unverified_total=D("0.00"),
                  supported_total=D("65000.00"), missing=[]),
)

# ------------------------------------------------------------------ 3. co-pay and sub-limit
#  1 cataract sub-limit Rs 40,000; billed 55,000 -> excess 15,000.00                        supported
#  2 co-pay 20% applies to the admissible amount: (59,000 - 15,000) x 20% = 8,800.00.
#    Insurer took 20% of the full claim, 59,000 x 20% = 11,800.00 -> 3,000.00 contestable
CASES["3_copay_sublimit"] = dict(
    title="SYNTHETIC 3 - Co-pay and sub-limit",
    policy=f"""{POLICY_HEAD}
Saral Senior Care - Policy Wording
Policy No: SCP/2026/30003
Sum Insured: Rs 3,00,000

3.1 Room Rent
Room rent is payable up to 1% of the Sum Insured per day.

4.2 Sub-limits
The following sub-limits apply per policy year:
- Cataract surgery: Rs 40,000 per eye

5.1 Co-payment
A 20% co-payment applies to every admissible claim.
""",
    bill=bill("Drishti Eye Hospital", "DEH/2026/1209", "Meena Pillai", [
        ("Cataract surgery package (left eye)", 1, "55000.00", "55000.00"),
        ("Ophthalmologist consultation", 1, "1500.00", "1500.00"),
        ("Pharmacy", 1, "2500.00", "2500.00")], "59,000.00"),
    settlement=letter("Ganga Mutual Insurance Ltd", "GMI/2026/44017", "SCP/2026/30003", "Meena Pillai",
                      "Drishti Eye Hospital", "59,000.00",
                      [("Amount above cataract sub-limit (Clause 4.2)", "15,000.00"),
                       ("Co-payment 20% (Clause 5.1)", "11,800.00")], "26,800.00", "32,200.00"),
    extracted=dict(bill_total=D("59000.00"), lines=3, room_limit=D("3000.00"), claimed=D("59000.00"),
                   approved=D("32200.00"), deductions=2, copay=D("20")),
    expected=dict(statuses=["supported", "contestable"], supported=[D("15000.00"), D("8800.00")],
                  contestable=[D("0.00"), D("3000.00")], basis=["recalculated", "recalculated"],
                  total=D("26800.00"), contestable_total=D("3000.00"), unverified_total=D("0.00"),
                  supported_total=D("23800.00"), missing=[]),
)

# ------------------------------------------------------------------ 4. non-payable items
#  1 gloves and masks 600.00: both listed in 7.1                                          supported
#  2 toiletries kit 350.00: "Toiletries" listed                                            supported
#  3 nebulizer kit 900.00: not on the list                                                 900.00 contestable
#  4 attendant food 800.00: "Food charges for attendant" listed                            supported
#  5 PPE kit 500.00: listed, but the bill has no PPE line, so the amount cannot be checked  unverified
CASES["4_non_payable"] = dict(
    title="SYNTHETIC 4 - Non-payable items",
    policy=f"""{POLICY_HEAD}
Nirmal Family Health - Policy Wording
Policy No: NPC/2026/40004
Sum Insured: Rs 2,00,000

3.1 Room Rent
Room rent is payable up to 1% of the Sum Insured per day.

7.1 Non-payable Items
The following items are not payable under this policy:
- Gloves
- Masks
- PPE kit
- Toiletries
- Food charges for attendant
""",
    bill=bill("Shanti Nursing Home", "SNH/2026/0311", "Arjun Das", [
        ("Room rent - General ward", 2, "2000.00", "4000.00"),
        ("Physician consultation", 2, "1000.00", "2000.00"),
        ("Gloves and masks", 1, "600.00", "600.00"),
        ("Toiletries kit", 1, "350.00", "350.00"),
        ("Nebulizer kit", 1, "900.00", "900.00"),
        ("Food charges for attendant", 2, "400.00", "800.00")], "8,650.00"),
    settlement=letter("Sahyadri General Insurance Ltd", "SGI/2026/50981", "NPC/2026/40004", "Arjun Das",
                      "Shanti Nursing Home", "8,650.00",
                      [("Non-payable items - Gloves and masks (Clause 7.1)", "600.00"),
                       ("Non-payable items - Toiletries kit (Clause 7.1)", "350.00"),
                       ("Non-payable items - Nebulizer kit (Clause 7.1)", "900.00"),
                       ("Non-payable items - Attendant food (Clause 7.1)", "800.00"),
                       ("Non-payable items - PPE kit (Clause 7.1)", "500.00")], "3,150.00", "5,500.00"),
    extracted=dict(bill_total=D("8650.00"), lines=6, room_limit=D("2000.00"), claimed=D("8650.00"),
                   approved=D("5500.00"), deductions=5),
    expected=dict(statuses=["supported", "supported", "contestable", "supported", "unverified"],
                  supported=[D("600.00"), D("350.00"), D("0.00"), D("800.00"), None],
                  contestable=[D("0.00"), D("0.00"), D("900.00"), D("0.00"), D("0.00")],
                  basis=["policy_list", "policy_list", "clause_absent", "policy_list", "insufficient"],
                  total=D("3150.00"), contestable_total=D("900.00"), unverified_total=D("500.00"),
                  supported_total=D("1750.00"), missing=[]),
)

# ------------------------------------------------------------------ 5. insurer cites clauses absent from the policy
#  1 administrative charges 1,200.00 "as per Clause 9.4": not on the 6.1 list, but the uploaded policy has no
#    Clause 9.4, so it may be incomplete                                                    unverified
#  2 room rent excess 1,500.00: billed 4,500/day, limit 1% x 5,00,000 = 5,000/day -> nothing deductible
#                                                                                          1,500.00 contestable
#  3 "Deduction as per Clause 8.2" 2,000.00: no reason given, clause not in policy          unverified
CASES["5_absent_clause"] = dict(
    title="SYNTHETIC 5 - Insurer cites clauses absent from the policy",
    policy=f"""{POLICY_HEAD}
Kshema Health Basic - Policy Wording
Policy No: KHB/2026/50005
Sum Insured: Rs 5,00,000

3.1 Room Rent
Room rent is payable up to 1% of the Sum Insured per day.

6.1 Non-payable Items
The following items are not payable under this policy:
- Gloves
- Masks
""",
    bill=bill("Vasant General Hospital", "VGH/2026/2290", "Farah Khan", [
        ("Room rent - Single room", 3, "4500.00", "13500.00"),
        ("Surgeon fee", 1, "30000.00", "30000.00"),
        ("Pharmacy", 1, "6500.00", "6500.00"),
        ("Administrative charges", 1, "1200.00", "1200.00")], "51,200.00"),
    settlement=letter("Tapti General Insurance Ltd", "TGI/2026/61234", "KHB/2026/50005", "Farah Khan",
                      "Vasant General Hospital", "51,200.00",
                      [("Administrative charges - non-payable (Clause 9.4)", "1,200.00"),
                       ("Room rent in excess of eligible limit (Clause 3.1)", "1,500.00"),
                       ("Deduction as per Clause 8.2", "2,000.00")], "4,700.00", "46,500.00"),
    extracted=dict(bill_total=D("51200.00"), lines=4, room_limit=D("5000.00"), claimed=D("51200.00"),
                   approved=D("46500.00"), deductions=3),
    expected=dict(statuses=["unverified", "contestable", "unverified"],
                  supported=[None, D("0.00"), None], contestable=[D("0.00"), D("1500.00"), D("0.00")],
                  basis=["insufficient", "recalculated", "no_reason"],
                  total=D("4700.00"), contestable_total=D("1500.00"), unverified_total=D("3200.00"),
                  supported_total=D("0.00"),
                  missing=["Clause 9.4 cited in deduction 1 is not in the uploaded policy",
                           "Clause 8.2 cited in deduction 3 is not in the uploaded policy"]),
)

# ------------------------------------------------------------------ 6. incomplete and poor-quality documents
# Bill: a low-resolution, blurred, noisy scan (image OCR). Policy: not supplied. Letter: no approved amount.
# Without a policy nothing can be checked: every deduction is unverified and nothing is called contestable.
BILL_LINES_6 = [("Room rent - General ward", 4, "3000.00", "12000.00"),
                ("Surgeon fee", 1, "20000.00", "20000.00"),
                ("Pharmacy", 1, "4800.00", "4800.00")]
CASES["6_incomplete_poor_quality"] = dict(
    title="SYNTHETIC 6 - Incomplete, poor-quality documents",
    policy=None,
    bill=bill("Kamal Charitable Hospital", "KCH/2026/0077", "Joseph Thomas", BILL_LINES_6, "36,800.00"),
    settlement=letter("Godavari Insurance Co Ltd", "GIC/2026/70001", "KHB/2026/60006", "Joseph Thomas",
                      "Kamal Charitable Hospital", "36,800.00",
                      [("Room rent in excess of eligible limit", "3,000.00"),
                       ("Deduction as per policy terms", "1,000.00")], None, None),
    extracted=dict(bill_total=D("36800.00"), lines=3, claimed=D("36800.00"), approved=None, deductions=2),
    expected=dict(statuses=["unverified", "unverified"], supported=[None, None],
                  contestable=[D("0.00"), D("0.00")], basis=["insufficient", "no_reason"],
                  total=D("4000.00"), contestable_total=D("0.00"), unverified_total=D("4000.00"),
                  supported_total=D("0.00"),
                  missing=["Policy not provided: deductions cannot be checked against policy clauses",
                           "Claimed or approved amount missing from the settlement letter"]),
)

# ------------------------------------------------------------------ 7. policy exclusions
#  1 dental treatment 4,000.00: "Dental treatment" is listed in exclusion clause 8.1          supported
#  2 hearing aid 12,000.00: not on the 8.1 list                                             12,000.00 contestable
# Approved = 23,000.00 - 16,000.00 = 7,000.00
CASES["7_exclusions"] = dict(
    title="SYNTHETIC 7 - Policy exclusions",
    policy=f"""{POLICY_HEAD}
Sushrut Health Secure - Policy Wording
Policy No: SHS/2026/70007
Sum Insured: Rs 3,00,000

3.1 Room Rent
Room rent is payable up to 1% of the Sum Insured per day.

8.1 Permanent Exclusions
The Company shall not be liable for:
- Dental treatment
- Cosmetic or aesthetic treatment
- Spectacles and contact lenses
""",
    bill=bill("Arogya Dham Hospital", "ADH/2026/5521", "Sunita Iyer", [
        ("Room rent - General ward", 2, "2500.00", "5000.00"),
        ("Dental treatment - tooth extraction", 1, "4000.00", "4000.00"),
        ("Hearing aid", 1, "12000.00", "12000.00"),
        ("Physician consultation", 2, "1000.00", "2000.00")], "23,000.00"),
    settlement=letter("Kaveri General Insurance Ltd", "KGI/CL/2026/7707", "SHS/2026/70007", "Sunita Iyer",
                      "Arogya Dham Hospital", "23,000.00",
                      [("Excluded - Dental treatment (Clause 8.1)", "4,000.00"),
                       ("Excluded - Hearing aid (Clause 8.1)", "12,000.00")], "16,000.00", "7,000.00"),
    extracted=dict(bill_total=D("23000.00"), lines=4, room_limit=D("3000.00"), claimed=D("23000.00"),
                   approved=D("7000.00"), deductions=2),
    expected=dict(statuses=["supported", "contestable"], supported=[D("4000.00"), D("0.00")],
                  contestable=[D("0.00"), D("12000.00")], basis=["policy_list", "clause_absent"],
                  total=D("16000.00"), contestable_total=D("12000.00"), unverified_total=D("0.00"),
                  supported_total=D("4000.00"), missing=[]),
)

# ------------------------------------------------------------------ 8. two-page bill, "/-" amounts, rounding
# Limit 1% x 5,00,000 = 5,000/day; room billed 7,000/day x 3 days.
#  1 room rent excess (7,000 - 5,000) x 3 = 6,000.00                                         supported
#  2 ratio 5,000 / 7,000; pharmacy exempt, so associated = surgeon 30,000 + OT 17,000 = 47,000.
#    payable 47,000 x 5/7 = 33,571.43 -> deduction 13,428.57. The insurer rounded to 13,429: a 0.43 difference,
#    within the Rs 1.00 rounding tolerance                                                   supported
# Approved = 74,000 - 6,000 - 13,429 = 54,571.00
CASES["8_multipage_rounding"] = dict(
    title="SYNTHETIC 8 - Two-page bill and rounding",
    policy=f"""{POLICY_HEAD}
Vasudha Health Optima - Policy Wording
Policy No: VHO/2026/80008
Sum Insured: Rs 5,00,000

3.1 Room Rent
Room rent is payable up to 1% of the Sum Insured per day.

3.2 Proportionate Deduction
If the Insured Person occupies a room with rent higher than the eligible room rent, the associated
medical expenses shall be payable in the same proportion as the eligible room rent bears to the actual room rent.
Proportionate deduction shall not apply to pharmacy, consumables, implants and diagnostics.
""",
    bill="\n".join([BILL_HEAD, "Nirmaya Heart Hospital", "FINAL IN-PATIENT BILL",
                    "Bill No: NHH/2026/3381    Bill Date: 14-Sep-2026", "Patient Name: Rahul Bose", "",
                    " 1. Room rent - Private room                    3 x   7,000.00 =   21,000.00",
                    " 2. Surgeon fee - Angioplasty                  1 x  30,000.00 =   30,000.00",
                    "",
                    "    Page total                                                   51,000.00",
                    "\f" + BILL_HEAD, "FINAL IN-PATIENT BILL (continued)", "",
                    " 3. Operation theatre charges                  1 x  17,000.00 =   17,000.00",
                    " 4. Pharmacy                                   1 x   6,000.00 =    6,000.00",
                    "", "    GRAND TOTAL (Rs)  74,000.00"]),
    settlement="\n".join([LETTER_HEAD, "Tapti General Insurance Ltd", "CLAIM SETTLEMENT LETTER",
                          "Claim No: TGI/2026/80088", "Policy No: VHO/2026/80008", "Patient Name: Rahul Bose",
                          "Hospital: Nirmaya Heart Hospital", "", "Amount Claimed: Rs 74,000/-", "", "Deductions:",
                          "1. Room rent above eligible limit (Clause 3.1)  Rs 6,000/-",
                          "2. Proportionate deduction on associated charges (Clause 3.2)  Rs 13,429/-", "",
                          "Total Deductions: Rs 19,429/-", "Amount Approved: Rs 54,571/-"]),
    extracted=dict(bill_total=D("74000.00"), lines=4, room_limit=D("5000.00"), claimed=D("74000.00"),
                   approved=D("54571.00"), deductions=2),
    expected=dict(statuses=["supported", "supported"], supported=[D("6000.00"), D("13428.57")],
                  contestable=[D("0.00"), D("0.00")], basis=["recalculated", "recalculated"],
                  total=D("19429.00"), contestable_total=D("0.00"), unverified_total=D("0.00"),
                  supported_total=D("19429.00"), missing=[]),
)

# ------------------------------------------------------------------ 9. conflicting documents, per-head table letter
# Limit 1% x 4,00,000 = 4,000/day.
#  1 room rent 7,000/day x 4 days: excess (7,000 - 4,000) x 4 = 12,000.00                    supported
#  2 "Pharmacy - Non-payable items" 2,000.00: pharmacy is not on the 6.1 list               2,000.00 contestable
# The letter adds up (36,000 - 22,000 = 14,000), but the documents conflict: claim 36,000 vs bill 35,000, policy
# number and patient name differ, a doctor visit is billed twice, 4 room days for a 2-night stay, and the amount
# paid (21,500) is less than the amount approved (22,000).
CASES["9_conflicting_documents"] = dict(
    title="SYNTHETIC 9 - Conflicting documents",
    policy=f"""{POLICY_HEAD}
Kalpataru Health Plan - Policy Wording
Policy No: KHP/2026/90009
Sum Insured: Rs 4,00,000

3.1 Room Rent
Room rent is payable up to 1% of the Sum Insured per day.

6.1 Non-payable Items
The following items are not payable under this policy:
- Gloves
- Masks
""",
    bill="\n".join([BILL_HEAD, "Sahyog City Hospital", "FINAL IN-PATIENT BILL",
                    "Bill No: SCH/2026/0909    Bill Date: 03-Sep-2026", "Patient Name: Nikhil Joshi",
                    "Date of Admission: 01/09/2026    Date of Discharge: 03/09/2026", "",
                    " 1. Room rent - Single room                     4 x   7,000.00 =   28,000.00",
                    " 2. Doctor visit                                1 x   1,000.00 =    1,000.00",
                    " 3. Doctor visit                                1 x   1,000.00 =    1,000.00",
                    " 4. Pharmacy                                    1 x   5,000.00 =    5,000.00",
                    "", "    GRAND TOTAL (Rs)  35,000.00"]),
    settlement="\n".join([LETTER_HEAD, "Godavari Insurance Co Ltd", "CLAIM SETTLEMENT LETTER",
                          "Claim No: GIC/2026/90901", "Policy No: KHP/2026/90090", "Patient Name: Nikita Joshi",
                          "Hospital: Sahyog City Hospital", "", "Amount Claimed: Rs 36,000.00", "",
                          "Description      Claimed      Approved     Deducted    Reason",
                          "Room Rent        28,000.00    16,000.00    12,000.00   Room rent capping as per Clause 3.1",
                          "Pharmacy          5,000.00     3,000.00     2,000.00   Non-payable items",
                          "Doctor visits     2,000.00     2,000.00         0.00",
                          "Total            35,000.00    21,000.00    14,000.00", "",
                          "Amount Approved: Rs 22,000.00", "Amount Paid: Rs 21,500.00"]),
    extracted=dict(bill_total=D("35000.00"), lines=4, room_limit=D("4000.00"), claimed=D("36000.00"),
                   approved=D("22000.00"), deductions=2),
    expected=dict(statuses=["supported", "contestable"], supported=[D("12000.00"), D("0.00")],
                  contestable=[D("0.00"), D("2000.00")], basis=["recalculated", "clause_absent"],
                  total=D("14000.00"), contestable_total=D("2000.00"), unverified_total=D("0.00"),
                  supported_total=D("12000.00"),
                  missing=["Bill lines total Rs 35,000.00 but the claim is for Rs 36,000.00",
                           "Policy number on the letter (KHP/2026/90090) differs from the policy (KHP/2026/90009)"]),
    failed_checks=["C-REC-05", "C-DUP-01", "C-STAY-01", "C-ID-01", "C-ID-02", "C-REC-06"],
)
