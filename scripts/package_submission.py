"""Allowlist packaging: never includes .env, cache, images or environments."""
import shutil
import sys
import zipfile
import argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from csv_pipeline import read_template, validate_outputs, discover_images, L1, L2
from config import Settings

ROOT = Path(__file__).resolve().parents[1]

def package(include_results=False, bills='test/bills', level1_template='test/csv/level1.csv',
            level2_template='test/csv/level2.csv', output_dir='output'):
    source = ROOT/'source'
    source.mkdir(exist_ok=True)
    files = [*ROOT.glob('*.py'), ROOT/'README.md', ROOT/'.env.example',
             ROOT/'requirements.txt', ROOT/'requirements-lock.txt', ROOT/'start_watcher.ps1', ROOT/'pytest.ini',
             ROOT/'scripts/package_submission.py']
    if not include_results:
        files += [*(ROOT/'tests').rglob('*.py'), *(ROOT/'tests/fixtures').glob('*.json'),
                  ROOT/'scripts/generate_practice.py', ROOT/'practice/selected_transcriptions.json',
                  ROOT/'practice/README.txt']
    if include_results:
        cfg = Settings.load()
        validate_outputs(read_template(ROOT/level1_template, L1),
                         read_template(ROOT/level2_template, L2),
                         ROOT/output_dir/'level1.csv', ROOT/output_dir/'level2.csv',
                         discover_images(ROOT/bills), True,
                         [cfg.primary, cfg.backup, cfg.openai_key])
    archive = ROOT/('submission.zip' if include_results else 'source_ready.zip')
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for file in files:
            if not file.is_file(): continue
            relative = file.relative_to(ROOT)
            destination = source/relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(file, destination)
            z.write(destination, str(Path('source')/relative))
        if include_results:
            for name in ('level1.csv', 'level2.csv'):
                z.write(ROOT/output_dir/name, str(Path('output')/name))
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None: raise ValueError('ZIP integrity check failed')
        if include_results:
            required={'output/level1.csv','output/level2.csv','source/README.md',
                      'source/.env.example','source/main.py','source/requirements.txt'}
            if not required.issubset(set(z.namelist())): raise ValueError('Required submission files missing')
        for entry in z.namelist():
            if Path(entry).name == '.env': raise ValueError('Real environment file in archive')
            if include_results:
                data=z.read(entry).decode('utf-8')
                if any(s and len(s)>8 and s in data for s in (cfg.primary,cfg.backup,cfg.openai_key)):
                    raise ValueError('Credential detected in archive')
    if archive.stat().st_size > 15_000_000:
        raise ValueError('ZIP exceeds fifteen MB')
    print(f'{archive.name}: {archive.stat().st_size} bytes. ' + ('Official outputs included.' if include_results else 'Source only; official results pending.'))

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--include-results',action='store_true')
    parser.add_argument('--bills',default='test/bills')
    parser.add_argument('--level1-template',default='test/csv/level1.csv')
    parser.add_argument('--level2-template',default='test/csv/level2.csv')
    parser.add_argument('--output-dir',default='output')
    args=parser.parse_args()
    package(args.include_results,args.bills,args.level1_template,args.level2_template,args.output_dir)
