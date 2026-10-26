from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
import pytest
import threading
from PIL import Image
from config import Settings
from api_clients import GoogleClient, OpenAIVerifier, ProviderError
from csv_pipeline import serialize, L1, L2
from storage import atomic_text
from watcher import wait_for_templates

class APIException(Exception):
    def __init__(self,code): self.code=code

def bare_client(settings):
    c=GoogleClient.__new__(GoogleClient)
    c.settings=settings;c.primary='primary';c.backup='backup'
    c.rate_lock=threading.Lock();c.last_request=0.0
    return c

def test_no_key_rotation_for_quota(monkeypatch):
    monkeypatch.setattr('api_clients.time.sleep',lambda _:None)
    c=bare_client(Settings(retries=2,backup_independent=True))
    calls=[]
    def fail(client): calls.append(client);raise APIException(429)
    with pytest.raises(ProviderError):c._retry(fail)
    assert calls==['primary']*3

def test_bad_request_not_retried():
    c=bare_client(Settings(retries=3))
    calls=[]
    def fail(client):calls.append(client);raise APIException(400)
    with pytest.raises(ProviderError):c._retry(fail)
    assert calls==['primary']

def test_independent_backup_only_on_service_outage():
    c=bare_client(Settings(retries=0,backup_independent=True))
    def outage(client):
        if client=='primary':raise APIException(503)
        return 'ok'
    assert c._retry(outage)=='ok'

def test_verification_disabled_never_calls(tmp_path):
    assert OpenAIVerifier(Settings(cache_dir=tmp_path)).verify('prompt',None,[]) is None
    assert not (tmp_path/'openai_spend.json').exists()

def test_optional_budget_preflight(tmp_path):
    v=OpenAIVerifier(Settings(verification=True,openai_key='not-a-real-key',budget=Decimal('0'),cache_dir=tmp_path))
    assert v.verify('prompt',None,[]) is None
    assert not (tmp_path/'openai_spend.json').exists()

@pytest.mark.parametrize('value',['broken','NaN','-1'])
def test_invalid_optional_ledger_skips_calls(tmp_path,value):
    import json
    (tmp_path/'openai_spend.json').write_text(json.dumps({'estimated_usd':value}))
    v=OpenAIVerifier(Settings(verification=True,openai_key='not-a-real-key',cache_dir=tmp_path))
    assert v.verify('prompt',None,[]) is None

def test_watcher_stable_files_and_single_callback(tmp_path,monkeypatch):
    bills=tmp_path/'bills';bills.mkdir()
    l1=[];l2=[]
    for i in range(10):
        bid=f'unseen_{i}'
        Image.new('RGB',(1,1)).save(bills/(bid+'.jpg'))
        l1.append({'bill_id':bid,'json':''})
        for j in range(12):l2.append({'bill_id':bid,'question_id':str(j),'question':'Unseen wording','answer':''})
    one,two=tmp_path/'one.csv',tmp_path/'two.csv'
    atomic_text(one,serialize(l1,L1));atomic_text(two,serialize(l2,L2))
    sleeps=[];calls=[]
    monkeypatch.setattr('watcher.time.sleep',lambda t:sleeps.append(t))
    def callback():calls.append(True);return 'processed'
    assert wait_for_templates(bills,one,two,callback,poll=1,timeout=10)=='processed'
    assert calls==[True] and sleeps==[1]

def test_watcher_incomplete_dataset_not_processed(tmp_path,monkeypatch):
    calls=[]
    monkeypatch.setattr('watcher.time.sleep',lambda _:None)
    with pytest.raises(TimeoutError): wait_for_templates(tmp_path,tmp_path/'one',tmp_path/'two',lambda:calls.append(True),poll=1,timeout=.01)
    assert calls==[]
