"""Template-driven serialization; IDs, questions, headers and order are immutable."""
import csv
import io
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from schemas import Bill
from storage import atomic_text, save_json
from validation import reliability, check_private

L1 = ['bill_id', 'json']
L2 = ['bill_id', 'question_id', 'question', 'answer']

def read_template(path, expected):
    with Path(path).open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f, strict=True)
        if reader.fieldnames != expected:
            raise ValueError(f'{Path(path).name}: expected exact headers {expected}')
        rows = list(reader)
    if not rows or any(None in row or any(v is None for v in row.values()) for row in rows):
        raise ValueError('Empty/malformed CSV template')
    if any(not row['bill_id'].strip() for row in rows): raise ValueError('Empty bill ID')
    return rows

def discover_images(bills):
    images = {}
    for path in sorted(Path(bills).rglob('*')):
        if path.is_file() and path.suffix.lower() in ('.png', '.jpg', '.jpeg'):
            key = path.stem.casefold()
            if key in images: raise ValueError('Ambiguous duplicate image stem: ' + path.stem)
            images[key] = path
    return images

def image_for(images, bill_id):
    # IDs can be stems or exact filenames; never fuzzy match or infer a provider.
    if '/' in bill_id or '\\' in bill_id or Path(bill_id).name != bill_id:
        raise ValueError('Unsafe bill ID path')
    path = images.get(Path(bill_id).stem.casefold() if Path(bill_id).suffix.lower() in ('.jpg', '.jpeg', '.png') else bill_id.casefold())
    if path is None: raise ValueError('No corresponding bill image: ' + bill_id)
    return path

def validate_inputs(l1, l2, images, official=True):
    ids = [r['bill_id'] for r in l1]
    if len(set(ids)) != len(ids): raise ValueError('Duplicate Level 1 bill ID')
    if set(r['bill_id'] for r in l2) != set(ids): raise ValueError('Level 1/2 bill sets differ')
    keys = [(r['bill_id'], r['question_id']) for r in l2]
    if len(set(keys)) != len(keys): raise ValueError('Duplicate bill/question pair')
    if any(not r['question_id'] or not r['question'].strip() for r in l2): raise ValueError('Missing question ID/text')
    for bill_id in ids: image_for(images, bill_id)
    if official:
        if len(l1) != 10 or len(l2) != 120: raise ValueError('Official templates must have exactly 10 Level 1 and 120 Level 2 rows')
        if any(n != 12 for n in Counter(r['bill_id'] for r in l2).values()): raise ValueError('Official template must have 12 questions per bill')

def serialize(rows, columns):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=columns, lineterminator='\n', extrasaction='raise')
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()

def validate_outputs(l1_template, l2_template, out1, out2, images, official=True, secrets=()):
    for path in (out1,out2):
        complete_text=Path(path).read_text(encoding='utf-8')
        if any(secret and len(secret)>8 and secret in complete_text for secret in secrets):
            raise ValueError('Secret detected in CSV output')
    l1, l2 = read_template(out1, L1), read_template(out2, L2)
    validate_inputs(l1, l2, images, official)
    for source, actual, fill in [(l1_template, l1, 'json'), (l2_template, l2, 'answer')]:
        if len(source) != len(actual): raise ValueError('Output row count changed')
        for before, after in zip(source, actual):
            if any(before[col] != after[col] for col in before if col != fill):
                raise ValueError('Original row/ID/question changed')
            if not after[fill].strip(): raise ValueError('Missing result cell')
            check_private(after[fill], secrets)
    for row in l1:
        Bill.model_validate_json(row['json'])
        if '\n' in row['json'] or '\r' in row['json']: raise ValueError('JSON is not compact single-line')
    return {'valid': True, 'level1_rows': len(l1), 'level2_rows': len(l2), 'official': official}

def run_pipeline(bills, level1_template, level2_template, output, extractor, engine,
                 official=True, secrets=()):
    output = Path(output)
    if not official and not any(part.lower() == 'practice' or part.lower().startswith('practice_') for part in output.parts):
        raise ValueError('Practice output path must contain practice; never use output/level2.csv for a rehearsal')
    inputs = {Path(level1_template).resolve(), Path(level2_template).resolve()}
    if any((output / name).resolve() in inputs for name in ('level1.csv', 'level2.csv')):
        raise ValueError('Output must not overwrite official templates')
    l1 = read_template(level1_template, L1)
    l2 = read_template(level2_template, L2)
    images = discover_images(bills)
    validate_inputs(l1, l2, images, official)
    out1, out2 = [dict(r) for r in l1], [dict(r) for r in l2]
    reports = []
    def process_bill(item):
        i,row=item
        bill_id = row['bill_id']
        path = image_for(images, bill_id)
        extraction = extractor.extract(path)
        questions = [{'question_id': r['question_id'], 'question': r['question']} for r in l2 if r['bill_id'] == bill_id]
        extraction, answers = engine.answer_batch(path, extraction, questions)
        # Persist evidence + per-bill audits for resumable, reviewable work.
        # Digest is a safe filename even when a supplied bill ID contains punctuation.
        from storage import digest
        save_json(output / 'diagnostics' / (digest(bill_id) + '.json'),
                  {'bill_id': bill_id, 'extraction': extraction.model_dump(mode='json'), 'answers': answers})
        print(f'Processed {bill_id}: {len(questions)} questions', flush=True)
        return i,bill_id,path,extraction,answers
    with ThreadPoolExecutor(max_workers=3) as pool:
        for i,bill_id,path,extraction,answers in pool.map(process_bill,enumerate(l1)):
            out1[i]['json'] = json.dumps(extraction.bill.model_dump(mode='json'), ensure_ascii=False, separators=(',', ':'), allow_nan=False)
            for r in out2:
                if r['bill_id'] == bill_id: r['answer'] = answers[r['question_id']]['answer']
            reports.append({'bill_id': bill_id, 'warnings': reliability(extraction, path.name), 'answers': answers})
    staged = output / '.staging'
    p1, p2 = staged / 'level1.csv', staged / 'level2.csv'
    atomic_text(p1, serialize(out1, L1))
    atomic_text(p2, serialize(out2, L2))
    report = validate_outputs(l1, l2, p1, p2, images, official, secrets)
    for name in ('level1.csv', 'level2.csv'):
        atomic_text(output / name, (staged / name).read_text(encoding='utf-8'))
    validate_outputs(l1, l2, output/'level1.csv', output/'level2.csv', images, official, secrets)
    report['bills'] = reports
    report['practice_notice'] = None if official else 'PRACTICE ONLY. Unofficial questions and templates; not official scored results.'
    report['runtime'] = {'extractor':type(extractor).__name__,'question_engine':type(engine).__name__,
                         'model':getattr(getattr(extractor,'settings',None),'model',None)}
    save_json(output / 'validation_report.json', report)
    if not official:
        atomic_text(output/'PRACTICE_ONLY.txt',report['practice_notice']+'\nSee validation_report.json for extraction method, evidence, arithmetic and warnings.\n')
    return report
