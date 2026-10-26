"""Strict competition schema and separate, source-linked internal evidence."""
from datetime import date
from typing import Literal, Annotated
import re
from pydantic import BaseModel, ConfigDict, Field, field_validator

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)

ChargeType = Literal['energy', 'fixed', 'fpa', 'quarterly_adjustment', 'surcharge', 'meter_rent', 'subsidy', 'other']
TaxType = Literal['gst', 'electricity_duty', 'income_tax', 'municipal_tax', 'other_tax']

class Charge(Strict):
    type: ChargeType
    amount: float

class Tax(Strict):
    type: TaxType
    amount: float

class Bill(Strict):
    provider: Literal['KE', 'LESCO', 'IESCO'] | None
    tariff: str | None
    sanctioned_load_kw: float | None
    bill_month: str | None = Field(pattern=r'^\d{4}-\d{2}$', description='Normalized ISO year-month YYYY-MM, e.g. September 2026 is 2026-09. Not the raw printed spelling.')
    reading_date: str | None = Field(pattern=r'^\d{4}-\d{2}-\d{2}$', description='Normalized ISO YYYY-MM-DD, not raw printed spelling.')
    issue_date: str | None = Field(pattern=r'^\d{4}-\d{2}-\d{2}$', description='Normalized ISO YYYY-MM-DD, not raw printed spelling.')
    due_date: str | None = Field(pattern=r'^\d{4}-\d{2}-\d{2}$', description='Normalized ISO YYYY-MM-DD, not raw printed spelling. This is a date, unlike the payable monetary fields.')
    previous_reading: float | None
    current_reading: float | None
    units_consumed: float | None
    charges: list[Charge]
    total_charges: float | None = Field(description='A PRINTED electricity/net electricity section subtotal. Never calculate a subtotal by adding a separately printed FPA/adjustment. Never use current_bill as this field. Null if no subtotal is printed.')
    taxes: list[Tax] = Field(description='Only separately printed named tax lines. If only a combined Taxes amount is visible, this array MUST be empty; put that combined amount in total_taxes.')
    total_taxes: float | None
    current_bill: float | None
    arrears: float | None
    payable_within_due_date: float | None
    payable_after_due_date: float | None

    @field_validator('bill_month')
    @classmethod
    def month(cls, v):
        if v is not None:
            if not re.fullmatch(r'\d{4}-\d{2}', v):
                raise ValueError('bill_month must be YYYY-MM')
            date.fromisoformat(v + '-01')
        return v

    @field_validator('reading_date', 'issue_date', 'due_date')
    @classmethod
    def dates(cls, v):
        if v is not None:
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', v):
                raise ValueError('date must be YYYY-MM-DD')
            date.fromisoformat(v)
        return v

    @field_validator('charges', 'taxes')
    @classmethod
    def nonzero(cls, items):
        if any(x.amount == 0 for x in items):
            raise ValueError('Zero-value lines must be omitted')
        return items

class Fact(Strict):
    id: str
    label: str
    value: str | None
    kind: Literal['number', 'text', 'date', 'month']
    unit: str
    section: str
    printed_text: str
    confidence: Literal['high', 'medium', 'low', 'unreadable']
    bbox: list[Annotated[float, Field(ge=0, le=1)]] | None = Field(default=None, min_length=4, max_length=4,
        description='Normalized [left, top, right, bottom] in 0..1, with right>left and bottom>top. Unknown boxes MUST be null; never [0,0,0,0] or pixel coordinates.')

    @field_validator('id')
    @classmethod
    def safe_id(cls, value):
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.-]*', value):
            raise ValueError('Invalid fact ID')
        return value

    @field_validator('bbox')
    @classmethod
    def box(cls, value):
        if value is not None and (len(value) != 4 or not all(0 <= x <= 1 for x in value)
                                  or value[0] >= value[2] or value[1] >= value[3]):
            raise ValueError('bbox must be normalized [left, top, right, bottom]')
        return value

class HistoryRow(Strict):
    month_label: str
    month: str | None = Field(pattern=r'^\d{4}-\d{2}$', description='Normalized YYYY-MM when year is visible or unambiguously established from chart year headings.')
    units_fact: str | None = Field(pattern=r'^[A-Za-z_][A-Za-z0-9_.-]*$', description='REFERENCE to existing Fact.id for this month consumption, NOT the numeric value.')
    billed_fact: str | None = Field(pattern=r'^[A-Za-z_][A-Za-z0-9_.-]*$', description='REFERENCE to existing Fact.id for this month billed amount, NOT the numeric value.')
    payment_fact: str | None = Field(pattern=r'^[A-Za-z_][A-Za-z0-9_.-]*$', description='REFERENCE to existing Fact.id for this month payment, NOT the numeric value.')

class Evidence(Strict):
    facts: list[Fact]
    history: list[HistoryRow]
    history_complete: bool
    net_metering: bool
    missing: list[str]
    ambiguities: list[str]

    @field_validator('facts')
    @classmethod
    def unique(cls, facts):
        if len({f.id for f in facts}) != len(facts):
            raise ValueError('Duplicate evidence ID')
        return facts

class RawHistoryRow(Strict):
    month_label: str
    month: str | None = Field(pattern=r'^\d{4}-\d{2}$')
    units: str | None = Field(description='Printed consumption value itself; null if absent/unreadable. Preserve negative signs.')
    billed: str | None = Field(description='Printed billed amount itself; null if absent/unreadable.')
    payment: str | None = Field(description='Printed payment itself; blank is null, never zero.')
    section: str
    confidence: Literal['high', 'medium', 'low']
    unreadable_cells: list[Literal['units', 'billed', 'payment']]

class RawEvidence(Strict):
    facts: list[Fact]
    history: list[RawHistoryRow]
    history_complete: bool
    net_metering: bool
    missing: list[str]
    ambiguities: list[str]

class FactPatch(Strict):
    facts: list[Fact]

class HistoricalEvidence(Strict):
    history: list[RawHistoryRow]
    history_complete: bool

class Extraction(Strict):
    bill: Bill
    evidence: Evidence

class Resolution(Strict):
    fact_id: str
    confirmed: bool
    visible_printed_text: str | None

class Resolutions(Strict):
    resolutions: list[Resolution]

class Step(Strict):
    id: str
    op: Literal['sum', 'difference', 'average', 'count_above', 'count_below',
                'count_at_least', 'count_at_most', 'percentage', 'percentage_change',
                'maximum', 'minimum', 'multiply', 'divide', 'round', 'days_between', 'identity']
    # Operands: fact ID, result ID prefixed $, or question literal prefixed #.
    args: list[str]
    unit: str
    decimals: int = Field(default=2, ge=0, le=6)
    requires_complete_history: bool = False

class AnswerPlan(Strict):
    question_id: str
    fact_ids: list[str]
    steps: list[Step]
    answer_template: str
    assumptions: list[str]
    missing: list[str]
    recover_from_image: bool = Field(default=False, description='True only when a required fact is likely visible in the bill but missing/uncertain in the catalog. False for genuine absence or unspecified question interpretation.')

class Plans(Strict):
    plans: list[AnswerPlan]

class QAArtifact(Strict):
    extraction: Extraction
    plans: Plans
