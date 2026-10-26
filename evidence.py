from datetime import date
from schemas import Extraction, Evidence, Fact, HistoryRow
from normalization import printed_decimal

HISTORY_KINDS = ('units', 'billed', 'payment')

def shift_month(month: str, delta: int) -> str:
    """Calendar arithmetic on YYYY-MM strings (delta in months)."""
    year, mon = map(int, month.split('-'))
    index = year * 12 + (mon - 1) + delta
    return f'{index // 12:04d}-{index % 12 + 1:02d}'

def month_name(month: str) -> str:
    return date.fromisoformat(month + '-01').strftime('%B %Y')

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
            else:
                try: printed = comparable_value(f)
                except ValueError:
                    issues.append(f'{name}_{i}: invalid evidence number'); continue
                expected = printed_decimal(str(item.amount))
                # Subsidies are printed unsigned under a deductions heading, but the
                # guide records them as negative: compare magnitudes for that type only.
                if getattr(item, 'type', None) == 'subsidy' and printed is not None:
                    printed, expected = abs(printed), abs(expected)
                if printed != expected:
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
    return prune_phantom_cells(Evidence(facts=list(facts.values()),history=list(rows.values()),
        history_complete=raw.history_complete,net_metering=raw.net_metering,
        missing=raw.missing,ambiguities=raw.ambiguities))

def prune_phantom_cells(evidence: Evidence) -> Evidence:
    """Drop 'unreadable' history cells for columns a source section never prints.

    Vision models often list billed/payment as unreadable for every bar of a usage
    chart, which has no such columns. A column with zero readable cells across an
    entire section is absent, not illegible; keeping it pollutes warnings and makes
    the planner report spurious missing payments.
    """
    facts = {f.id: f for f in evidence.facts}
    groups = {}
    for row in evidence.history:
        for kind in HISTORY_KINDS:
            ref = getattr(row, kind + '_fact')
            if ref and ref.startswith('history_cell_') and ref in facts:
                groups.setdefault((facts[ref].section, kind), []).append((row, ref))
    phantom = set()
    for (section, kind), cells in groups.items():
        # Only prune billed/payment columns if 100% empty across a usage chart (>=3 bars).
        # Never prune units cells or single rows.
        if kind in ('billed', 'payment') and len(cells) >= 3 and any(w in section.lower() for w in ('chart', 'bar', 'graph', 'usage')):
            if all(facts[ref].value is None for _, ref in cells):
                phantom.update(ref for _, ref in cells)
    if not phantom: return evidence
    rows = []
    for row in evidence.history:
        update = {kind + '_fact': None for kind in HISTORY_KINDS if getattr(row, kind + '_fact') in phantom}
        rows.append(row.model_copy(update=update) if update else row)
    # Facts still referenced elsewhere (other rows) are retained.
    referenced = {getattr(r, k + '_fact') for r in rows for k in HISTORY_KINDS}
    kept = [f for f in evidence.facts if f.id not in phantom or f.id in referenced]
    return evidence.model_copy(update={'facts': kept, 'history': rows})

def readable_history_months(extraction, kind='units'):
    catalog = fact_catalog(extraction)
    months = {}
    for row in extraction.evidence.history:
        ref = getattr(row, kind + '_fact')
        if row.month and ref and ref in catalog and catalog[ref].value is not None:
            months[row.month] = catalog[ref]
    return months

def history_gaps(extraction, window=12):
    """Months in the printed-history window (bill month minus 1..window) lacking readable units.

    Only reported when the bill evidently prints a monthly series (>= 3 readable months),
    so bills without history never trigger extra model calls.
    """
    bill_month = extraction.bill.bill_month
    readable = readable_history_months(extraction)
    if not bill_month or len(readable) < 3: return []
    expected = [shift_month(bill_month, -k) for k in range(window, 0, -1)]
    return [m for m in expected if m not in readable]

def merge_history_rows(evidence: Evidence, raw_rows, months) -> Evidence:
    """Merge targeted reread rows only for the requested gap months; never overwrite readable cells."""
    wanted = set(months)
    facts = {f.id: f for f in evidence.facts}
    rows = {r.month: r for r in evidence.history if r.month}
    others = [r for r in evidence.history if not r.month]
    added = False
    for item in raw_rows:
        if item.month not in wanted: continue
        row = rows.get(item.month) or HistoryRow(month_label=item.month_label, month=item.month,
                                                 units_fact=None, billed_fact=None, payment_fact=None)
        update = {}
        for kind in HISTORY_KINDS:
            value = getattr(item, kind)
            if value is None: continue
            try: printed_decimal(value)
            except ValueError: continue
            existing = getattr(row, kind + '_fact')
            if existing and existing in facts and facts[existing].value is not None: continue
            fid = f"history_gap_{item.month.replace('-', '_')}_{kind}"
            facts[fid] = Fact(id=fid, label=item.month_label + ' ' + kind, value=value, kind='number',
                              unit='kWh' if kind == 'units' else 'PKR', section=item.section,
                              printed_text=value, confidence=item.confidence)
            update[kind + '_fact'] = fid
        if update:
            rows[item.month] = row.model_copy(update=update)
            added = True
    if not added: return evidence
    history = [rows[m] for m in sorted(rows)] + others
    return evidence.model_copy(update={'facts': list(facts.values()), 'history': history})

def canonicalize_signs(extraction: Extraction) -> Extraction:
    """Apply the guide's sign rules deterministically; magnitudes are never changed.

    * Subsidy/relief lines are recorded as negative deductions.
    * A scalar whose source fact prints a CR/parenthesised credit is negative.
    """
    bill = extraction.bill
    catalog = fact_catalog(extraction)
    update = {}
    charges = [c.model_copy(update={'amount': -abs(c.amount)}) if c.type == 'subsidy' and c.amount > 0 else c
               for c in bill.charges]
    if charges != bill.charges: update['charges'] = charges
    for name in ('arrears', 'current_bill', 'payable_within_due_date', 'payable_after_due_date'):
        value, fact = getattr(bill, name), catalog.get(name)
        if value is None or value <= 0 or fact is None or fact.value is None: continue
        try: printed = printed_decimal(fact.printed_text)
        except ValueError: continue
        if printed < 0 and abs(printed) == printed_decimal(str(value)):
            update[name] = -abs(value)
    if not update: return extraction
    return extraction.model_copy(update={'bill': bill.model_copy(update=update)})
