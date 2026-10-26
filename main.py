"""Windows-compatible entry point. Practice and official modes are deliberately explicit."""
import argparse
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from config import Settings
from storage import save_json
from csv_pipeline import run_pipeline

ROOT = Path(__file__).resolve().parent

def parser():
    p = argparse.ArgumentParser(description='Bill-grounded utility decoder')
    p.add_argument('--bills', default='test/bills')
    p.add_argument('--level1-template', default='test/csv/level1.csv')
    p.add_argument('--level2-template', default='test/csv/level2.csv')
    p.add_argument('--output', default='output')
    p.add_argument('--train', action='store_true')
    p.add_argument('--train-bill', help='Optional one-image training evaluation by discovered stem')
    p.add_argument('--no-cache', action='store_true')
    p.add_argument('--practice', action='store_true', help='Unofficial templates; relaxed row counts')
    p.add_argument('--offline-practice', action='store_true', help='Use selected reviewed evidence and limited offline intent grammar; requires --practice')
    p.add_argument('--reviewed-evidence', default='practice/reviewed_evidence')
    p.add_argument('--watch', action='store_true', help='Wait for stable official files, then run once')
    p.add_argument('--background', action='store_true', help='Start --watch in a hidden process with workspace logs')
    p.add_argument('--release-time', help='Optional local Pakistan timestamp, e.g. 2026-10-10T12:30:00')
    p.add_argument('--watch-timeout', type=float)
    return p

def live_components(args):
    from api_clients import GoogleClient, OpenAIVerifier
    from extractor import Extractor
    from question_engine import QuestionEngine
    settings = Settings.load()
    client = GoogleClient(settings)
    extractor = Extractor(settings, client, no_cache=args.no_cache, verifier=OpenAIVerifier(settings))
    return settings, extractor, QuestionEngine(settings, client, extractor, no_cache=args.no_cache)

def run(args):
    if args.background:
        if not args.watch: raise ValueError('--background requires --watch')
        if args.practice or args.offline_practice or args.train:
            raise ValueError('Background watch is official-only')
        command = [sys.executable, str(ROOT/'main.py'), *[arg for arg in sys.argv[1:] if arg != '--background']]
        flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
        with (ROOT/'watcher.log').open('w', encoding='utf-8') as log, (ROOT/'watcher_errors.log').open('w', encoding='utf-8') as errors:
            watcher_process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=errors,
                stdin=subprocess.DEVNULL, creationflags=flags, start_new_session=os.name != 'nt')
        (ROOT/'watcher.pid').write_text(str(watcher_process.pid), encoding='utf-8')
        print(f'Background watcher started (PID {watcher_process.pid}). Logs: watcher.log / watcher_errors.log')
        return {'watcher_pid':watcher_process.pid}
    if args.offline_practice and not args.practice:
        raise ValueError('Reviewed practice evidence is forbidden in official mode')
    if args.watch and (args.practice or args.offline_practice or args.train):
        raise ValueError('Watcher is for official inputs only')
    if args.train:
        from evaluate import evaluate_training
        settings, extractor, _ = live_components(args)
        images = Path(args.bills)
        if str(images) == str(Path('test/bills')):
            images = ROOT / 'train-20261010T055743Z-1-001/train/bills'
        return evaluate_training(images, extractor, ROOT/'diagnostics/training', [args.train_bill] if args.train_bill else None)
    if args.watch:
        from watcher import wait_for_templates, PAKISTAN
        release = datetime.fromisoformat(args.release_time).replace(tzinfo=PAKISTAN) if args.release_time else None
        def callback():
            # .env is deliberately loaded at release, so keys can be configured while waiting.
            return process(args)
        return wait_for_templates(args.bills, args.level1_template, args.level2_template,
                                  callback, release, timeout=args.watch_timeout)
    return process(args)

def process(args):
    if args.offline_practice:
        from practice_data import ReviewedPracticeExtractor
        from practice_planner import PracticeEngine
        settings = Settings.load()
        extractor = ReviewedPracticeExtractor(Path(args.reviewed_evidence))
        engine = PracticeEngine()
    else:
        settings, extractor, engine = live_components(args)
    result = run_pipeline(args.bills, args.level1_template, args.level2_template,
        args.output, extractor, engine, official=not args.practice,
        secrets=[settings.primary, settings.backup, settings.openai_key])
    print(f"Validated {result['level1_rows']} Level 1 and {result['level2_rows']} Level 2 rows. " +
          ('PRACTICE ONLY.' if args.practice else 'Official template output complete.'), flush=True)
    return result

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('google_genai').setLevel(logging.WARNING)
    try: run(parser().parse_args())
    except (RuntimeError, ValueError, OSError) as exc:
        # ProviderError already strips sensitive provider content. No traceback with payloads.
        print('ERROR: ' + str(exc), flush=True)
        raise SystemExit(1)
