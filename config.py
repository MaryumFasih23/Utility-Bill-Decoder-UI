"""Configuration; only approved runtime models can pass these checks."""
import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from dotenv import dotenv_values

APPROVED = frozenset({'gemini-3.5-flash-lite', 'gemini-3.1-flash-lite',
                      'claude-haiku-4-5', 'gpt-4.1-mini', 'gpt-5-mini'})

@dataclass(frozen=True)
class Settings:
    primary: str = ''
    backup: str = ''
    backup_independent: bool = False
    model: str = 'gemini-3.1-flash-lite'
    provider: str = 'google'
    openai_key: str = ''
    verification: bool = False
    verification_model: str = 'gpt-4.1-mini'
    budget: Decimal = Decimal('1.00')
    retries: int = 3
    cache_dir: Path = Path('cache')
    # Free-tier Gemini allows 15 requests/minute; 4.2 s spacing keeps one process safe.
    # Paid accounts can lower this (e.g. 0) to remove artificial latency.
    min_request_interval: float = 4.2
    # Long-side pixel cap for images sent to the model. Phone photos above this
    # size add upload time without adding legible detail; crops are still upscaled.
    max_image_side: int = 3072

    def __post_init__(self):
        if self.model not in APPROVED or not self.model.startswith('gemini-'):
            raise ValueError('Primary model must be an approved Gemini ID; no automatic substitution.')
        if self.provider != 'google':
            raise ValueError('Only the Google primary provider is implemented.')
        if self.verification_model != 'gpt-4.1-mini':
            raise ValueError('Optional verification is restricted to gpt-4.1-mini.')
        if not self.budget.is_finite() or self.budget < 0 or not 0 <= self.retries <= 5:
            raise ValueError('Invalid budget or retry bound.')
        if not 0 <= self.min_request_interval <= 60:
            raise ValueError('MIN_REQUEST_INTERVAL must be between 0 and 60 seconds.')
        if not 768 <= self.max_image_side <= 8192:
            raise ValueError('MAX_IMAGE_SIDE must be between 768 and 8192 pixels.')

    @classmethod
    def load(cls):
        env = dict(dotenv_values(Path(__file__).parent / '.env'))
        env.update(os.environ)
        return cls(primary=env.get('GOOGLE_API_KEY_PRIMARY') or '',
                   backup=env.get('GOOGLE_API_KEY_BACKUP') or '',
                   backup_independent=(env.get('GOOGLE_BACKUP_INDEPENDENT') or 'false').lower() == 'true',
                   model=env.get('MODEL_NAME') or 'gemini-3.1-flash-lite',
                   provider=env.get('MODEL_PROVIDER') or 'google',
                   openai_key=env.get('OPENAI_API_KEY') or '',
                   verification=(env.get('OPENAI_VERIFICATION_ENABLED') or 'false').lower() == 'true',
                   verification_model=env.get('OPENAI_VERIFICATION_MODEL') or 'gpt-4.1-mini',
                   budget=Decimal(env.get('OPENAI_BUDGET_USD') or '1.00'),
                   retries=int(env.get('MAX_RETRIES') or '3'),
                   cache_dir=Path(env.get('CACHE_DIR') or 'cache'),
                   min_request_interval=float(env.get('MIN_REQUEST_INTERVAL') or '4.2'),
                   max_image_side=int(env.get('MAX_IMAGE_SIDE') or '3072'))

    def require_primary(self):
        if not self.primary or self.primary.startswith(('YOUR_', 'REPLACE_')):
            raise RuntimeError('Google key missing. Copy .env.example to .env and set GOOGLE_API_KEY_PRIMARY locally. OpenAI is not enabled as a fallback.')
