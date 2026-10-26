import json
from pathlib import Path
import pytest
from PIL import Image
from config import Settings
from csv_pipeline import (run_pipeline, serialize, read_template, validate_inputs,
                          validate_outputs, discover_images, L1, L2)
from question_engine import execute_plan
from schemas import AnswerPlan, Step
from storage import atomic_text, Cache
from main import parser, run

class FakeExtractor:
    def __init__(self,sample): self.sample=sample
    def extract(self,path): return self.sample

class FakeEngine:
    def answer_batch(self,path,extraction,questions):
        answers={}
        for q in questions:
            p=AnswerPlan(question_id=q['question_id'], fact_ids=['payable_after_due_date','payable_within_due_date'],
                steps=[Step(id='r',op='difference',args=['payable_after_due_date','payable_within_due_date'],unit='PKR')],
                answer_template='PKR {{calc:r}}.',assumptions=[],missing=[])
            answers[q['question_id']]=execute_plan(p,q['question'],extraction)
        return extraction,answers

def templates(tmp_path,n=10):
    bills=tmp_path/'bills'; bills.mkdir()
    l1=[];l2=[]
    for i in range(n):
        bid=f'arbitrary_{i}'
        Image.new('RGB',(2,2)).save(bills/(bid+'.png'))
        l1.append({'bill_id':bid,'json':''})
        for j in range(12):
            l2.append({'bill_id':bid,'question_id':f'question-{j}',
                       'question':'Unseen question, with "quotes"\nand Unicode: روپے?','answer':''})
    one,two=tmp_path/'l1.csv',tmp_path/'l2.csv'
    atomic_text(one,serialize(l1,L1));atomic_text(two,serialize(l2,L2))
    return bills,one,two,l1,l2

def test_full_official_shape_and_roundtrip(tmp_path,sample):
    bills,one,two,l1,l2=templates(tmp_path)
    out=tmp_path/'results'
    original_one,original_two=one.read_bytes(),two.read_bytes()
    report=run_pipeline(bills,one,two,out,FakeExtractor(sample),FakeEngine())
    assert report['level1_rows']==10 and report['level2_rows']==120
    assert one.read_bytes()==original_one and two.read_bytes()==original_two
    actual=read_template(out/'level2.csv',L2)
    assert all(r['answer']=='PKR 286.' for r in actual)
    assert [r['question'] for r in actual]==[r['question'] for r in l2]
    # Tampering must be caught by the output validator.
    actual[0]['question']='changed'
    atomic_text(out/'level2.csv',serialize(actual,L2))
    with pytest.raises(ValueError,match='changed'): validate_outputs(l1,l2,out/'level1.csv',out/'level2.csv',discover_images(bills))

def test_row_count_not_synthesized(tmp_path):
    bills,one,two,l1,l2=templates(tmp_path,5)
    with pytest.raises(ValueError,match='exactly'): validate_inputs(l1,l2,discover_images(bills))
    validate_inputs(l1,l2,discover_images(bills),False)

def test_missing_image(tmp_path):
    bills,one,two,l1,l2=templates(tmp_path)
    (bills/'arbitrary_0.png').unlink()
    with pytest.raises(ValueError,match='image'): validate_inputs(l1,l2,discover_images(bills))

def test_unsafe_practice_modes():
    with pytest.raises(ValueError): run(parser().parse_args(['--offline-practice']))
    with pytest.raises(ValueError): run(parser().parse_args(['--watch','--practice']))

def test_main_regular_mode_dispatch(monkeypatch):
    monkeypatch.setattr('main.process',lambda args:'processed')
    assert run(parser().parse_args([]))=='processed'

def test_practice_cannot_overwrite_official_location(tmp_path,sample):
    bills,one,two,_,_=templates(tmp_path,5)
    with pytest.raises(ValueError,match='Practice output'): run_pipeline(bills,one,two,tmp_path/'output',FakeExtractor(sample),FakeEngine(),False)

def test_output_cannot_overwrite_templates(tmp_path,sample):
    bills,one,two,_,_=templates(tmp_path)
    renamed=one.with_name('level1.csv');one.rename(renamed)
    with pytest.raises(ValueError,match='overwrite'): run_pipeline(bills,renamed,two,tmp_path,FakeExtractor(sample),FakeEngine())

def test_reject_unapproved_models():
    with pytest.raises(ValueError): Settings(model='gemini-pro')
    with pytest.raises(ValueError): Settings(verification_model='gpt-5-mini')
    assert not Settings().verification

def test_cache_schema_and_no_cache(tmp_path,sample):
    from schemas import Extraction
    cache=Cache(tmp_path)
    cache.put('key',sample)
    assert cache.get('key',Extraction).bill.current_bill==3430.24
    assert Cache(tmp_path,False).get('key',Extraction) is None
    atomic_text(tmp_path/'key.json','{"bad":true}')
    assert cache.get('key',Extraction) is None
