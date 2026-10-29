"""Second pass re-derives prices/RR from evidence, never reads cached PASS as proof.
Shared source predicates are definitions, not an independent perception channel.
"""
from decimal import Decimal
from .schemas import Grade, Gate, digest
from .ledger import EvidenceError
from .models import model_geometry,structural_extreme
from .policy import POLICY


def payload_digest(candidate):
    return digest(candidate.model_dump(mode='json',exclude={'validation_digest'}))


def validate(candidate, ledger, registry, policy=POLICY):
    issues=[]
    def fail(reason,status=Grade.FAIL):
        issues.append(Gate(name='independent_validator',status=status,reason=reason))
    seed=candidate.seed;r=seed.refs
    if candidate.snapshot_id!=ledger.snapshot.snapshot_id or candidate.policy_hash!=policy.hash:fail('VALIDATOR_CONTEXT_MISMATCH')
    card=registry.cards.get(seed.model_id)
    if not card or not registry.enabled(seed.model_id):fail('SOURCE_DISABLED',Grade.UNKNOWN)
    elif candidate.card_hash!=digest(card):fail('VALIDATOR_CARD_HASH_MISMATCH')
    if ledger.snapshot.symbol!='XAUUSD' or ledger.snapshot.price_unit!='XAUUSD_NATIVE':fail('UNSUPPORTED_SYMBOL_PROFILE')
    if not ledger.snapshot.feed or not ({'M15','M5','M1'} if ledger.snapshot.execution_mode==5 else {'H1','M15','M5'})<=set(ledger.snapshot.timeframes):fail('INPUT_UNVERIFIED',Grade.UNKNOWN)
    try:
        lo,hi,formation,closed=model_geometry(seed,ledger)
        if seed.model_id=='MC04':fail('POI_IS_NOT_ENTRY_MODEL',Grade.UNKNOWN)
        if seed.model_id in {'MC07','MC08'} and seed.route!='REVERSAL':fail('MODEL_ROUTE_MISMATCH')
        if ledger.snapshot.mode==1 and not closed:fail('TRIGGER_ABSENT_F3',Grade.UNKNOWN)
        e=(lo+hi)/2 if seed.entry_rule=='CE' else hi if seed.side=='BUY' else lo
        q=ledger.price(ledger.snapshot.quote_ref,'SNAPSHOT_QUOTE')
        if candidate.order=='MARKET':e=q
        w=ledger.price(r.get('swing'),'PROTECTED_SWING');b=ledger.price(r.get('buffer'),'STOP_BUFFER')
        extreme=structural_extreme(seed,ledger)
        if w!=extreme:fail('SWING_ANCHOR_MISMATCH')
        s=w-b if seed.side=='BUY' else w+b
        t1=ledger.price(r.get('tp1'),'TARGET');t2=ledger.price(r.get('tp2'),'TARGET')
        raw={'entry':e,'swing':w,'buffer':b,'sl':s,'tp1':t1,'tp2':t2,'poi_low':lo,'poi_high':hi}
        if raw!=candidate.prices:fail('PRICE_RECOMPUTE_MISMATCH')
        valid=(s<w<e<t1<t2) if seed.side=='BUY' else (t2<t1<e<w<s)
        if b<=0 or not valid:fail('STRUCTURAL_OR_TARGET_GEOMETRY_FAIL')
        sign=Decimal(1) if seed.side=='BUY' else Decimal(-1)
        risk=sign*(e-s)
        if risk<=0:fail('NONPOSITIVE_RISK')
        else:
            rr1,rr2=sign*(t1-e)/risk,sign*(t2-e)/risk
            if rr1!=candidate.rr1 or rr2!=candidate.rr2 or risk/Decimal('.01')!=candidate.stop_points:fail('RR_OR_UNIT_RECOMPUTE_MISMATCH')
            if rr1<policy.rr1_min or rr2<policy.rr2_min:fail('RR_BELOW_PROVISIONAL_MINIMUM')
        for field,role,tag in [('poi_state','POI_STATE','FRESH'),('expiry','EXPIRY','CANCEL_ON_INVALIDATION_OR_TARGET_TAKEN')]:
            rec=ledger.get(r.get(field))
            if ledger.tag(rec.id,role)!=tag:fail(field.upper()+'_NOT_CURRENT')
            if rec.at<formation:fail(field.upper()+'_CHRONOLOGY_FAIL')
        if ledger.tag(r.get('barrier_audit'),'BARRIER_AUDIT')!='COMPLETE':fail('BARRIER_COVERAGE_UNKNOWN',Grade.UNKNOWN)
        for ref in seed.barrier_refs:
            v=ledger.price(ref,'BARRIER')
            if (e<v<t2 if seed.side=='BUY' else t2<v<e) and v!=t1:fail('TARGET_OBSTRUCTED')
        q=ledger.price(ledger.snapshot.quote_ref,'SNAPSHOT_QUOTE')
        legal=(candidate.order=='BUY_LIMIT' and seed.side=='BUY' and e<q) or (candidate.order=='SELL_LIMIT' and seed.side=='SELL' and e>q) or (candidate.order=='MARKET' and lo<=q<=hi and e==q)
        if not legal:fail('ORDER_MECHANICS_FAIL')
        if seed.order_requested!='AUTO' and candidate.order!=seed.order_requested:fail('REQUESTED_ORDER_MISMATCH')
    except EvidenceError as ex:fail('RAW_EVIDENCE_UNVERIFIED:'+str(ex),Grade.UNKNOWN)
    except (ValueError,TypeError) as ex:fail('MODEL_GEOMETRY_FAIL:'+str(ex))
    if candidate.live_ready:fail('LIVE_READINESS_FORBIDDEN')
    return tuple(issues)
