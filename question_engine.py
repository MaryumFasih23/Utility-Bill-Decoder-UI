"""General model planning + deterministic execution + audited placeholder rendering."""
import json
import re
from decimal import Decimal
from pathlib import Path
from calculations import calculate, format_number
from evidence import fact_catalog, comparable_value
from extractor import source_images
from prompts import PLANNING_PROMPT, PROMPT_VERSION
from schemas import Plans, AnswerPlan, QAArtifact, FactPatch
from storage import Cache, digest
from validation import check_private

QA_VERSION = 'qa.v4'
TOKEN = re.compile(r'\{\{(fact|calc|label):([A-Za-z_][A-Za-z0-9_.-]*)\}\}')
ANY_TOKEN = re.compile(r'\{\{\s*([A-Za-z_][A-Za-z0-9_.-]*)\s*:\s*([A-Za-z_][A-Za-z0-9_.-]*)\s*\}\}')

class GroundingError(ValueError):
    pass

def execute_plan(plan: AnswerPlan, question: str, extraction):
    catalog = fact_catalog(extraction)
    used = set(plan.fact_ids)
    # A reference in the calculation AST is itself an explicit evidence citation.
    # Expand the redundant summary list mechanically; never invent new facts.
    used.update(arg for step in plan.steps for arg in step.args if arg in catalog)
    used.update(name for kind,name in TOKEN.findall(plan.answer_template) if kind=='fact' and name in catalog)
    if not used.issubset(catalog): raise GroundingError('Plan references nonexistent facts')
    image_observation = not used and not plan.missing and not plan.steps
    if image_observation and not extraction.evidence.facts:
        raise GroundingError('Answer lacks bill evidence')
    if plan.missing:
        detail='; '.join(plan.missing)
        check_private(detail)
        return {'answer': 'The bill does not provide enough readable evidence to establish this answer. Missing or ambiguous: '+detail+'.',
                'missing': plan.missing, 'calculations': [], 'sources': sorted(used)}
    values = {}
    for fid in used:
        f = catalog[fid]
        if f.value is None or f.confidence in ('low', 'unreadable'):
            raise GroundingError('Required fact is unreadable: ' + fid)
        try: values[fid] = comparable_value(f)
        except ValueError: raise GroundingError('Invalid fact number: ' + fid) from None
    results, formats, labels, trace = {}, {}, {}, []
    question_numbers = {Decimal(x.replace(',', '')) for x in re.findall(r'[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?', question)}
    history_labels = {}
    if extraction.bill.bill_month:
        history_labels['units_consumed'] = extraction.bill.bill_month
    for row in extraction.evidence.history:
        for ref in (row.units_fact, row.billed_fact, row.payment_fact):
            if ref: history_labels[ref] = row.month or row.month_label
    for step in plan.steps:
        if step.id in results or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.-]*', step.id):
            raise GroundingError('Invalid/duplicate calculation ID')
        if step.requires_complete_history and not extraction.evidence.history_complete:
            raise GroundingError('Printed history was not completely recovered')
        operands = []
        controls=set()
        if step.op=='divide' and len(step.args)==2:
            first=step.args[0]
            alias=TOKEN.fullmatch(first)
            if alias and alias.group(1)=='calc': first='$'+alias.group(2)
            first=first.lstrip('$')
            prior=next((s for s in plan.steps if s.id==first and s.id in results),None)
            if prior and prior.op=='sum' and all(a in catalog for a in prior.args):
                controls.add(Decimal(len(prior.args)))
        for arg in step.args:
            alias = TOKEN.fullmatch(arg)
            if alias:
                kind, ref = alias.groups()
                if kind == 'calc': arg = '$' + ref
                elif kind == 'fact': arg = ref
            if arg in results and arg not in used: arg = '$' + arg
            if step.op == 'identity' and arg.lower() in ('true','false'):
                observed=str(extraction.evidence.net_metering).lower()
                if arg.lower()!=observed: raise GroundingError('Boolean conflicts with extracted visual evidence')
                operands.append(observed)
                continue
            if arg.startswith('$'):
                if arg[1:] not in results: raise GroundingError('Forward or missing calculation reference')
                operands.append(results[arg[1:]])
            elif arg.startswith('#'):
                try: value = Decimal(arg[1:].replace(',', ''))
                except Exception: raise GroundingError('Invalid literal') from None
                if value not in question_numbers and value not in controls and not (step.op.startswith('count_') and value in (0,1)):
                    raise GroundingError('Numeric assumption absent from question')
                operands.append(value)
            else:
                if arg in used:
                    operands.append(values[arg])
                elif re.fullmatch(r'[+-]?\d+(?:\.\d+)?',arg) and (Decimal(arg) in question_numbers or Decimal(arg) in controls or
                      (step.op.startswith('count_') and Decimal(arg) in (0,1))):
                    operands.append(Decimal(arg))
                else: raise GroundingError('Operand is not an existing cited fact or question literal: ' + arg)
        if step.op in ('percentage','percentage_change','divide') and len(operands)==2 and operands[1]==0:
            return {'answer':'This calculation is undefined because the printed denominator is zero.',
                    'missing':['Nonzero denominator'], 'calculations':trace, 'sources':sorted(used)}
        try: result = calculate(step.op, operands)
        except (ValueError, ArithmeticError): raise GroundingError('Invalid arithmetic operation') from None
        results[step.id] = result
        formats[step.id] = format_number(result, step.decimals) if isinstance(result,Decimal) else str(result)
        if step.op in ('maximum', 'minimum'):
            tied = [history_labels[arg] for arg, value in zip(step.args, operands)
                    if value == result and arg in history_labels]
            labels[step.id] = ', '.join(tied)
        trace.append({'id': step.id, 'operation': step.op, 'operands': step.args,
                      'operand_values': [str(v) for v in operands], 'exact_result': str(result),
                      'formatted_result': formats[step.id], 'unit': step.unit})
    template = plan.answer_template
    if plan.assumptions: template += ' Assumption: ' + ' '.join(plan.assumptions)
    # Canonicalize a bare placeholder only when it is an existing cited source fact.
    template=re.sub(r'\{\{([A-Za-z_][A-Za-z0-9_.-]*)\}\}',
                    lambda m:'{{fact:'+m.group(1)+'}}' if m.group(1) in used else m.group(0),template)
    def canonical_placeholder(match):
        kind,name=match.groups()
        if kind in ('fact','calc','label'): return '{{'+kind+':'+name+'}}'
        # Normalize presentation aliases only when the target is already verified.
        if name in results and (kind==name or kind in ('result','calculation','value','month')):
            is_month = name in labels and labels[name] and ('month' in question.lower() or kind=='month')
            return '{{'+('label' if is_month else 'calc')+':'+name+'}}'
        if kind=='value' and name in values: return '{{fact:'+name+'}}'
        return match.group(0)
    template=ANY_TOKEN.sub(canonical_placeholder,template)
    literal = TOKEN.sub('', template)
    # Validate plain numeric prose against source/calculation/question values as well
    # as placeholders. This handles natural threshold wording without outsourcing math.
    verified_numbers = set(question_numbers)
    verified_numbers.update(v for v in values.values() if isinstance(v,Decimal))
    verified_numbers.update(Decimal(v) for v in formats.values() if re.fullmatch(r'[+-]?\d+(?:\.\d+)?',v))
    for step in plan.steps:
        historical_operands={a for a in step.args if a in history_labels}
        if historical_operands: verified_numbers.add(Decimal(len(historical_operands)))
        if step.op in ('average','sum') and all(a in catalog for a in step.args):
            verified_numbers.add(Decimal(len(step.args)))
    visible_dates={str(v) for v in values.values() if isinstance(v,str)}
    visible_dates.update(f.value for f in catalog.values() if f.value and f.kind in ('date','month'))
    visible_dates.update(r.month for r in extraction.evidence.history if r.month)
    visible_dates.update(history_labels[arg] for step in plan.steps for arg in step.args if arg in history_labels)
    for source_text in sorted(visible_dates,key=len,reverse=True):
        if re.fullmatch(r'\d{4}-\d{2}(?:-\d{2})?',source_text):
            literal=literal.replace(source_text,'')
            from datetime import datetime
            parsed=datetime.strptime(source_text[:7],'%Y-%m')
            verified_numbers.add(Decimal(parsed.year))
            if len(source_text)==10:
                verified_numbers.add(Decimal(int(source_text[-2:])))
            verified_numbers.add(Decimal(parsed.month))
            literal=literal.replace(parsed.strftime('%B %Y'),'').replace(parsed.strftime('%b %Y'),'')
            for month_name in (parsed.strftime('%B'),parsed.strftime('%b')):
                literal=re.sub(r'\b'+month_name+r'[\s/-]*'+parsed.strftime('%y')+r'\b','',literal,flags=re.I)
    for f in catalog.values():
        if f.value and f.kind=='number' and '%' in f.unit and f.confidence not in ('low','unreadable'):
            verified_numbers.add(comparable_value(f))
        if f.id in used:
            literal=literal.replace(f.printed_text,'') if re.search(r'\d',f.printed_text) else literal
    verified_literals=[]
    for number in re.findall(r'[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?',literal):
        numeric=Decimal(number.replace(',',''))
        if numeric not in verified_numbers:
            raise GroundingError('Unverified numeric literal in answer prose: '+number)
        verified_literals.append(number)
    if '{{' in literal or '}}' in literal: raise GroundingError('Unrecognized answer placeholder; use only {{fact:id}}, {{calc:step_id}} or {{label:extremum_step_id}}')
    def replace(match):
        kind, name = match.groups()
        if kind == 'fact':
            if name not in used: raise GroundingError('Uncited answer fact')
            # Number formatting preserves source decimal precision, normalized CR sign.
            return str(values[name])
        if kind == 'calc':
            if name not in formats: raise GroundingError('Missing answer calculation')
            return formats[name]
        if name not in labels or not labels[name]: raise GroundingError('No grounded month label for extrema')
        return labels[name]
    answer = TOKEN.sub(replace, template).strip()
    # Numeric extrema alone do not answer a request for the month. The label is
    # determined by Python, including ties, rather than inferred in prose.
    asks_month=bool(re.search(r'\b(?:which|what)\s+month\b|\bby\s+month\b',question,re.I))
    if asks_month:
        if len(labels)==1 and next(iter(labels.values())):
            winner=next(iter(labels.values()))
            answer=re.sub(r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\b',winner,answer)
        for winning_labels in dict.fromkeys(labels.values()):
            if winning_labels and winning_labels not in answer:
                answer+=' Month(s): '+winning_labels+'.'
    if not answer: raise GroundingError('Empty answer')
    check_private(answer)
    sources = [{'id': fid, 'section': catalog[fid].section,
                'printed_text': catalog[fid].printed_text} for fid in sorted(used)]
    if image_observation:
        sources.append({'id':'original_image_observation','section':'Original bill image',
                        'printed_text':'Qualitative visual interpretation; no numerical claims.'})
    return {'answer': answer, 'missing': [], 'calculations': trace,
            'verified_prose_numbers':verified_literals,
            'sources': sources}

class QuestionEngine:
    def __init__(self, settings, client, extractor, no_cache=False):
        self.settings, self.client, self.extractor = settings, client, extractor
        self.cache = Cache(settings.cache_dir / 'plans', not no_cache)
        self.drafts = Cache(settings.cache_dir / 'plan_drafts', not no_cache)

    def answer_batch(self, path: Path, extraction, questions):
        # Bill ID grouping done by pipeline; never send facts from another bill.
        key = digest(path.read_bytes(), extraction.model_dump_json(), json.dumps(questions, ensure_ascii=False),
                     self.settings.model, PROMPT_VERSION, QA_VERSION, json.dumps(Plans.model_json_schema(), sort_keys=True))
        cached = self.cache.get(key, QAArtifact) or self.drafts.get(key, QAArtifact)
        plans = cached.plans if cached else None
        if cached: extraction = cached.extraction
        prompt = PLANNING_PROMPT + '\nEvidence:\n' + extraction.model_dump_json() + '\nQuestions:\n' + json.dumps(questions, ensure_ascii=False)
        calendar=[{'month':r.month,'label':r.month_label,'units':r.units_fact,
                   'billed':r.billed_fact,'payment':r.payment_fact} for r in extraction.evidence.history]
        prompt+='\nCalendar index (source-linked; use exact months):\n'+json.dumps(calendar)
        prompt+='''\nFINAL INTERPRETATION AUDIT: same month last year MUST mean exactly
the bill month minus one year, never a closest-month proxy. If absent, say unavailable.
For a hypothetical using last month consumption, multiply a bill-derived rate by
last month's units, never current units. For next month seasonal forecasts use the
NEXT calendar month last year, not the current month last year. For trend questions
report the actual direction correctly: a negative difference means decrease; a
positive difference means increase. State the selected three-month period accurately.
If only recent billing/payment months are visible, explain that limitation and give
the available monthly budget estimate rather than inventing full-year payment data.
Use exact question-specified month ranges for seasonal calculations.'''
        if plans is None:
            plans = self.client.generate(prompt, Plans, source_images(path))
        self.check_ids(plans, questions)
        missing = sorted({item for plan in plans.plans if plan.recover_from_image for item in plan.missing}) if not cached else []
        if missing:
            recovered = self.extractor.extract(path, focus='Recover these question facts if visible: ' + '; '.join(missing))
            extraction = recovered
            prompt = PLANNING_PROMPT + '\nRecovered evidence:\n' + extraction.model_dump_json() + '\nQuestions:\n' + json.dumps(questions, ensure_ascii=False)
            plans = self.client.generate(prompt, Plans, source_images(path))
            self.check_ids(plans, questions)
        self.drafts.put(key,QAArtifact(extraction=extraction,plans=plans))
        question_map = {q['question_id']: q['question'] for q in questions}
        failures = []
        for p in plans.plans:
            try: execute_plan(p, question_map[p.question_id], extraction)
            except GroundingError as exc: failures.append(p.question_id + ': ' + str(exc))
        if failures:
            # One bounded semantic repair, same bill/image. No key switch for planner bugs.
            repair = prompt + '\nRepair these grounding errors. Do not guess.\n' + json.dumps(failures) + '\nEarlier plans:\n' + plans.model_dump_json()
            plans = self.client.generate(repair, Plans, source_images(path))
            self.check_ids(plans, questions)
            self.drafts.put(key,QAArtifact(extraction=extraction,plans=plans))
        remaining=[]
        for p in plans.plans:
            try: execute_plan(p,question_map[p.question_id],extraction)
            except GroundingError as exc: remaining.append(p.question_id+': '+str(exc))
        if remaining:
            patch_prompt='''Reread this original bill to recover non-identifying facts needed
for its customer questions. Return FactPatch. Include all printed late-payment date
windows, surcharge percentages and amounts, FCA/FPA reference month, chart labels,
and any unclear values. Use new descriptive fact IDs. Numeric values are exact printed
strings, dates ISO, window text as printed; never calculate or infer missing digits.
No names, addresses, account/reference/consumer/meter serial identifiers.
Grounding errors to address: '''+json.dumps(remaining)
            patch=self.client.generate(patch_prompt,FactPatch,source_images(path))
            facts={f.id:f for f in extraction.evidence.facts}
            for f in patch.facts:
                if f.id not in facts: facts[f.id]=f
            extraction=extraction.model_copy(update={'evidence':extraction.evidence.model_copy(update={'facts':list(facts.values())})})
            prompt=PLANNING_PROMPT+'\nExpanded source evidence:\n'+extraction.model_dump_json()+'\nQuestions:\n'+json.dumps(questions,ensure_ascii=False)
            plans=self.client.generate(prompt,Plans,source_images(path))
            self.check_ids(plans,questions)
            self.drafts.put(key,QAArtifact(extraction=extraction,plans=plans))
        answers = {}
        for p in plans.plans:
            try: answers[p.question_id] = execute_plan(p, question_map[p.question_id], extraction)
            except GroundingError as exc:
                # A planner defect is a processing failure, not missing bill evidence.
                raise RuntimeError('Unresolved grounding error for question ' + p.question_id + ': ' + str(exc)) from None
        self.cache.put(key, QAArtifact(extraction=extraction, plans=plans))
        return extraction, answers

    def answer_single(self, path: Path, extraction, question: str, question_id: str = 'user_q'):
        """Answer a single ad-hoc customer query using the grounded planning pipeline."""
        _, answers = self.answer_batch(path, extraction, [{'question_id': question_id, 'question': question}])
        return answers[question_id]

    @staticmethod
    def check_ids(plans, questions):
        ids = [p.question_id for p in plans.plans]
        expected = [q['question_id'] for q in questions]
        if len(ids) != len(set(ids)) or set(ids) != set(expected):
            raise RuntimeError('Planner omitted, duplicated or changed question IDs')
