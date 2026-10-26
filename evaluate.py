"""Reference data is loaded only here, never by the production extractor."""
import json
from collections import Counter
from pathlib import Path
from csv_pipeline import discover_images, image_for
from storage import save_json
from validation import reliability

def compare_bill(actual, expected):
    matches, total, mismatches = 0, 0, []
    for field, value in expected.items():
        if field in ('charges', 'taxes'):
            def items(values): return Counter((x['type'], str(float(x['amount']))) for x in values)
            found, wanted = items(actual[field]), items(value)
            # Multiset matching preserves duplicates; printed order is not part of the score.
            denominator = max(sum(found.values()), sum(wanted.values()), 1)
            n = sum((found & wanted).values()) if found or wanted else 1
            matches += n
            total += denominator
            if found != wanted:
                mismatches.append({'field': field, 'missing_lines': list((wanted-found).elements()),
                                   'extra_lines': list((found-wanted).elements())})
        else:
            total += 1
            if actual.get(field) == value: matches += 1
            else: mismatches.append({'field': field, 'expected': value, 'actual': actual.get(field)})
    return {'matched_components': matches, 'total_components': total,
            'matching_score_percent': round(matches/total*100, 2),
            'all_exact': not mismatches, 'mismatches': mismatches,
            'score_definition': 'Each scalar is one component; each line item is one multiset component. Duplicate lines counted. Empty array is one component. Denominator is max(predicted,reference) line count.'}

def evaluate_training(bills, extractor, output, bill_ids=None):
    images = discover_images(bills)
    required = bill_ids or ['IESCO_0004', 'KESC_0004', 'KESC_0008', 'LESCO_0005', 'LESCO_0006']
    reports = []
    for bill_id in required:
        path = image_for(images, bill_id)
        try:
            result = extractor.extract(path)
            report = {'bill_id': bill_id, 'processed': True, 'warnings': reliability(result, path.name)}
            save_json(Path(output)/f'{bill_id}.extraction.json', result.model_dump(mode='json'))
            if bill_id == 'KESC_0008':
                expected = json.loads((Path(__file__).parent/'tests/fixtures/kesc_0008_reference.json').read_text())
                report['official_reference_evaluation'] = compare_bill(result.bill.model_dump(mode='json'), expected)
            else: report['accuracy'] = 'Not measured: no official labels supplied.'
        except (RuntimeError, ValueError, OSError) as exc:
            report = {'bill_id': bill_id, 'processed': False, 'error': str(exc)}
        reports.append(report)
        print(json.dumps(report, ensure_ascii=False), flush=True)
    save_json(Path(output)/'training_report.json', reports)
    if not all(r['processed'] for r in reports): raise RuntimeError('Training evaluation incomplete; see diagnostics/training/training_report.json')
    return reports
