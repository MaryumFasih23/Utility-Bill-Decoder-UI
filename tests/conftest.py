import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import json
import pytest
from schemas import Extraction

@pytest.fixture
def sample():
    reference = json.loads((Path(__file__).parent/'fixtures/kesc_0008_reference.json').read_text())
    facts = []
    for name, value in reference.items():
        if name in ('charges', 'taxes'): continue
        kind = 'number' if isinstance(value, (int, float)) else 'date' if name in ('reading_date','issue_date','due_date') else 'month' if name == 'bill_month' else 'text'
        facts.append({'id':name, 'label':name, 'value':str(value), 'kind':kind,
                      'unit':'PKR' if 'bill' in name or 'tax' in name or 'payable' in name else '',
                      'section':'TEST FIXTURE printed summary', 'printed_text':str(value),
                      'confidence':'high'})
    history = []
    for month, units in [('2025-12', 300), ('2026-01', 200), ('2026-02', 300)]:
        fid = 'h_' + month.replace('-', '_')
        facts.append({'id':fid, 'label':month, 'value':str(units), 'kind':'number', 'unit':'kWh',
                      'section':'TEST FIXTURE history', 'printed_text':str(units), 'confidence':'high'})
        history.append({'month':month, 'month_label':month, 'units_fact':fid, 'billed_fact':None, 'payment_fact':None})
    return Extraction.model_validate({'bill':reference, 'evidence':{'facts':facts, 'history':history,
        'history_complete':True, 'net_metering':False, 'missing':[], 'ambiguities':[]}})
