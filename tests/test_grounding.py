import pytest
from schemas import AnswerPlan, Step, Bill
from question_engine import execute_plan, GroundingError
from evaluate import compare_bill
from validation import reliability

def plan(refs, steps, template):
    return AnswerPlan(question_id='arbitrary_id', fact_ids=refs, steps=steps,
                      answer_template=template, assumptions=[], missing=[])

def test_tax_percent(sample):
    p=plan(['total_taxes','current_bill'], [Step(id='p',op='percentage',args=['total_taxes','current_bill'],unit='%')], 'Taxes are {{calc:p}}%.')
    assert execute_plan(p,'What share of the current bill is taxes?',sample)['answer'] == 'Taxes are 16.61%.'

def test_identity_lookup_can_return_a_date(sample):
    p=plan(['due_date'],[Step(id='d',op='identity',args=['due_date'],unit='')], 'Due date: {{calc:d}}.')
    assert execute_plan(p,'What is the due date?',sample)['answer']=='Due date: 2026-04-21.'

def test_tied_months(sample):
    refs=[r.units_fact for r in sample.evidence.history]
    p=plan(refs, [Step(id='peak',op='maximum',args=refs,unit='kWh',requires_complete_history=True)], '{{label:peak}}: {{calc:peak}} kWh.')
    assert execute_plan(p,'Find peak usage.',sample)['answer'] == '2025-12, 2026-02: 300 kWh.'

def test_verified_placeholder_aliases(sample):
    refs=[r.units_fact for r in sample.evidence.history]
    p=plan(refs,[Step(id='max_units',op='maximum',args=refs,unit='kWh')], 'The month is {{max_units:max_units}}.')
    assert execute_plan(p,'Which month has maximum usage?',sample)['answer']=='The month is 2025-12, 2026-02.'

def test_extreme_month_answer_includes_grounded_month(sample):
    refs=[r.units_fact for r in sample.evidence.history]
    p=plan(refs,[Step(id='peak',op='maximum',args=refs,unit='kWh')], 'Maximum: {{calc:peak}} kWh.')
    assert execute_plan(p,'Which month has maximum usage?',sample)['answer'].endswith('Month(s): 2025-12, 2026-02.')

def test_zero_bill_percentage_is_explicitly_undefined(sample):
    next(f for f in sample.evidence.facts if f.id=='current_bill').value='0'
    p=plan(['current_bill','total_taxes'],[Step(id='p',op='percentage',args=['total_taxes','current_bill'],unit='%')],'{{calc:p}}%.')
    assert 'undefined' in execute_plan(p,'Tax share?',sample)['answer']

def test_literal_in_question(sample):
    p=plan(['units_consumed'],[Step(id='r',op='multiply',args=['units_consumed','#2'],unit='kWh')],'{{calc:r}} kWh.')
    assert execute_plan(p,'What is 2 times consumption?',sample)['answer']=='302 kWh.'
    with pytest.raises(GroundingError): execute_plan(p,'What is double consumption?',sample)

def test_ast_fact_reference_counts_as_source_citation(sample):
    p=plan([], [Step(id='r',op='difference',args=['current_reading','previous_reading'],unit='kWh')], '{{calc:r}} kWh.')
    result=execute_plan(p,'Subtract printed readings.',sample)
    assert result['answer']=='151 kWh.' and len(result['sources'])==2

def test_question_threshold_in_natural_prose_is_verified(sample):
    refs=[r.units_fact for r in sample.evidence.history]
    p=plan(refs,[Step(id='n',op='count_above',args=refs+['200'],unit='months')], '{{calc:n}} months exceed 200 kWh.')
    assert execute_plan(p,'How many months exceed 200 kWh?',sample)['answer']=='2 months exceed 200 kWh.'

def test_literal_math_answer_must_match_python(sample):
    p=plan(['current_reading','previous_reading'],[Step(id='n',op='difference',args=['current_reading','previous_reading'],unit='kWh')], '151 kWh.')
    assert execute_plan(p,'Reading difference?',sample)['answer']=='151 kWh.'
    p.answer_template='152 kWh.'
    with pytest.raises(GroundingError):execute_plan(p,'Reading difference?',sample)

@pytest.mark.parametrize('template', ['It is 16.61%.', '{{calc:invented}}', '{{fact:unseen}}', '{{unknown:x}}'])
def test_fabricated_answer_rejected(template,sample):
    with pytest.raises(GroundingError): execute_plan(plan(['current_bill'],[],template),'Explain bill',sample)

def test_missing_numeric_fact(sample):
    sample.evidence.facts[0].confidence='unreadable'
    with pytest.raises(GroundingError): execute_plan(plan(['provider'],[],'{{fact:provider}}'),'provider?',sample)

def test_history_missing_cell(sample):
    fid=sample.evidence.history[1].units_fact
    next(f for f in sample.evidence.facts if f.id==fid).value=None
    refs=[r.units_fact for r in sample.evidence.history]
    with pytest.raises(GroundingError): execute_plan(plan(refs,[Step(id='r',op='average',args=refs,unit='kWh')],'{{calc:r}}'), 'Average?', sample)

def test_incomplete_history(sample):
    sample.evidence.history_complete=False
    refs=[r.units_fact for r in sample.evidence.history]
    with pytest.raises(GroundingError): execute_plan(plan(refs,[Step(id='r',op='sum',args=refs,unit='kWh',requires_complete_history=True)],'{{calc:r}}'),'Total?',sample)

def test_duplicate_line_score(sample):
    expected=sample.bill.model_dump()
    actual=sample.bill.model_dump()
    actual['charges'].append(dict(actual['charges'][1]))
    report=compare_bill(actual,expected)
    assert not report['all_exact'] and report['mismatches'][0]['field']=='charges'

def test_strict_schema(sample):
    data=sample.bill.model_dump()
    for change in [{'extra_identifier':'123'}, {'current_bill':'3430.24'}, {'current_bill':True}, {'current_bill':float('nan')}, {'due_date':'2026-02-30'}]:
        with pytest.raises(ValueError): Bill.model_validate({**data,**change})

def test_warnings_do_not_change_money(sample):
    sample.bill.current_bill=1.0
    before=sample.bill.model_dump()
    assert any('current_bill' in w for w in reliability(sample,'KESC_0008.png'))
    assert sample.bill.model_dump()==before
