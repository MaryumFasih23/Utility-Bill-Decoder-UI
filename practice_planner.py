"""OFFLINE PRACTICE ONLY: generic intent grammar, not an official-runtime fallback.

Uses exactly the same executor as the model planner. No bill-name or question lookup.
Unknown phrasing is explicitly unsupported in this limited practice planner.
"""
import re
from schemas import AnswerPlan, Step
from question_engine import execute_plan

def plan_practice(question_id, question, extraction):
    q = question.lower()
    refs, steps, assumptions = [], [], []
    def step(op, args, unit, complete=False):
        refs.extend(a for a in args if not a.startswith(('#', '$')))
        steps.append(Step(id='result', op=op, args=args, unit=unit,
                          decimals=2, requires_complete_history=complete))
    if ('percent' in q or 'percentage' in q) and 'tax' in q:
        step('percentage', ['total_taxes', 'current_bill'], '%')
        template = 'Taxes are {{calc:result}}% of the printed current bill.'
    elif ('late' in q or 'after' in q) and ('difference' in q or 'extra' in q or 'more' in q):
        step('difference', ['payable_after_due_date', 'payable_within_due_date'], 'PKR')
        template = 'The highest printed after-due amount exceeds the within-due amount by PKR {{calc:result}}.'
    elif ('difference' in q or 'subtract' in q) and ('reading' in q):
        if extraction.evidence.net_metering:
            return AnswerPlan(question_id=question_id, fact_ids=[], steps=[],
                answer_template='', assumptions=[], missing=['An unambiguous selected meter register is required.'])
        step('difference', ['current_reading', 'previous_reading'], 'kWh')
        template = 'The meter-reading difference is {{calc:result}} kWh.'
    elif ('histor' in q or 'month' in q) and any(term in q for term in ('highest', 'lowest', 'maximum', 'minimum', 'average', 'total', 'sum', 'above', 'below', 'exceed')):
        metric = 'billed_fact' if 'billed' in q else 'payment_fact' if 'payment' in q else 'units_fact'
        args = [getattr(row, metric) for row in extraction.evidence.history if getattr(row, metric)]
        unit = 'PKR' if metric != 'units_fact' else 'kWh'
        if not args:
            return AnswerPlan(question_id=question_id, fact_ids=[], steps=[], answer_template='', assumptions=[], missing=['Readable historical ' + metric])
        if any(x in q for x in ('highest', 'maximum', 'lowest', 'minimum')):
            op = 'minimum' if 'lowest' in q or 'minimum' in q else 'maximum'
            step(op, args, unit, True)
            template = 'The ' + ('lowest' if op == 'minimum' else 'highest') + ' value is {{calc:result}} ' + unit + ' in {{label:result}}.'
        elif any(x in q for x in ('above', 'below', 'exceed')):
            threshold = re.search(r'(?:above|below|exceed\w*)\s+([+-]?\d+(?:\.\d+)?)', q)
            if not threshold:
                return AnswerPlan(question_id=question_id, fact_ids=[], steps=[], answer_template='', assumptions=[], missing=['A readable question threshold'])
            op = 'count_below' if 'below' in q else 'count_above'
            step(op, args + ['#' + threshold[1]], 'months', True)
            template = '{{calc:result}} printed historical months meet the threshold.'
        else:
            step('average' if 'average' in q else 'sum', args, unit, True)
            template = 'The ' + ('average' if 'average' in q else 'total') + ' across the printed history is {{calc:result}} ' + unit + '.'
        assumptions = ['The period includes every readable month in the printed history.']
    else:
        choices = [('arrears', 'arrears', 'PKR'), ('current bill', 'current_bill', 'PKR'),
                   ('taxes', 'total_taxes', 'PKR'), ('units consumed', 'units_consumed', 'kWh'),
                   ('due date', 'due_date', ''), ('provider', 'provider', ''),
                   ('within', 'payable_within_due_date', 'PKR')]
        found = next(((fid, unit) for term, fid, unit in choices if term in q), None)
        if found:
            fid, unit = found
            refs.append(fid)
            template = 'The printed value is ' + unit + ' {{fact:' + fid + '}}.'
        else:
            return AnswerPlan(question_id=question_id, fact_ids=[], steps=[], answer_template='', assumptions=[], missing=['Question requires the live general model planner; offline grammar does not support this wording.'])
    return AnswerPlan(question_id=question_id, fact_ids=list(dict.fromkeys(refs)), steps=steps,
                      answer_template=template, assumptions=assumptions, missing=[])

class PracticeEngine:
    def answer_batch(self, path, extraction, questions):
        from question_engine import GroundingError
        answers = {}
        for q in questions:
            plan = plan_practice(q['question_id'], q['question'], extraction)
            try: answers[q['question_id']] = execute_plan(plan, q['question'], extraction)
            except GroundingError as exc:
                answers[q['question_id']] = {'answer': 'This cannot be established from the selected readable practice evidence.',
                    'missing': [str(exc)], 'sources': plan.fact_ids, 'calculations': []}
        return extraction, answers
