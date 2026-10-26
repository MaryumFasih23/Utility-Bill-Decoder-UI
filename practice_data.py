"""Opt-in reviewed practice evidence, image-hash bound and barred from official CLI mode."""
import json
from pathlib import Path
from schemas import Extraction
from storage import digest

class ReviewedPracticeExtractor:
    def __init__(self, directory): self.directory = directory

    def extract(self, path):
        record = json.loads((self.directory/(path.stem + '.json')).read_text(encoding='utf-8'))
        if record.get('practice_only') is not True:
            raise ValueError('Reviewed data lacks PRACTICE ONLY marker')
        if record['image_sha256'] != digest(path.read_bytes()):
            raise ValueError('Reviewed practice evidence does not match source image content')
        return Extraction.model_validate(record['extraction'])
