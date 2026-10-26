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

    def __post_init__(self):
        if self.model not in APPROVED or not self.model.startswith('gemini-'):
            raise ValueError('Primary model must be an approved Gemini ID; no automatic substitution.')
        if self.provider != 'google':
            raise ValueError('Only the Google primary provider is implemented.')
        if self.verification_model != 'gpt-4.1-mini':
            raise ValueError('Optional verification is restricted to gpt-4.1-mini.')
        if not self.budget.is_finite() or self.budget < 0 or not 0 <= self.retries <= 5:
            raise ValueError('Invalid budget or retry bound.')

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
                   cache_dir=Path(env.get('CACHE_DIR') or 'cache'))

    def require_primary(self):
        if not self.primary or self.primary.startswith(('YOUR_', 'REPLACE_')):
            raise RuntimeError('Google key missing. Copy .env.example to .env and set GOOGLE_API_KEY_PRIMARY locally. OpenAI is not enabled as a fallback.')
