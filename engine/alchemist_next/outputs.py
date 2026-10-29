"""Canonical decision stays separate from legacy Journal compatibility output."""
import json
from decimal import Decimal
from .schemas import State, Grade
from .validator import payload_digest
from .reason_codes import legacy_f


def selected(decision):
    if decision.state!=State.TRADE:return None
    matches=[c for c in decision.candidates if c.seed.id==decision.selected_id]
    if len(matches)!=1:raise ValueError('Invalid selected candidate')
    c=matches[0]
    if c.state!=State.TRADE or c.validation_digest!=payload_digest(c):raise ValueError('UNVALIDATED_OR_TAMPERED_CANDIDATE')
    return c


def trade_card(decision,snapshot):
    if decision.snapshot_id!=snapshot.snapshot_id:raise ValueError('SNAPSHOT_MISMATCH')
    c=selected(decision)
    if c:
        lane='CONFIRMED' if snapshot.mode==1 else 'ANTICIPATORY / PRECONFIRMATION_HIGH_RISK'
        p=c.prices
        return (f'{c.order} | Entry {p["entry"]} | SL {p["sl"]} | TP1 {p["tp1"]} | TP2 {p["tp2"]} | RR {c.rr1:.2f}/{c.rr2:.2f}\n'
                f'{decision.state.value} | {snapshot.symbol} Mode {snapshot.mode} | {lane}\n'
                f'ระยะ SL {c.stop_points} M4RX points | RR threshold provisional | ไม่ใช่คำสั่งที่ส่งแล้ว\n'
                f'เหตุผล: {"ซื้อ" if c.seed.side=="BUY" else "ขาย"}จาก {"Breaker + FVG contained (Unicorn)" if c.seed.model_id=="MC08" else "Breaker แบบ FVG-linked"} ที่มี liquidity raid → break เดิม; Entry อิง POI และ SL เลย protected extreme | {c.seed.model_id} | AS_OF_CURSOR {snapshot.cursor.isoformat()} | Cancel: POI invalid/target taken | NOT_UNATTENDED_READY / SNAPSHOT_ONLY / BROKER_UNVERIFIED')
    missing='; '.join(decision.reasons[:8]) or 'No eligible candidate within declared scope'
    return f'{decision.state.value} | NOT EXECUTABLE | AS_OF_CURSOR {snapshot.cursor.isoformat()}\n{missing}'


def legacy_journal(decision,snapshot):
    if decision.snapshot_id!=snapshot.snapshot_id:raise ValueError('SNAPSHOT_MISMATCH')
    c=selected(decision)
    obj={k:None for k in ('direction','entry_zone','trigger','entry','sl','tp','tp1','tp2','tp3','rr','rr1','rr2','rr3','invalidation')}
    obj.update(status='TRADE' if c else 'NO_TRADE',bias='neutral',symbol=snapshot.symbol,asset_type='forex' if snapshot.symbol=='XAUUSD' else 'unknown',
               timeframe='/'.join(('H1','M15','M5')) if {'H1','M15','M5'}<=set(snapshot.timeframes) else '/'.join(snapshot.timeframes),
               chart_time=snapshot.cursor.isoformat(),order_type=c.order if c else 'NONE',entry_type=('market' if c.order=='MARKET' else 'limit') if c else 'none',
               summary=decision.state.value+': snapshot candidate only' if c else decision.state.value+': not executable',
               conditions=['Readiness: '+decision.state.value,'No broker order authorized','NOT_UNATTENDED_READY','RR_THRESHOLDS_PROVISIONAL'],
               evidence=[],missing=[legacy_f(r)+':'+r for r in decision.reasons],risks=['BROKER_UNVERIFIED','ANNOTATION_NOT_PIXEL_VERIFIED'],confidence='low')
    if c:
        obj.update(direction=c.seed.side.lower(),entry_zone=f'{c.prices["poi_low"]}–{c.prices["poi_high"]}',
                   trigger='CLOSED_BREAK' if snapshot.mode==1 else 'ANTICIPATORY_ENTRY_AT_EXISTING_KEY_LEVEL',
                   entry=c.prices['entry'],sl=c.prices['sl'],tp1=c.prices['tp1'],tp2=c.prices['tp2'],tp=c.prices['tp1'],
                   rr1=c.rr1,rr2=c.rr2,rr=c.rr1,invalidation='Cancel on POI invalidation or target taken before entry',
                   evidence=[c.seed.model_id]+[k+':'+v for k,v in sorted(c.seed.refs.items())],missing=[])
        obj['risks'].extend(c.preferences)
        if snapshot.mode==9:obj['risks'].append('PRECONFIRMATION_HIGH_RISK')
    return obj


def numeric_json(value):
    """Emit exact finite Decimal as JSON numbers for legacy import, no float round trip."""
    if isinstance(value,Decimal):
        if not value.is_finite():raise ValueError('Non-finite JSON number')
        return format(value,'f')
    if isinstance(value,dict):return '{'+','.join(json.dumps(k)+':'+numeric_json(v) for k,v in value.items())+'}'
    if isinstance(value,(list,tuple)):return '['+','.join(numeric_json(v) for v in value)+']'
    return json.dumps(value,ensure_ascii=False,allow_nan=False)


def readiness_counts(decisions):
    # Opportunities deduplicated by evaluation_id; legacy NO_TRADE never used as denominator.
    unique={d.evaluation_id:d for d in decisions}
    return {s.value:sum(d.state==s for d in unique.values()) for s in State}
