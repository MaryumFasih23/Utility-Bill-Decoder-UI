import hashlib
import json
import os
from pathlib import Path

def digest(*parts):
    h = hashlib.sha256()
    for part in parts:
        encoded = part if isinstance(part, bytes) else str(part).encode('utf-8')
        h.update(len(encoded).to_bytes(8, 'big'))
        h.update(encoded)
    return h.hexdigest()

def atomic_text(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(text, encoding='utf-8', newline='')
    os.replace(temp, path)

def save_json(path: Path, data):
    atomic_text(path, json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False))

class Cache:
    def __init__(self, root: Path, enabled=True):
        self.root, self.enabled = root, enabled

    def get(self, key, schema):
        path = self.root / (key + '.json')
        if not self.enabled or not path.exists(): return None
        # Corrupt caches are invalidated; never substitute empty extraction.
        try: return schema.model_validate_json(path.read_text(encoding='utf-8'))
        except (ValueError, OSError): return None

    def put(self, key, result):
        if self.enabled: save_json(self.root / (key + '.json'), result.model_dump(mode='json'))
