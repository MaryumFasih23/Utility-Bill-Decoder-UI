"""All arithmetic executes here. No model-generated code or eval."""
from decimal import Decimal, ROUND_HALF_UP
from datetime import date

def calculate(op: str, values: list):
    if not values:
        raise ValueError('No operands')
    if op == 'identity' and len(values)==1 and isinstance(values[0],(Decimal,str)):
        return values[0]
    if op == 'days_between':
        if len(values) != 2:
            raise ValueError('days_between needs two dates')
        return Decimal((date.fromisoformat(str(values[0])) - date.fromisoformat(str(values[1]))).days)
    if not all(isinstance(v, Decimal) and v.is_finite() for v in values):
        raise ValueError('Numeric operation requires finite numeric evidence')
    if op == 'sum': return sum(values, Decimal(0))
    if op == 'average': return sum(values, Decimal(0)) / len(values)
    if op == 'maximum': return max(values)
    if op == 'minimum': return min(values)
    if op.startswith('count_'):
        if len(values) < 2: raise ValueError('Count needs data and threshold')
        data, threshold = values[:-1], values[-1]
        predicates = {'count_above': lambda x: x > threshold,
                      'count_below': lambda x: x < threshold,
                      'count_at_least': lambda x: x >= threshold,
                      'count_at_most': lambda x: x <= threshold}
        return Decimal(sum(predicates[op](x) for x in data))
    if len(values) != 2: raise ValueError(f'{op} requires two operands')
    a, b = values
    if op == 'difference': return a - b
    if op == 'multiply': return a * b
    if op in ('divide', 'percentage', 'percentage_change'):
        if b == 0: raise ValueError('Cannot divide by zero')
        if op == 'divide': return a / b
        if op == 'percentage': return a / b * 100
        return (a - b) / b * 100  # (new, old)
    if op == 'round':
        if b != b.to_integral_value() or not 0 <= b <= 6:
            raise ValueError('Invalid rounding precision')
        return a.quantize(Decimal(1).scaleb(-int(b)), rounding=ROUND_HALF_UP)
    raise ValueError(f'Unsupported operation: {op}')

def format_number(value: Decimal, decimals=2):
    rounded = value.quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)
    return format(rounded, 'f').rstrip('0').rstrip('.') if decimals else format(rounded, 'f')
