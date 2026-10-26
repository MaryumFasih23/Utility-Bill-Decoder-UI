from decimal import Decimal
import pytest
from calculations import calculate, format_number
from normalization import printed_decimal

@pytest.mark.parametrize('text,expected', [('54770CR','-54770'), ('-0.53','-0.53'),
    ('(1,200.40)','-1200.40'), ('Rs. 3,430.24','3430.24'), ('−123','-123'), ('0','0')])
def test_printed_values(text, expected): assert printed_decimal(text) == Decimal(expected)

@pytest.mark.parametrize('text', ['1,23', '1O5', 'masked', '', 'NaN', 'Inf', '1e3', '1.2.3'])
def test_bad_numbers(text):
    with pytest.raises(ValueError): printed_decimal(text)

@pytest.mark.parametrize('op,values,expected', [
 ('sum',['0.1','0.2'],'0.3'), ('difference',['10','3'],'7'), ('average',['2','4'],'3'),
 ('percentage',['25','100'],'25'), ('percentage_change',['120','100'],'20'),
 ('count_above',['100','200','201','200'],'1'), ('count_below',['100','200','201','200'],'1'),
 ('count_at_least',['100','200','201','200'],'2'), ('count_at_most',['100','200','201','200'],'2'),
 ('maximum',['-100','-20'],'-20'), ('minimum',['-100','-20'],'-100'),
 ('multiply',['1.25','4'],'5'), ('divide',['5','2'],'2.5'), ('round',['1.255','2'],'1.26')])
def test_numeric_ops(op, values, expected): assert calculate(op, list(map(Decimal,values))) == Decimal(expected)

def test_zero_denominator():
    with pytest.raises(ValueError): calculate('percentage', [Decimal(1), Decimal(0)])

def test_empty_average():
    with pytest.raises(ValueError): calculate('average', [])

def test_dates(): assert calculate('days_between', ['2026-04-21','2026-04-07']) == 14

@pytest.mark.parametrize('value,digits,expected', [('100',2,'100'), ('100',0,'100'), ('0',2,'0'), ('1.255',2,'1.26'), ('-0.53',2,'-0.53')])
def test_format(value,digits,expected): assert format_number(Decimal(value),digits) == expected
