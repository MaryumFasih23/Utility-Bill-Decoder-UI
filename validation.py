"""Warnings are diagnostics, never monetary corrections."""
from datetime import date
from decimal import Decimal
import re
from normalization import printed_decimal
from evidence import evidence_checks

def reliability(extraction, filename):
    b, e = extraction.bill, extraction.evidence
    warnings = evidence_checks(extraction)
    expected = next((provider for prefix, provider in [('KESC', 'KE'), ('KE_', 'KE'), ('LESCO', 'LESCO'), ('IESCO', 'IESCO')]
                     if filename.upper().startswith(prefix)), None)
    if expected and b.provider != expected: warnings.append('provider: filename/layout mismatch')
    for name in ('provider', 'bill_month', 'current_bill', 'units_consumed', 'due_date', 'payable_within_due_date'):
        if getattr(b, name) is None: warnings.append(f'{name}: missing expected field')
    if b.issue_date and b.due_date and b.issue_date > b.due_date:
        warnings.append('due_date: occurs before issue_date')
    if b.reading_date and b.issue_date and b.reading_date > b.issue_date:
        warnings.append('reading_date: occurs after issue_date')
    if b.bill_month and b.issue_date:
        month_date = date.fromisoformat(b.bill_month + '-01')
        if abs((date.fromisoformat(b.issue_date) - month_date).days) > 62:
            warnings.append('bill_month: distant from issue_date')
    def d(v): return Decimal(str(v))
    for label, items, total in [('total_charges', b.charges, b.total_charges), ('total_taxes', b.taxes, b.total_taxes)]:
        if items and total is not None and abs(sum((d(x.amount) for x in items), Decimal(0)) - d(total)) > Decimal('.05'):
            warnings.append(f'{label}: printed total differs from line sum; retain printed values')
    if all(x is not None for x in (b.current_bill, b.total_charges, b.total_taxes)):
        if abs(d(b.current_bill) - d(b.total_charges) - d(b.total_taxes)) > Decimal('.05'):
            warnings.append('current_bill: differs from charges plus taxes; inspect adjustments')
    if all(x is not None for x in (b.current_bill, b.arrears, b.payable_within_due_date)):
        if abs(d(b.current_bill) + d(b.arrears) - d(b.payable_within_due_date)) > Decimal(1):
            warnings.append('payable_within_due_date: balance relationship needs review')
    if not e.net_metering and all(x is not None for x in (b.previous_reading, b.current_reading, b.units_consumed)):
        if d(b.current_reading) - d(b.previous_reading) != d(b.units_consumed):
            warnings.append('units_consumed: register difference mismatch; rollover/multiplier possible')
    if e.net_metering: warnings.append('net-metering: multiple registers; do not subtract arbitrary rows')
    for f in e.facts:
        if f.confidence in ('low', 'unreadable'): warnings.append(f'{f.id}: uncertain source fact')
        if f.value and f.kind == 'number':
            try:
                val = printed_decimal(f.value)
                if 'CR' in f.printed_text.upper() and val > 0:
                    warnings.append(f'{f.id}: CR sign conflict')
            except ValueError: warnings.append(f'{f.id}: invalid printed number')
    return sorted(set(warnings + e.ambiguities))

def check_private(text, secrets=()):
    if any(key and len(key) > 8 and key in text for key in secrets):
        raise ValueError('Secret detected in output')
    if re.search(r'\b(?:AIza[\w-]{25,}|sk-[\w-]{16,}|\d{5}-\d{7}-\d)\b', text):
        raise ValueError('Secret/identifier pattern detected in output')
    if re.search(r'\b(?:CNIC|consumer\s+(?:id|number)|account\s+(?:no\.?|number)|meter\s+(?:no\.?|number)|reference\s+(?:no\.?|number))\s*[:=]\s*\S+', text, re.I):
        raise ValueError('Forbidden customer identifier detected')
