from typing import Literal
from decimal import Decimal
from pydantic import model_validator
from alchemist_next.schemas import Typed,D

class TradePlan(Typed):
    direction: Literal['BUY','SELL']
    order_type: Literal['BUY_LIMIT','SELL_LIMIT','MARKET']
    entry: D
    sl: D
    tp1: D
    tp2: D
    stop_M4RX_points: D
    rr1: D
    rr2: D
    model_id: str
    preference_deviations: tuple[str,...] = ()
    rr_basis: Literal['GROSS_NATIVE_PRICE'] = 'GROSS_NATIVE_PRICE'
    evidence_refs: dict[str,str]
    precision_refs: dict[str,str]
    invalidation: str
    expiry: str

    @model_validator(mode='after')
    def valid_plan(self):
        if not (self.sl<self.entry<self.tp1<self.tp2 if self.direction=='BUY' else self.tp2<self.tp1<self.entry<self.sl):raise ValueError('Journal geometry invalid')
        if self.order_type!='MARKET' and not self.order_type.startswith(self.direction):raise ValueError('Journal order side invalid')
        if self.rr1<=0 or self.rr2<=0:raise ValueError('Journal RR invalid')
        return self

class RiskAcceptance(Typed):
    lot: None = None
    maximum_cash_loss: None = None
    status: Literal['BROKER_SPECS_SIZE_BUDGET_UNVERIFIED'] = 'BROKER_SPECS_SIZE_BUDGET_UNVERIFIED'

class JournalEntry(Typed):
    schema_version: Literal['2.0.0-dev']
    record_id: str
    record_type: Literal['CONTEXT','ANALYSIS']
    mode: Literal[1,2,3,4,5,9] | None
    readiness: Literal['DATA_UNVERIFIED','PREPARED_PLAN','TRADE_CANDIDATE','NO_VALID_SETUP','EXPIRED','CONTEXT_ONLY']
    execution_lane: Literal['CONFIRMED','ANTICIPATORY','CONTEXT_ONLY','UNKNOWN']
    snapshot: dict | None
    source_hashes: list[str]
    plan: TradePlan | None
    missing_or_blockers: list[str]
    analysis_diagnostics: list[str] = []
    risk_acceptance: RiskAcceptance
    lifecycle: Literal['SIGNAL_CANDIDATE','NO_ORDER']
    runtime: Literal['ENGINE_RAN_LOCALLY','LEGACY_IMPORT_NOT_REVALIDATED']
    release: Literal['PARTIAL_DEVELOPER_PREVIEW']
    live_ready: Literal[False]
    reported_legacy: dict | None = None

    @model_validator(mode='after')
    def readiness_binding(self):
        if (self.readiness=='TRADE_CANDIDATE')!=(self.plan is not None):raise ValueError('Readiness/plan mismatch')
        if self.mode==2 and self.plan is not None:raise ValueError('Mode2 cannot carry order plan')
        if self.runtime=='LEGACY_IMPORT_NOT_REVALIDATED' and self.plan is not None:raise ValueError('Legacy cannot grant validated trade')
        return self
