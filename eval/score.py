"""
eval/score.py — Accuracy Scorer for Level 1 Ground-Truth Verification
Reads eval/review_sheet.csv, computes overall, per-field, and per-provider accuracy,
and outputs a comprehensive markdown report to eval/accuracy_report.md.
"""
import csv
from datetime import datetime
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]
SHEET_PATH = ROOT / "eval/review_sheet.csv"
REPORT_PATH = ROOT / "eval/accuracy_report.md"

def get_provider(bill_id: str) -> str:
    bid = bill_id.upper()
    if bid.startswith("KESC") or bid.startswith("KE"):
        return "KE"
    if bid.startswith("LESCO"):
        return "LESCO"
    if bid.startswith("IESCO"):
        return "IESCO"
    return "UNKNOWN"

def score_review_sheet():
    if not SHEET_PATH.exists():
        print(f"Error: {SHEET_PATH} does not exist. Run scripts/build_review_sheet.py first.")
        return

    rows = []
    with open(SHEET_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)

    total_rows = len(rows)
    correct_rows = []
    incorrect_rows = []
    unsure_rows = []
    unlabeled_rows = []

    for r in rows:
        status = r["correct"].strip().lower()
        if status == "correct":
            correct_rows.append(r)
        elif status == "incorrect":
            incorrect_rows.append(r)
        elif status == "unsure":
            unsure_rows.append(r)
        else:
            unlabeled_rows.append(r)

    total_evaluated = len(correct_rows) + len(incorrect_rows)
    overall_accuracy = (len(correct_rows) / total_evaluated * 100.0) if total_evaluated > 0 else 0.0

    # Provider breakdown
    provider_stats = defaultdict(lambda: {"correct": 0, "incorrect": 0, "unsure": 0, "unlabeled": 0})
    for r in rows:
        prov = get_provider(r["bill_id"])
        st = r["correct"].strip().lower()
        if st in ("correct", "incorrect", "unsure"):
            provider_stats[prov][st] += 1
        else:
            provider_stats[prov]["unlabeled"] += 1

    # Field breakdown
    field_stats = defaultdict(lambda: {"correct": 0, "incorrect": 0, "unsure": 0, "unlabeled": 0})
    for r in rows:
        # Normalize list item fields for grouped statistics as well as exact
        base_field = r["field"].split("[")[0].split(":")[0]
        st = r["correct"].strip().lower()
        if st in ("correct", "incorrect", "unsure"):
            field_stats[base_field][st] += 1
        else:
            field_stats[base_field]["unlabeled"] += 1

    # Exact field breakdown
    exact_field_stats = defaultdict(lambda: {"correct": 0, "incorrect": 0, "unsure": 0, "unlabeled": 0})
    for r in rows:
        st = r["correct"].strip().lower()
        if st in ("correct", "incorrect", "unsure"):
            exact_field_stats[r["field"]][st] += 1
        else:
            exact_field_stats[r["field"]]["unlabeled"] += 1

    date_str = datetime.now().strftime("%B %d, %Y")

    # Generate Markdown Report
    lines = [
        "# Level 1 Ground-Truth Verification & Accuracy Report",
        "",
        f"**Verification Date:** {date_str}  ",
        "**Methodology:** All labels were independently verified by a human against original bill scans.  ",
        "**Evaluation Scope:** 10 Official Test Bills across K-Electric, LESCO, and IESCO.  ",
        "",
        "---",
        "",
        "## 1. Overall Field-Level Accuracy Summary",
        "",
        "Accuracy is defined as `Correct / Total Evaluated`, strictly excluding rows marked `Unsure`.",
        "",
        "| Metric | Count | Percentage |",
        "| :--- | :---: | :---: |",
        f"| **Overall Field-Level Accuracy** | **{len(correct_rows)} / {total_evaluated}** | **{overall_accuracy:.2f}%** |",
        f"| Total Labeled / Evaluated | {total_evaluated} / {total_rows} | {(total_evaluated / total_rows * 100):.1f}% |",
        f"| Correct Fields | {len(correct_rows)} | {(len(correct_rows) / total_rows * 100):.1f}% of all rows |",
        f"| Incorrect Fields | {len(incorrect_rows)} | {(len(incorrect_rows) / total_rows * 100):.1f}% of all rows |",
        f"| Unsure Fields (Reported Separately) | {len(unsure_rows)} | {(len(unsure_rows) / total_rows * 100):.1f}% of all rows |",
        f"| Unlabeled Rows | {len(unlabeled_rows)} | {(len(unlabeled_rows) / total_rows * 100):.1f}% of all rows |",
        "",
        "---",
        "",
        "## 2. Accuracy Breakdown by Utility Provider",
        "",
        "| Provider | Correct | Incorrect | Unsure | Unlabeled | Total Evaluated | Accuracy (%) |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: |"
    ]

    for prov in sorted(provider_stats.keys()):
        stat = provider_stats[prov]
        tot = stat["correct"] + stat["incorrect"]
        acc = (stat["correct"] / tot * 100.0) if tot > 0 else 0.0
        lines.append(f"| **{prov}** | {stat['correct']} | {stat['incorrect']} | {stat['unsure']} | {stat['unlabeled']} | {tot} | **{acc:.2f}%** |")

    lines.extend([
        "",
        "---",
        "",
        "## 3. Accuracy Breakdown by Field (Grouped)",
        "",
        "| Base Field | Correct | Incorrect | Unsure | Unlabeled | Evaluated | Accuracy (%) |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: |"
    ])

    for fld in sorted(field_stats.keys()):
        stat = field_stats[fld]
        tot = stat["correct"] + stat["incorrect"]
        acc = (stat["correct"] / tot * 100.0) if tot > 0 else 0.0
        lines.append(f"| `{fld}` | {stat['correct']} | {stat['incorrect']} | {stat['unsure']} | {stat['unlabeled']} | {tot} | **{acc:.2f}%** |")

    lines.extend([
        "",
        "---",
        "",
        "## 4. Detailed Audit of Incorrect Fields",
        ""
    ])

    if incorrect_rows:
        lines.extend([
            "| Bill ID | Field | Extracted Value | True Value | Notes / Reason |",
            "| :--- | :--- | :--- | :--- | :--- |"
        ])
        for r in incorrect_rows:
            ext = r["extracted_value"] if r["extracted_value"] != "" else "*(null/empty)*"
            true_v = r["true_value"] if r["true_value"] != "" else "*(not provided)*"
            note = r["notes"] if r["notes"] != "" else "—"
            lines.append(f"| **{r['bill_id']}** | `{r['field']}` | `{ext}` | `{true_v}` | {note} |")
    else:
        lines.append("*(No incorrect fields recorded in this verification run.)*")

    lines.append("")
    report_text = "\n".join(lines)
    REPORT_PATH.write_text(report_text, encoding="utf-8")

    print("\n" + "=" * 60)
    print(" LEVEL 1 VERIFICATION ACCURACY REPORT")
    print("=" * 60)
    print(f"Overall Accuracy:  {overall_accuracy:.2f}% ({len(correct_rows)}/{total_evaluated})")
    print(f"Unsure Rows:       {len(unsure_rows)} (excluded from denominator)")
    print(f"Unlabeled Rows:    {len(unlabeled_rows)}")
    print(f"Report written to: {REPORT_PATH}")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    score_review_sheet()
