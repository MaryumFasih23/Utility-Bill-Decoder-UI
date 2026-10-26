import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Map bill_ids to their image paths
images = {}
for p in (ROOT / "test-20261010T073553Z-1-001/test/bills").glob("*"):
    if p.suffix.lower() in ('.jpg', '.jpeg', '.png'):
        images[p.stem] = str(p.relative_to(ROOT)).replace('\\', '/')

l1_path = ROOT / "output/level1.csv"
rows_out = []

scalar_fields = [
    "provider", "tariff", "sanctioned_load_kw", "bill_month", "reading_date",
    "issue_date", "due_date", "previous_reading", "current_reading", "units_consumed",
    "total_charges", "total_taxes", "current_bill", "arrears",
    "payable_within_due_date", "payable_after_due_date"
]

with open(l1_path, encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    for row in reader:
        bid = row['bill_id']
        b = json.loads(row['json'])
        img_path = images.get(bid, "")

        # 1. Scalar fields
        for fld in scalar_fields:
            val = b.get(fld)
            extracted_str = "" if val is None else str(val)
            rows_out.append({
                "bill_id": bid,
                "field": fld,
                "extracted_value": extracted_str,
                "bill_image_path": img_path,
                "correct": "",
                "true_value": "",
                "notes": ""
            })

        # 2. Charges: item count + individual items
        charges = b.get("charges", [])
        rows_out.append({
            "bill_id": bid,
            "field": "charges:item_count",
            "extracted_value": str(len(charges)),
            "bill_image_path": img_path,
            "correct": "",
            "true_value": "",
            "notes": ""
        })
        for i, c in enumerate(charges):
            c_str = f"{c.get('type')}: {c.get('amount')}"
            rows_out.append({
                "bill_id": bid,
                "field": f"charges[{i}]",
                "extracted_value": c_str,
                "bill_image_path": img_path,
                "correct": "",
                "true_value": "",
                "notes": ""
            })

        # 3. Taxes: item count + individual items
        taxes = b.get("taxes", [])
        rows_out.append({
            "bill_id": bid,
            "field": "taxes:item_count",
            "extracted_value": str(len(taxes)),
            "bill_image_path": img_path,
            "correct": "",
            "true_value": "",
            "notes": ""
        })
        for i, t in enumerate(taxes):
            t_str = f"{t.get('type')}: {t.get('amount')}"
            rows_out.append({
                "bill_id": bid,
                "field": f"taxes[{i}]",
                "extracted_value": t_str,
                "bill_image_path": img_path,
                "correct": "",
                "true_value": "",
                "notes": ""
            })

out_csv = ROOT / "eval/review_sheet.csv"
fieldnames = ["bill_id", "field", "extracted_value", "bill_image_path", "correct", "true_value", "notes"]

with open(out_csv, "w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows_out)

print(f"Successfully generated {out_csv} with {len(rows_out)} rows.")
