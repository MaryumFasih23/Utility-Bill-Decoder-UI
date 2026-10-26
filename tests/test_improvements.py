import pytest
from pathlib import Path
from schemas import Charge, Fact, RawEvidence
from evidence import (shift_month, month_name, prune_phantom_cells,
                      canonicalize_signs, history_gaps, merge_history_rows,
                      materialize_evidence)
from config import Settings
from question_engine import QuestionEngine, execute_plan
from schemas import AnswerPlan, Step

def test_shift_month():
    assert shift_month('2026-09', -1) == '2026-08'
    assert shift_month('2026-01', -1) == '2025-12'
    assert shift_month('2025-12', 1) == '2026-01'
    assert shift_month('2026-09', -12) == '2025-09'
    assert month_name('2026-09') == 'September 2026'

def test_prune_phantom_chart_cells():
    # A 3-bar usage chart where billed/payment were recorded as unreadable
    rows = [
        {'month_label': 'Jul 26', 'month': '2026-07', 'units': '250', 'billed': None, 'payment': None,
         'section': '13 Month Usage Chart', 'confidence': 'high', 'unreadable_cells': ['billed', 'payment']},
        {'month_label': 'Aug 26', 'month': '2026-08', 'units': '230', 'billed': None, 'payment': None,
         'section': '13 Month Usage Chart', 'confidence': 'high', 'unreadable_cells': ['billed', 'payment']},
        {'month_label': 'Sep 26', 'month': '2026-09', 'units': '190', 'billed': None, 'payment': None,
         'section': '13 Month Usage Chart', 'confidence': 'high', 'unreadable_cells': ['billed', 'payment']},
    ]
    raw = RawEvidence(facts=[], history=rows, history_complete=True, net_metering=False, missing=[], ambiguities=[])
    ev = materialize_evidence(raw)
    # The units cells should be present, but phantom billed/payment facts should be pruned
    for r in ev.history:
        assert r.units_fact is not None
        assert r.billed_fact is None
        assert r.payment_fact is None

def test_canonicalize_signs(sample):
    # If subsidy is positive in charges, canonicalize_signs should make it negative
    b = sample.bill.model_copy(update={'charges': sample.bill.charges + [Charge(type='subsidy', amount=1000.0)]})
    ex = sample.model_copy(update={'bill': b})
    updated = canonicalize_signs(ex)
    subsidy_charge = next(c for c in updated.bill.charges if c.type == 'subsidy')
    assert subsidy_charge.amount == -1000.0

def test_history_gaps_and_merge(sample):
    # sample bill has bill_month '2026-04' and history for 2025-12, 2026-01, 2026-02
    gaps = history_gaps(sample, window=6)
    # Expected last 6 months: 2025-10, 2025-11, 2025-12, 2026-01, 2026-02, 2026-03
    assert '2026-03' in gaps
    assert '2025-11' in gaps
    assert '2026-01' not in gaps

    # Test merge_history_rows fills gap without overwriting
    class FakeRow:
        def __init__(self, m, u):
            self.month = m; self.month_label = m; self.units = u; self.billed = None; self.payment = None
            self.section = 'Recovered'; self.confidence = 'high'
    recovered_rows = [FakeRow('2026-03', '280')]
    merged = merge_history_rows(sample.evidence, recovered_rows, ['2026-03'])
    row_03 = next(r for r in merged.history if r.month == '2026-03')
    fact_03 = next(f for f in merged.facts if f.id == row_03.units_fact)
    assert fact_03.value == '280'

def test_settings_validation():
    s = Settings(min_request_interval=0.5, max_image_side=2048)
    assert s.min_request_interval == 0.5
    assert s.max_image_side == 2048
    with pytest.raises(ValueError):
        Settings(min_request_interval=-1)
    with pytest.raises(ValueError):
        Settings(max_image_side=100)

def test_answer_single_method(tmp_path, sample):
    from PIL import Image
    dummy = tmp_path / 'dummy.png'
    Image.new('RGB', (10, 10)).save(dummy)
    class MockClient:
        def generate(self, prompt, schema, images=()):
            from schemas import Plans
            return Plans(plans=[
                AnswerPlan(question_id='user_q', fact_ids=['current_bill'],
                           steps=[Step(id='cb', op='identity', args=['current_bill'], unit='PKR')],
                           answer_template='Your current bill is PKR {{calc:cb}}.',
                           assumptions=[], missing=[])
            ])
    engine = QuestionEngine(Settings(cache_dir=tmp_path), MockClient(), None, no_cache=True)
    ans = engine.answer_single(dummy, sample, 'What is my current bill?')
    assert 'PKR 3430.24' in ans['answer']
