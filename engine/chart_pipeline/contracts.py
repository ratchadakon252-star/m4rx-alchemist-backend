from datetime import datetime
from typing import Literal
from alchemist_next.schemas import Typed,D,Bar,EvidenceRecord,CandidateSeed,RouteCoverage,Decision
from pydantic import model_validator

class AxisAnchor(Typed):
    pixel_y: D
    label_price: D
    pixel_uncertainty: D
    bbox: tuple[int,int,int,int]

class ObservedFact(Typed):
    field: str
    text: str
    bbox: tuple[int,int,int,int] | None = None
    confidence: str

class ChartSource(Typed):
    id: str
    kind: Literal['SCREENSHOT','OHLC','MANUAL_REVIEW']
    path: str
    sha256: str
    symbol: str | None
    feed: str | None
    tf: str | None
    cursor: datetime | None
    visible_start: datetime | None = None
    visible_end: datetime | None = None
    price_precision: Literal['EXACT_NATIVE','BOUNDED','UNKNOWN'] = 'UNKNOWN'
    quote: D | None = None
    quote_at: datetime | None = None
    confidence: str = 'UNKNOWN'
    facts: tuple[ObservedFact,...] = ()
    axis_anchors: tuple[AxisAnchor,...] = ()
    source_role: Literal['SOURCE_CHART','REPLY','OUTCOME','OTHER'] = 'SOURCE_CHART'
    future_relation: Literal['AS_OF_VERIFIED','UNKNOWN','AFTER_CURSOR'] = 'UNKNOWN'

    @model_validator(mode='after')
    def span(self):
        if self.visible_start and self.visible_end and self.visible_start>self.visible_end:
            raise ValueError('Invalid visible interval')
        if len(self.sha256)!=64:raise ValueError('Source hash required')
        return self

class TimedBar(Typed):
    id: str
    bar: Bar
    available_at: datetime

    @model_validator(mode='after')
    def availability(self):
        if self.available_at<self.bar.closed_at:raise ValueError('Cannot know a closed bar early')
        return self

class Adapted(Typed):
    source: ChartSource
    bars: tuple[TimedBar,...]
    evidence: tuple[EvidenceRecord,...] = ()
    issues: tuple[str,...]
    excluded_after_cursor: tuple[str,...]
    observation_only: bool

class Probe(Typed):
    side: Literal['BUY','SELL']
    route: Literal['REVERSAL','CONTINUATION']
    model_id: str
    start: datetime | None
    end: datetime | None
    bars_examined: int
    status: str
    reason: str
    evidence_ids: tuple[str,...] = ()

class ScanAudit(Typed):
    status: Literal['SCAN_NOT_RUN','INSUFFICIENT_COVERAGE','NO_ELIGIBLE_MODEL_IN_SCOPE','NO_CANDIDATE_AFTER_COMPLETE_SCAN','CANDIDATES_FOUND']
    probes: tuple[Probe,...]
    seed_ids: tuple[str,...]
    complete_in_scope: bool
    source_hashes: tuple[str,...]
    model_scope: tuple[str,...]
    unavailable_models: tuple[str,...]
    span_start: datetime | None
    span_end: datetime | None
    events: tuple[str,...] = ()
    diagnostics: tuple[str,...] = ()

class PipelineResult(Typed):
    case_id: str
    mode: Literal[1,9]
    readiness: str
    reasons: tuple[str,...]
    scan: ScanAudit
    source_ids: tuple[str,...]
    decision: Decision | None
    entry: D | None = None
    sl: D | None = None
    tp1: D | None = None
    tp2: D | None = None
    rr1: D | None = None
    rr2: D | None = None
    live_ready: Literal[False] = False
