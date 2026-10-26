"""Wait for stable complete official inputs; process once, then exit."""
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from csv_pipeline import read_template, discover_images, validate_inputs, L1, L2

PAKISTAN = timezone(timedelta(hours=5))

def wait_for_templates(bills, level1, level2, callback, release_time=None, poll=5, timeout=None):
    if not 1 <= poll <= 60: raise ValueError('Poll interval must be between one and sixty seconds')
    deadline = time.monotonic() + timeout if timeout is not None else None
    previous = None
    last_notice = None
    while True:
        if deadline is not None and time.monotonic() >= deadline:
            raise TimeoutError('Watch timeout: no complete official dataset was processed')
        if release_time and datetime.now(PAKISTAN) < release_time:
            notice = 'Waiting for configured Pakistan release time.'
            previous = None
        else:
            try:
                images = discover_images(bills)
                l1, l2 = read_template(level1, L1), read_template(level2, L2)
                validate_inputs(l1, l2, images, official=True)
                paths = [Path(level1), Path(level2), *images.values()]
                signature = tuple((str(p), p.stat().st_size, p.stat().st_mtime_ns) for p in paths)
                if signature == previous:
                    return callback()
                previous = signature
                notice = 'Official templates found; checking that input files are stable.'
            except (FileNotFoundError, OSError, ValueError) as exc:
                previous = None
                notice = 'Waiting for complete official templates and images: ' + str(exc)
        if notice != last_notice:
            print(notice, flush=True)
            last_notice = notice
        time.sleep(poll)
