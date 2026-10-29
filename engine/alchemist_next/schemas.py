"""Typed P2 contracts. Decimal inputs are strings/integers, never binary floats."""
from __future__ import annotations
from datetime import datetime
from decimal import Decimal
from enum import Enum
from hashlib import sha256
import json
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, BeforeValidator, field_validator, model_validator


def decimal_input(v):
    if isinstance(v, (bool, float)):
        raise ValueError('Use a decimal string, not float/bool')
    d = Decimal(v)
    if not d.is_finite():
        raise ValueError('Non-finite price')
    return d


D = Annotated[Decimal, BeforeValidator(decimal_input)]


class Typed(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, validate_default=True)

    @field_validator('*', mode='after')
    @classmethod
    def aware_times(cls, v):
        if isinstance(v, datetime) and (v.tzinfo is None or v.utcoffset() is None):
            raise ValueError('Timezone-aware timestamps required')
        return v


def digest(v) -> str:
    if isinstance(v, BaseModel):
        v = v.model_dump(mode='json')
    return sha256(json.dumps(v, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


class Grade(str, Enum):
    PASS = 'PASS'
    FAIL = 'FAIL'
    UNKNOWN = 'UNKNOWN'
    NA = 'NOT_APPLICABLE'


class State(str, Enum):
    DATA = 'DATA_UNVERIFIED'
    PREPARED = 'PREPARED_PLAN'
    TRADE = 'TRADE_CANDIDATE'
    NONE = 'NO_VALID_SETUP'
    EXPIRED = 'EXPIRED'


class Bar(Typed):
    opened_at: datetime
    closed_at: datetime
    open: D
    high: D
    low: D
    close: D

    @model_validator(mode='after')
    def geometry(self):
        if not self.opened_at < self.closed_at or not (0 < self.low <= min(self.open, self.close) <= max(self.open, self.close) <= self.high):
            raise ValueError('Invalid OHLC/time ordering')
        return self


class Snapshot(Typed):
    symbol: str
    feed: str | None
    cursor: datetime
    mode: Literal[1, 9]
    timeframes: tuple[str, ...]
    source_hashes: tuple[str, ...]
    quote_ref: str | None
    context: Literal['REPLAY', 'SNAPSHOT'] = 'REPLAY'
    price_unit: str = 'XAUUSD_NATIVE'
    execution_mode: Literal[1,5,9] | None = None

    @field_validator('source_hashes')
    @classmethod
    def hashes(cls, v):
        if not v or any(len(s) != 64 or any(c not in '0123456789abcdef' for c in s) for s in v):
            raise ValueError('SHA256 source hashes required')
        return tuple(sorted(set(v)))

    @field_validator('timeframes')
    @classmethod
    def tfs(cls, v):
        if len(v) != len(set(v)):
            raise ValueError('Duplicate TF labels')
        return tuple(sorted(v))

    @property
    def snapshot_id(self):
        data=self.model_dump(mode='json')
        if self.execution_mode is None:data.pop('execution_mode')
        return digest(data)


class EvidenceRecord(Typed):
    id: str
    snapshot_id: str
    source_hash: str
    source_kind: Literal['OHLC', 'IMAGE', 'MANUAL', 'SYNTHETIC', 'POLICY', 'LEGACY_REPORT']
    locator: str
    tf: str
    at: datetime
    available_at: datetime
    state: Literal['OBSERVED', 'DERIVED', 'UNKNOWN']
    role: str
    value: D | None = None
    bar: Bar | None = None
    tag: str | None = None
    uncertainty: D | None = None
    parents: tuple[str, ...] = ()
    formula: Literal['ADD', 'SUB', 'MEAN'] | None = None

    @model_validator(mode='after')
    def provenance(self):
        if not self.id or not self.locator.strip() or len(self.source_hash) != 64:
            raise ValueError('Evidence requires ID/hash/source locator')
        if self.available_at < self.at:
            raise ValueError('Cannot know evidence before event')
        if self.state == 'UNKNOWN' and any(x is not None for x in (self.value, self.bar, self.tag)):
            raise ValueError('UNKNOWN cannot carry asserted values')
        if self.state != 'UNKNOWN' and sum(x is not None for x in (self.value, self.bar, self.tag)) != 1:
            raise ValueError('Exactly one value/bar/tag payload required')
        if self.state == 'DERIVED' and (self.value is None or len(self.parents) != 2 or self.formula is None):
            raise ValueError('Derived price requires 2 parents and formula')
        if self.state != 'DERIVED' and (self.parents or self.formula):
            raise ValueError('Only derived records have parents/formula')
        if self.uncertainty is not None and self.uncertainty < 0:
            raise ValueError('Negative uncertainty')
        return self


class SourceProof(Typed):
    file_name: str
    sha256: str
    pages: tuple[int, ...]
    scope: str
    reviewed_by: str


class ModelCard(Typed):
    id: str
    name: str
    version: str
    role: Literal['ENTRY_MODEL', 'POI', 'BACKLOG']
    source_status: Literal['VERIFIED_SCOPED', 'REVIEW_PARTIAL', 'ATTACHED_NOT_REVIEWED', 'MISSING_SOURCE']
    enabled: bool
    source_variant: str
    sources: tuple[SourceProof, ...] = ()
    dependencies: tuple[str, ...] = ()
    rules: tuple[str, ...]
    policy_overlays: tuple[str, ...]
    limitations: tuple[str, ...]
    execution_scopes: tuple[str, ...] = ('P3','P4')

    @model_validator(mode='after')
    def source_gate(self):
        if self.enabled and (self.source_status != 'VERIFIED_SCOPED' or not self.sources or self.role == 'BACKLOG'):
            raise ValueError('Cannot enable an unverified/backlog card')
        return self


class CandidateSeed(Typed):
    id: str
    model_id: str
    side: Literal['BUY', 'SELL']
    route: Literal['REVERSAL', 'CONTINUATION']
    refs: dict[str, str]
    entry_rule: Literal['NEAR_EDGE', 'CE'] = 'NEAR_EDGE'
    order_requested: Literal['AUTO', 'BUY_LIMIT', 'SELL_LIMIT', 'MARKET'] = 'AUTO'
    barrier_refs: tuple[str, ...] = ()
    leg_bar_refs: tuple[str, ...] = ()
    precision_refs: dict[str,str] = {}


class RouteCoverage(Typed):
    side: Literal['BUY', 'SELL']
    route: Literal['REVERSAL', 'CONTINUATION']
    evidence_ref: str
    start: datetime
    end: datetime
    status: Literal['COMPLETE', 'PARTIAL', 'NOT_REVIEWED']

    @model_validator(mode='after')
    def span(self):
        if self.start > self.end:
            raise ValueError('Reversed scan range')
        return self


class BrokerContext(Typed):
    symbol: str | None = None
    feed: str | None = None
    as_of: datetime | None = None
    bid: D | None = None
    ask: D | None = None
    tick_size: D | None = None
    min_distance: D | None = None
    max_spread: D | None = None
    max_quote_age_seconds: int | None = None
    fees: D | None = None
    risk_budget: D | None = None
    contract_size: D | None = None
    provenance: str | None = None
    # No defaults certify an asset, quote, budget or broker policy.


class Gate(Typed):
    name: str
    status: Grade
    reason: str
    evidence_ids: tuple[str, ...] = ()


class Candidate(Typed):
    seed: CandidateSeed
    snapshot_id: str
    card_hash: str
    policy_hash: str
    gates: tuple[Gate, ...]
    prices: dict[str, D | None]
    rr1: D | None
    rr2: D | None
    stop_points: D | None
    order: Literal['BUY_LIMIT', 'SELL_LIMIT', 'MARKET', 'NONE']
    state: State
    preferences: tuple[str, ...]
    incomplete_fields: tuple[str, ...]
    broker_checks: tuple[Gate, ...]
    live_ready: Literal[False] = False
    validation_digest: str | None = None


class Decision(Typed):
    snapshot_id: str
    evaluation_id: str
    policy_hash: str
    state: State
    selected_id: str | None
    candidates: tuple[Candidate, ...]
    reasons: tuple[str, ...]
    coverage: tuple[RouteCoverage, ...]
    coverage_complete: bool
    historical_ids: tuple[str, ...]
    perception: Literal['ANNOTATION_VALIDATED_NOT_PIXEL_VERIFIED'] = 'ANNOTATION_VALIDATED_NOT_PIXEL_VERIFIED'
    live_ready: Literal[False] = False


class LifecycleEvent(Typed):
    status: Literal['SIGNAL_CANDIDATE', 'SUBMITTED', 'FILLED', 'CLOSED', 'CANCELLED', 'EXPIRED']
    at: datetime
    evidence_ref: str
    authority: Literal['SNAPSHOT', 'SIMULATION', 'BROKER']


class Lifecycle(Typed):
    candidate_id: str
    events: tuple[LifecycleEvent, ...]

    @model_validator(mode='after')
    def transitions(self):
        allowed = {None: {'SIGNAL_CANDIDATE'}, 'SIGNAL_CANDIDATE': {'SUBMITTED','EXPIRED'},
                   'SUBMITTED': {'FILLED','CANCELLED','EXPIRED'}, 'FILLED': {'CLOSED'}}
        prev = None
        when = None
        for event in self.events:
            if not event.evidence_ref or event.status not in allowed.get(prev, set()) or (when and event.at < when):
                raise ValueError('Invalid lifecycle or missing evidence')
            if event.status in {'SUBMITTED','FILLED','CLOSED','CANCELLED'} and event.authority == 'SNAPSHOT':
                raise ValueError('Snapshot cannot attest broker/simulation execution')
            prev, when = event.status, event.at
        return self

    @property
    def verified_closed(self):
        return bool(self.events) and self.events[-1].status == 'CLOSED' and all(e.authority == 'BROKER' for e in self.events[1:])


class AnalysisInput(Typed):
    snapshot: Snapshot
    evidence: tuple[EvidenceRecord, ...]
    seeds: tuple[CandidateSeed, ...]
    coverage: tuple[RouteCoverage, ...]
    broker: BrokerContext = BrokerContext()
    discovery_audit: dict | None = None
