"""Create clearly labelled practice templates from data, never official results."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from csv_pipeline import discover_images, image_for, serialize, L1, L2
from schemas import Bill, Extraction
from normalization import printed_decimal
from storage import save_json, atomic_text, digest

ROOT = Path(__file__).resolve().parents[1]

QUESTIONS = [
    'What percentage of the printed current bill consists of taxes?',
    'How much extra is the highest printed after-due amount compared with the within-due amount?',
    'Which month has the highest units in the printed historical period?',
    'Which month has the lowest units in the printed historical period?',
    'What is the average consumption across the printed historical months?',
    'What is the total consumption across the printed historical months?',
    'How many printed historical months have consumption above 200 kWh?',
    'How many printed historical months have consumption below 100 kWh?',
    'What is the average billed amount across the printed billing history?',
    'What is the difference between the current and previous meter readings?',
    'What is the printed arrears amount, preserving any credit sign?',
    'What is the bill due date?'
]

def next_month(start, offset):
    year, month = map(int, start.split('-'))
    n = year*12 + month-1 + offset
    return f'{n//12:04d}-{n%12+1:02d}'

def build(bills):
    data = json.loads((ROOT/'practice/selected_transcriptions.json').read_text(encoding='utf-8'))
    images = discover_images(bills)
    level1, level2 = [], []
    for bill_id, selected in data['bills'].items():
        path = image_for(images, bill_id)
        official = {name: [] if name in ('charges', 'taxes') else None for name in Bill.model_fields}
        official['provider'] = selected['provider']
        facts = []
        def fact(fid, value, unit='kWh', section='Bill history', kind='number', label=None):
            facts.append({'id':fid, 'label':label or fid, 'value':value, 'unit':unit,
                          'kind':kind, 'section':section, 'printed_text':value or 'Unreadable / blank',
                          'confidence':'medium' if value is not None else 'unreadable', 'bbox':None})
        fact('provider', selected['provider'], '', 'Provider logo/header', 'text')
        for fid, value in selected['facts'].items():
            unit = 'kWh' if fid in ('units_consumed', 'previous_reading', 'current_reading') else 'PKR'
            kind = 'date' if fid in ('reading_date', 'issue_date', 'due_date') else 'number'
            section = 'Meter information' if unit == 'kWh' else 'Bill summary / charges breakdown'
            fact(fid, value, '' if kind == 'date' else unit, section, kind)
            if fid in official:
                official[fid] = value if kind == 'date' else float(printed_decimal(value))
        rows = {}
        for i, units in enumerate(selected['historical_units']):
            month = next_month(selected['history_start'], i)
            fid = 'history_' + month.replace('-', '_') + '_units'
            fact(fid, units, label=month+' usage')
            rows[month] = {'month':month, 'month_label':month, 'units_fact':fid, 'billed_fact':None, 'payment_fact':None}
        for month, billed, payment in selected['billing_history']:
            row = rows.setdefault(month, {'month':month, 'month_label':month, 'units_fact':None, 'billed_fact':None, 'payment_fact':None})
            for suffix, val in [('billed', billed), ('payment', payment)]:
                fid = 'history_' + month.replace('-', '_') + '_' + suffix
                fact(fid, val, 'PKR', 'Billing and payment history', label=month+' '+suffix)
                row[suffix+'_fact'] = fid
        extraction = Extraction.model_validate({'bill':official, 'evidence':{
            'facts':facts, 'history':list(rows.values()), 'history_complete':True,
            'net_metering':selected['net_metering'],
            'missing':['Only selected manual transcriptions supplied; full live extraction not performed.'],
            'ambiguities':['PRACTICE ONLY: selected evidence is unlabelled and not verified official ground truth.']}})
        save_json(ROOT/'practice/reviewed_evidence'/f'{bill_id}.json', {
            'practice_only':True, 'image_sha256':digest(path.read_bytes()),
            'method':'Codex visual review, selected manual transcription; not runtime LLM extraction.',
            'extraction':extraction.model_dump(mode='json')})
        level1.append({'bill_id':bill_id, 'json':''})
        for i, question in enumerate(QUESTIONS, 1):
            level2.append({'bill_id':bill_id, 'question_id':f'practice_{i:02d}', 'question':question, 'answer':''})
    atomic_text(ROOT/'practice/templates/level1.csv', serialize(level1, L1))
    atomic_text(ROOT/'practice/templates/level2.csv', serialize(level2, L2))
    atomic_text(ROOT/'practice/README.txt', data['notice'] + '\nThese 60 representative questions are NOT competition guide questions or official test questions.\n')
    print('Created PRACTICE ONLY templates: five bills, sixty questions. No official rows synthesized.')

if __name__ == '__main__':
    build(sys.argv[1] if len(sys.argv)>1 else ROOT/'train-20261010T055743Z-1-001/train/bills')
