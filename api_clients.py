"""Official SDK calls, bounded retries and opt-in verification spending estimates."""
import base64
import json
import logging
import time
import random
import threading
from decimal import Decimal
from pathlib import Path
from pydantic import ValidationError
import httpx
from config import Settings
from storage import save_json

log = logging.getLogger(__name__)

class ProviderError(RuntimeError):
    pass

class GoogleClient:
    def __init__(self, settings: Settings):
        settings.require_primary()
        from google import genai
        from google.genai import types
        self.settings, self.types = settings, types
        self.primary = genai.Client(api_key=settings.primary,
            http_options=types.HttpOptions(timeout=120_000,
                retry_options=types.HttpRetryOptions(attempts=1)))
        self.backup = None
        if settings.backup and settings.backup_independent and settings.backup != settings.primary:
            self.backup = genai.Client(api_key=settings.backup,
                http_options=types.HttpOptions(timeout=120_000,
                    retry_options=types.HttpRetryOptions(attempts=1)))
        self.checked = False
        self.rate_lock = threading.Lock()
        self.last_request = 0.0
        self.stats_lock = threading.Lock()
        self.stats = {'calls': 0, 'seconds': 0.0, 'input_tokens': 0, 'output_tokens': 0}

    def _record(self, seconds, response):
        """Usage accounting only; never stores prompts, images or provider payloads."""
        usage = getattr(response, 'usage_metadata', None)
        lock = getattr(self, 'stats_lock', None)
        if lock is None: return
        with lock:
            self.stats['calls'] += 1
            self.stats['seconds'] += seconds
            self.stats['input_tokens'] += int(getattr(usage, 'prompt_token_count', 0) or 0)
            self.stats['output_tokens'] += int(getattr(usage, 'candidates_token_count', 0) or 0)

    def check_model(self):
        if not self.checked:
            self._retry(lambda client: client.models.get(model=self.settings.model))
            self.checked = True

    def _retry(self, call):
        last_code = None
        for attempt in range(self.settings.retries + 1):
            try:
                with self.rate_lock:
                    interval = getattr(self.settings, 'min_request_interval', 4.2)
                    remaining=interval-(time.monotonic()-self.last_request)
                    if remaining>0: time.sleep(remaining)
                    self.last_request=time.monotonic()
                return call(self.primary)
            except Exception as exc:
                # Never log raw provider exceptions: they can contain headers, keys or data.
                last_code = getattr(exc, 'code', None) or getattr(exc, 'status_code', None)
                transient = last_code in (429, 500, 502, 503, 504) or isinstance(exc, (TimeoutError, ConnectionError, httpx.TransportError))
                if not transient:
                    raise ProviderError(f'Google request failed ({type(exc).__name__}, status={last_code}); check model/account/request.') from None
                if attempt < self.settings.retries:
                    log.warning('Google transient error status=%s; bounded retry %s', last_code, attempt + 1)
                    # Exponential backoff with jitter avoids synchronized retries from worker threads.
                    time.sleep(min(2 ** attempt, 16) + random.uniform(0, 0.5))
        # No quota-key rotation, including when independence is configured.
        if self.backup is not None and last_code in (500, 502, 503, 504):
            try: return call(self.backup)
            except Exception as exc:
                raise ProviderError(f'Independent backup unavailable ({type(exc).__name__}).') from None
        raise ProviderError(f'Google retries exhausted (status={last_code}); checkpoint retained. No quota rotation.')

    def generate(self, prompt, schema, images=()):
        self.check_model()
        contents = [prompt]
        for image_bytes, mime in images:
            contents.append(self.types.Part.from_bytes(data=image_bytes, mime_type=mime))
        for parse_attempt in range(2):
            started = time.monotonic()
            response = self._retry(lambda client: client.models.generate_content(
                model=self.settings.model, contents=contents,
                config=self.types.GenerateContentConfig(temperature=0,
                    max_output_tokens=18000, response_mime_type='application/json',
                    automatic_function_calling=self.types.AutomaticFunctionCallingConfig(disable=True),
                    response_json_schema=schema.model_json_schema())))
            self._record(time.monotonic() - started, response)
            if not response.text:
                raise ProviderError('Google returned no JSON; no fabricated fallback.')
            try: return schema.model_validate_json(response.text)
            except ValidationError as exc:
                details = ['.'.join(map(str, err['loc'])) + ': ' + err['type'] for err in exc.errors(include_input=False, include_url=False)]
                error = '; '.join(details[:20])
            except ValueError:
                error = 'invalid JSON'
            if parse_attempt == 0:
                log.warning('Schema repair with the same configured model: %s', error)
                contents[0] += '\nYour last response failed validation. Correct these exact schema errors, with no invented data: ' + error + '\nUse ISO dates, omit zero charge/tax lines, and use exactly the provided fact IDs. Values for Fact are strings or null, not JSON numbers.'
            else:
                raise ProviderError('Google JSON failed strict schema validation: ' + error + '. No key switch for parsing errors.') from None

class OpenAIVerifier:
    """Sequential single-process estimated ledger. Not a guaranteed account spending cap."""
    def __init__(self, settings):
        self.settings = settings
        self.ledger = settings.cache_dir / 'openai_spend.json'

    def verify(self, prompt, schema, images):
        if not self.settings.verification or not self.settings.openai_key:
            return None
        from openai import OpenAI
        try:
            spent = Decimal(json.loads(self.ledger.read_text())['estimated_usd']) if self.ledger.exists() else Decimal(0)
            if not spent.is_finite() or spent < 0: raise ValueError('Invalid spend ledger')
        except (ValueError, OSError, KeyError, ArithmeticError):
            log.warning('Verification skipped: spend ledger unreadable.')
            return None
        # Conservative input estimate includes image tiles; reserve before a call. On
        # failure retain reservation, since an interrupted request might be billed.
        input_estimate = len(prompt.encode('utf-8')) + 12000 * len(images)
        reserve = Decimal(input_estimate) * Decimal('0.4') / 1_000_000 + Decimal(18000) * Decimal('1.6') / 1_000_000
        if spent + reserve > self.settings.budget:
            log.info('Verification skipped: estimated budget reached.')
            return None
        save_json(self.ledger, {'estimated_usd': str(spent + reserve), 'guaranteed_cap': False})
        content = [{'type': 'input_text', 'text': prompt}]
        for data, mime in images:
            content.append({'type': 'input_image', 'image_url': f'data:{mime};base64,' + base64.b64encode(data).decode(), 'detail': 'high'})
        try:
            with OpenAI(api_key=self.settings.openai_key, max_retries=0, timeout=120) as client:
                response = client.responses.parse(model=self.settings.verification_model,
                    input=[{'role': 'user', 'content': content}], text_format=schema,
                    temperature=0, max_output_tokens=18000)
            usage = response.usage
            if usage:
                actual = Decimal(usage.input_tokens) * Decimal('0.4') / 1_000_000 + Decimal(usage.output_tokens) * Decimal('1.6') / 1_000_000
                save_json(self.ledger, {'estimated_usd': str(spent + actual), 'guaranteed_cap': False})
            return response.output_parsed
        except Exception as exc:
            log.warning('Optional verification unavailable (%s); Gemini pipeline continues.', type(exc).__name__)
            return None
