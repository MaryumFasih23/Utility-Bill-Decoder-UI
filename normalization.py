"""Printed numbers; CR is a credit, never a positive outstanding balance."""
from decimal import Decimal, InvalidOperation
import re

def printed_decimal(text: str) -> Decimal:
    raw = text.strip().upper().replace('−', '-').replace('–', '-')
    raw = re.sub(r'^(PKR|RS\.?|RUPEES)\s*', '', raw)
    credit = raw.endswith('CR')
    if credit:
        raw = raw[:-2].strip()
    parentheses = raw.startswith('(') and raw.endswith(')')
    if parentheses:
        raw = raw[1:-1].strip()
    if not re.fullmatch(r'[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?', raw):
        raise ValueError('Unreadable or invalid printed numeric format')
    try:
        result = Decimal(raw.replace(',', ''))
    except InvalidOperation as exc:
        raise ValueError('Invalid number') from exc
    return -abs(result) if credit or parentheses else result
