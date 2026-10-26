from schemas import Extraction, Evidence, Fact, HistoryRow
from normalization import printed_decimal

def fact_catalog(extraction: Extraction):
    return {f.id: f for f in extraction.evidence.facts}

def comparable_value(fact):
    if fact.value is None: return None
    if fact.id == 'provider':
        text=fact.value.upper().replace('-', ' ').strip()
        if text in ('KE','KESC','K ELECTRIC') or 'KARACHI ELECTRIC' in text: return 'KE'
        if text=='IESCO' or 'ISLAMABAD ELECTRIC' in text: return 'IESCO'
        if text=='LESCO' or 'LAHORE ELECTRIC' in text: return 'LESCO'
    return printed_decimal(fact.value) if fact.kind == 'number' else fact.value

def evidence_checks(extraction):
    issues = []
    catalog = fact_catalog(extraction)
    for name, value in extraction.bill.model_dump().items():
        if name in ('charges', 'taxes') or value is None: continue
        fact = catalog.get(name)
        if fact is None:
            issues.append(f'{name}: no source provenance')
            continue
        try:
            actual = comparable_value(fact)
            expected = printed_decimal(str(value)) if isinstance(value, (int, float)) else value
            if actual != expected: issues.append(f'{name}: official field conflicts with source fact')
        except ValueError:
            issues.append(f'{name}: invalid evidence number')
    for name, items in [('charge', extraction.bill.charges), ('tax', extraction.bill.taxes)]:
        for i, item in enumerate(items):
            f = catalog.get(f'{name}_{i}')
            if f is None: issues.append(f'{name}_{i}: no source provenance')
            elif comparable_value(f) != printed_decimal(str(item.amount)):
                issues.append(f'{name}_{i}: line amount conflicts with evidence')
    for row in extraction.evidence.history:
        for ref in (row.units_fact, row.billed_fact, row.payment_fact):
            if ref and ref not in catalog: issues.append(f'{ref}: dangling history reference')
    return issues

def materialize_evidence(raw):
    """Create fact references in Python; the model transcribes historical cells only."""
    facts = {f.id:f for f in raw.facts}
    if len(facts) != len(raw.facts): raise ValueError('Duplicate internal source fact ID')
    rows = {}
    for i, item in enumerate(raw.history):
        # Merge chart and billing table only when the exact year/month is known.
        key = item.month or f'unknown_{i}'
        row = rows.setdefault(key, HistoryRow(month_label=item.month_label, month=item.month,
                              units_fact=None,billed_fact=None,payment_fact=None))
        for kind in ('units','billed','payment'):
            value = getattr(item,kind)
            if value is None and kind not in item.unreadable_cells: continue
            if value is not None: printed_decimal(value)  # Reject impossible formatting.
            fid=f'history_cell_{i}_{kind}'
            if fid in facts: raise ValueError('Reserved historical fact ID collision')
            facts[fid]=Fact(id=fid,label=item.month_label+' '+kind,value=value,kind='number',
                unit='kWh' if kind=='units' else 'PKR',section=item.section,
                printed_text=value or 'Unreadable printed cell',
                confidence='unreadable' if value is None else item.confidence)
            existing = getattr(row,kind+'_fact')
            if existing and facts[existing].value is not None and value is None:
                continue  # A blank cell in a different table cannot erase a readable chart cell.
            if existing and facts[existing].value is not None and value is not None and facts[existing].value != value:
                raw.ambiguities.append(item.month_label+' has conflicting '+kind+' cells; both facts retained.')
                facts[existing].confidence='low'
                facts[fid].confidence='low'
            setattr(row,kind+'_fact',fid)
    return Evidence(facts=list(facts.values()),history=list(rows.values()),
        history_complete=raw.history_complete,net_metering=raw.net_metering,
        missing=raw.missing,ambiguities=raw.ambiguities)
