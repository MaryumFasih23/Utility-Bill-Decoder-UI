from schemas import RawEvidence
from evidence import materialize_evidence

def raw(rows):
    return RawEvidence(facts=[],history=rows,history_complete=True,net_metering=False,missing=[],ambiguities=[])

def row(month,units=None,billed=None,payment=None,unreadable=None):
    return {'month_label':month,'month':month,'units':units,'billed':billed,'payment':payment,
            'section':'TEST ONLY','confidence':'high','unreadable_cells':unreadable or []}

def test_history_cells_are_linked_by_python():
    evidence=materialize_evidence(raw([row('2026-01','100'),row('2026-01',billed='1200.25',payment='0')]))
    assert len(evidence.history)==1
    facts={f.id:f for f in evidence.facts}
    h=evidence.history[0]
    assert facts[h.units_fact].value=='100'
    assert facts[h.billed_fact].value=='1200.25'
    assert facts[h.payment_fact].value=='0'

def test_unreadable_is_not_zero():
    evidence=materialize_evidence(raw([row('2026-01',unreadable=['units'])]))
    assert evidence.facts[0].value is None
    assert evidence.facts[0].confidence=='unreadable'

def test_credit_cells_preserved():
    evidence=materialize_evidence(raw([row('2026-01','-200','54770CR')]))
    assert {f.value for f in evidence.facts}=={'-200','54770CR'}

def test_conflicting_duplicate_month_flags_uncertainty():
    evidence=materialize_evidence(raw([row('2026-01','100'),row('2026-01','200')]))
    assert evidence.ambiguities and all(f.confidence=='low' for f in evidence.facts)

def test_provider_names_normalize_for_comparison():
    from schemas import Fact
    from evidence import comparable_value
    fact=Fact(id='provider',label='provider',value='ISLAMABAD ELECTRIC SUPPLY COMPANY',
              kind='text',unit='',section='header',printed_text='ISLAMABAD ELECTRIC SUPPLY COMPANY',confidence='high')
    assert comparable_value(fact)=='IESCO'
