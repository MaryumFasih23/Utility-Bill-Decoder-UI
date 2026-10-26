# Level 1 Ground-Truth Verification & Accuracy Report

**Verification Date:** October 26, 2026  
**Methodology:** All labels were independently verified by a human against original bill scans.  
**Evaluation Scope:** 10 Official Test Bills across K-Electric, LESCO, and IESCO.  

---

## 1. Overall Field-Level Accuracy Summary

Accuracy is defined as `Correct / Total Evaluated`, strictly excluding rows marked `Unsure`.

| Metric | Count | Percentage |
| :--- | :---: | :---: |
| **Overall Field-Level Accuracy** | **225 / 237** | **94.94%** |
| Total Labeled / Evaluated | 237 / 237 | 100.0% |
| Correct Fields | 225 | 94.9% of all rows |
| Incorrect Fields | 12 | 5.1% of all rows |
| Unsure Fields (Reported Separately) | 0 | 0.0% of all rows |
| Unlabeled Rows | 0 | 0.0% of all rows |

---

## 2. Accuracy Breakdown by Utility Provider

| Provider | Correct | Incorrect | Unsure | Unlabeled | Total Evaluated | Accuracy (%) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **IESCO** | 63 | 0 | 0 | 0 | 63 | **100.00%** |
| **KE** | 95 | 12 | 0 | 0 | 107 | **88.79%** |
| **LESCO** | 67 | 0 | 0 | 0 | 67 | **100.00%** |

---

## 3. Accuracy Breakdown by Field (Grouped)

| Base Field | Correct | Incorrect | Unsure | Unlabeled | Evaluated | Accuracy (%) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `arrears` | 10 | 0 | 0 | 0 | 10 | **100.00%** |
| `bill_month` | 10 | 0 | 0 | 0 | 10 | **100.00%** |
| `charges` | 52 | 0 | 0 | 0 | 52 | **100.00%** |
| `current_bill` | 10 | 0 | 0 | 0 | 10 | **100.00%** |
| `current_reading` | 10 | 0 | 0 | 0 | 10 | **100.00%** |
| `due_date` | 10 | 0 | 0 | 0 | 10 | **100.00%** |
| `issue_date` | 10 | 0 | 0 | 0 | 10 | **100.00%** |
| `payable_after_due_date` | 10 | 0 | 0 | 0 | 10 | **100.00%** |
| `payable_within_due_date` | 10 | 0 | 0 | 0 | 10 | **100.00%** |
| `previous_reading` | 10 | 0 | 0 | 0 | 10 | **100.00%** |
| `provider` | 10 | 0 | 0 | 0 | 10 | **100.00%** |
| `reading_date` | 10 | 0 | 0 | 0 | 10 | **100.00%** |
| `sanctioned_load_kw` | 10 | 0 | 0 | 0 | 10 | **100.00%** |
| `tariff` | 10 | 0 | 0 | 0 | 10 | **100.00%** |
| `taxes` | 13 | 12 | 0 | 0 | 25 | **52.00%** |
| `total_charges` | 10 | 0 | 0 | 0 | 10 | **100.00%** |
| `total_taxes` | 10 | 0 | 0 | 0 | 10 | **100.00%** |
| `units_consumed` | 10 | 0 | 0 | 0 | 10 | **100.00%** |

---

## 4. Detailed Audit of Incorrect Fields

| Bill ID | Field | Extracted Value | True Value | Notes / Reason |
| :--- | :--- | :--- | :--- | :--- |
| **KESC_0002** | `taxes:item_count` | `3` | `0` | Per guide rules, if taxes are grouped under total_taxes and not listed individually as line items with breakdown counts, item_count should be 0. |
| **KESC_0002** | `taxes[0]` | `electricity_duty: 81.89` | `*(not provided)*` | Taxes item_count should be 0. |
| **KESC_0002** | `taxes[1]` | `gst: 1159.4` | `*(not provided)*` | Taxes item_count should be 0. |
| **KESC_0002** | `taxes[2]` | `municipal_tax: 20.0` | `*(not provided)*` | Taxes item_count should be 0. |
| **KESC_0003** | `taxes:item_count` | `3` | `0` | According to the guide rules, if taxes are combined under total_taxes, taxes:item_count=0 is correct. |
| **KESC_0003** | `taxes[0]` | `electricity_duty: 299.83` | `*(not provided)*` | Taxes item count should be 0 as per rules. |
| **KESC_0003** | `taxes[1]` | `gst: 3831.98` | `*(not provided)*` | Taxes item count should be 0 as per rules. |
| **KESC_0003** | `taxes[2]` | `municipal_tax: 125.0` | `*(not provided)*` | Taxes item count should be 0 as per rules. |
| **KESC_0006** | `taxes:item_count` | `3` | `0` | According to the guide rules, since taxes are combined under total_taxes, taxes:item_count=0 is correct. |
| **KESC_0006** | `taxes[0]` | `electricity_duty: 231.04` | `*(not provided)*` | Taxes are grouped under total_taxes subtotal row, so individual taxes array items should be empty/omitted according to rules. |
| **KESC_0006** | `taxes[1]` | `gst: 3030.08` | `*(not provided)*` | Taxes are grouped under total_taxes subtotal row, so individual taxes array items should be empty/omitted according to rules. |
| **KESC_0006** | `taxes[2]` | `municipal_tax: 100.0` | `*(not provided)*` | Taxes are grouped under total_taxes subtotal row, so individual taxes array items should be empty/omitted according to rules. |
