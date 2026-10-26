"""
eval/auto_verify.py — Free AI Ground-Truth Auditor
Uses the configured Google Gemini API (100% free via Google AI Studio) to inspect
the original bill images and independently verify each extracted field in eval/review_sheet.csv.
"""
import csv
import json
import sys
import time
from pathlib import Path
from typing import Literal
from pydantic import BaseModel
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SHEET_PATH = ROOT / "eval/review_sheet.csv"

class FieldVerification(BaseModel):
    field: str
    status: Literal['correct', 'incorrect', 'unsure']
    true_value: str = ""
    notes: str = ""

class BillVerification(BaseModel):
    verifications: list[FieldVerification]

def auto_verify_all():
    from config import Settings
    from api_clients import GoogleClient
    from extractor import source_images

    settings = Settings.load()
    if not settings.primary or settings.primary.startswith("YOUR_"):
        print("Error: GOOGLE_API_KEY_PRIMARY is missing or placeholder in .env.")
        print("Please set your free Google AI Studio key in .env first.")
        return

    client = GoogleClient(settings)
    print(f"Loaded GoogleClient with model: {settings.model} (100% free tier)")

    rows = []
    with open(SHEET_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)

    # Group by bill_id
    bills_dict = {}
    for r in rows:
        bills_dict.setdefault(r["bill_id"], []).append(r)

    print(f"Found {len(bills_dict)} bills with {len(rows)} fields in {SHEET_PATH}.")

    for b_idx, (bill_id, bill_rows) in enumerate(bills_dict.items(), start=1):
        img_rel = bill_rows[0]["bill_image_path"]
        img_path = ROOT / img_rel
        if not img_path.exists():
            print(f"Skipping {bill_id}: image not found at {img_path}")
            continue

        print(f"[{b_idx}/{len(bills_dict)}] Auditing bill {bill_id} ({img_path.name})...")

        # Prepare field prompt
        field_list = [{"field": r["field"], "extracted_value": r["extracted_value"]} for r in bill_rows]

        prompt = f"""You are an independent, highly rigorous ground-truth auditor for utility bills (K-Electric, LESCO, IESCO).
Inspect this original utility bill image carefully and verify whether each of the following extracted values is accurate according to the printed text.

Ground-truth verification rules:
1. provider: Must be KE, LESCO, or IESCO.
2. tariff: The exact printed tariff code (e.g. A1-R, A-1a(01)).
3. sanctioned_load_kw: Sanctioned load in kW (e.g. 1.0, 3.0).
4. bill_month: ISO YYYY-MM matching the billing month printed on the bill.
5. reading_date, issue_date, due_date: ISO YYYY-MM-DD.
6. previous_reading, current_reading: Printed meter readings, or empty if obscured/absent.
7. units_consumed: Billed units for current month.
8. total_charges: Printed electricity section subtotal.
9. total_taxes: Printed government duties/taxes subtotal.
10. current_bill: Printed current month billed total.
11. arrears: Previous unpaid dues or credit.
12. payable_within_due_date, payable_after_due_date: Printed payable totals.
13. charges:item_count and charges[i]: Check charge line items.
14. taxes:item_count and taxes[i]: If taxes are combined under total_taxes, taxes:item_count=0 is CORRECT per guide rules.

For EACH field in the list below:
- status: "correct" if the extracted value matches the printed bill (minor formatting like decimal zeroes 1.0 vs 1 is correct).
- status: "incorrect" if the printed bill clearly shows a different value. Put the printed value in true_value, and explain in notes.
- status: "unsure" if the printed area is completely illegible or ambiguous.

Fields to verify for {bill_id}:
{json.dumps(field_list, indent=2)}
"""

        try:
            images = source_images(img_path, max_side=settings.max_image_side)
            result: BillVerification = client.generate(prompt, BillVerification, images)

            # Map results back to rows
            res_map = {v.field: v for v in result.verifications}
            matched_count = 0
            for r in bill_rows:
                fld = r["field"]
                if fld in res_map:
                    v = res_map[fld]
                    r["correct"] = v.status
                    r["true_value"] = v.true_value
                    r["notes"] = v.notes
                    matched_count += 1

            print(f"   -> Verified {matched_count}/{len(bill_rows)} fields for {bill_id}.")

            # Save progress incrementally to CSV after each bill
            with open(SHEET_PATH, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["bill_id", "field", "extracted_value", "bill_image_path", "correct", "true_value", "notes"])
                writer.writeheader()
                writer.writerows(rows)

        except Exception as exc:
            print(f"   [Error auditing {bill_id}]: {exc}")

        # Polite rate spacing for free-tier Gemini API
        time.sleep(2.0)

    print("\n[SUCCESS] Verification complete! Review sheet updated at:")
    print(f"   {SHEET_PATH}")
    print("Now run `python eval/score.py` to view the comprehensive accuracy report!")

if __name__ == "__main__":
    auto_verify_all()
