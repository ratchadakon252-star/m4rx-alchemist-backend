"""Source-scoped FVG/Breaker/contained Unicorn predicates on annotated raw bars.
No image reader, pivot detector or assertion of independent perception.
"""
from datetime import timedelta
from .schemas import Gate, Grade
from .ledger import EvidenceError


def base_model_geometry(seed, ledger):
    r = seed.refs
    c1, c2, c3 = [ledger.bar(r.get(k)) for k in ('c1','c2','c3')]
    if not (c1.closed_at == c2.opened_at and c2.closed_at == c3.opened_at and all(b.closed_at-b.opened_at == timedelta(minutes=5) for b in (c1,c2,c3))):
        raise ValueError('FVG_NONCONSECUTIVE_BARS')
    buy = seed.side == 'BUY'
    original_buy=not buy if seed.model_id=='MC05' else buy
    low, high = (c1.high, c3.low) if original_buy else (c3.high, c1.low)
    if low >= high or (original_buy and c2.close <= c2.open) or (not original_buy and c2.close >= c2.open):
        raise ValueError('FVG_GEOMETRY_FAIL')
    proof_time = c3.closed_at
    if seed.model_id == 'MC04':
        return low, high, proof_time, False
    if seed.model_id=='MC05':
        inverted=ledger.bar(r.get('inversion'))
        left,protected,right=[ledger.bar(r.get(k)) for k in ('protected_left','protected_bar','protected_right')]
        if not (left.closed_at==protected.opened_at and protected.closed_at==right.opened_at and right.closed_at<=inverted.opened_at and c3.closed_at<=inverted.opened_at):
            raise ValueError('IFVG_CHRONOLOGY_FAIL')
        pivot=(protected.low<left.low and protected.low<right.low) if buy else (protected.high>left.high and protected.high>right.high)
        crossing=inverted.close>high if buy else inverted.close<low
        if not pivot:raise ValueError('IFVG_PROTECTED_SWING_UNVERIFIED')
        if not crossing:raise ValueError('IFVG_INVERSION_CLOSE_ABSENT')
        leg=[ledger.bar(x) for x in seed.leg_bar_refs] or [protected,inverted]
        if buy and min(x.low for x in leg)<protected.low or not buy and max(x.high for x in leg)>protected.high:
            raise ValueError('IFVG_SWING_ALREADY_BREACHED')
        return low,high,inverted.closed_at,True
    prior = ledger.get(r.get('prior'))
    inner = ledger.get(r.get('inner'))
    prior_price = ledger.price(r.get('prior'), 'PRIOR_LIQUIDITY')
    inner_price = ledger.price(r.get('inner'), 'INNER_SWING')
    origin, raid, broken = [ledger.bar(r.get(k)) for k in ('origin','raid','break')]
    if ledger.tag(r.get('latest_swing'), 'SWING_AUDIT') != 'LATEST_UNBROKEN_AT_RAID':
        raise ValueError('BREAKER_SWING_NOT_LATEST')
    if not (prior.at < origin.closed_at <= inner.at < raid.opened_at and raid.closed_at <= broken.opened_at):
        raise ValueError('BREAKER_CHRONOLOGY_FAIL')
    if not origin.low <= inner_price <= origin.high:
        raise ValueError('ORIGIN_NOT_AT_INNER_SWING')
    if buy:
        valid = raid.low < prior_price and broken.high > inner_price and origin.close > origin.open
        closed = broken.close > inner_price
    else:
        valid = raid.high > prior_price and broken.low < inner_price and origin.close < origin.open
        closed = broken.close < inner_price
    if not valid:
        raise ValueError('BREAKER_RAID_BREAK_OR_ORIGIN_FAIL')
    if not (raid.opened_at <= c2.opened_at <= broken.closed_at and c3.closed_at >= broken.closed_at):
        raise ValueError('GAP_NOT_LINKED_TO_BREAK_LEG')
    proof_time = max(proof_time, broken.closed_at)
    # Scoped MC08 = fully contained variant reported at book p405, not partial-overlap screening variant.
    if seed.model_id == 'MC08':
        if not origin.low <= low < high <= origin.high:
            raise ValueError('UNICORN_FVG_NOT_CONTAINED')
    else:
        low, high = origin.low, origin.high
    return low, high, proof_time, closed



def observed_poi_geometry(seed,ledger):
    if seed.model_id!='MC05':return None
    r=seed.refs;a,c,z=[ledger.bar(r.get(k)) for k in ('c1','c2','c3')]
    inv=ledger.bar(r.get('inversion'))
    buy=seed.side=='BUY'
    lo,hi=(z.high,a.low) if buy else (a.high,z.low)
    if lo>=hi or not (a.closed_at==c.opened_at and c.closed_at==z.opened_at and inv.opened_at>=z.closed_at):return None
    if not (inv.close>hi if buy else inv.close<lo):return None
    return lo,hi,inv.closed_at,True

def structural_extreme(seed,ledger):
    r=seed.refs
    if seed.model_id=='MC05':
        leg=[ledger.bar(r.get('protected_bar')),ledger.bar(r.get('inversion'))]+[ledger.bar(x) for x in seed.leg_bar_refs]
    else:
        leg=[ledger.bar(r.get('raid'))]+[ledger.bar(r.get(k)) for k in ('c1','c2','break')]+[ledger.bar(x) for x in seed.leg_bar_refs]
    return min(x.low for x in leg) if seed.side=='BUY' else max(x.high for x in leg)


def model_geometry(seed,ledger):
    lo,hi,formed,closed=base_model_geometry(seed,ledger)
    if ledger.snapshot.execution_mode!=5:return lo,hi,formed,closed
    p=seed.precision_refs
    a,c,z=[ledger.bar(p.get(k),'M1') for k in ('c1','c2','c3')]
    broken=ledger.bar(p.get('break'),'M1');level=ledger.price(p.get('level'),'M1_STRUCTURE')
    if not (a.closed_at==c.opened_at and c.closed_at==z.opened_at and a.opened_at>=formed and broken.opened_at>=formed and ledger.get(p.get('level')).available_at<=broken.opened_at):
        raise ValueError('M1_AFTER_M5_CHRONOLOGY_FAIL')
    if any(x.closed_at-x.opened_at!=timedelta(minutes=1) for x in (a,c,z,broken)):
        raise ValueError('M1_DURATION_FAIL')
    buy=seed.side=='BUY'
    ml,mh=(a.high,z.low) if buy else (z.high,a.low)
    crosses=broken.close>level if buy else broken.close<level
    directional=c.close>c.open if buy else c.close<c.open
    if not (lo<=ml<mh<=hi and crosses and directional):raise ValueError('M1_CONTAINED_POI_OR_CLOSED_BREAK_FAIL')
    return ml,mh,max(z.closed_at,broken.closed_at),closed


def evaluate_model(seed, ledger, registry):
    refs=tuple(seed.refs.get(k,'') for k in ('c1','c2','c3','prior','inner','origin','raid','break'))
    if not registry.enabled(seed.model_id):
        return (Gate(name='model',status=Grade.UNKNOWN,reason='SOURCE_DISABLED',evidence_ids=refs),None)
    if seed.model_id not in {'MC04','MC05','MC07','MC08'}:
        return (Gate(name='model',status=Grade.UNKNOWN,reason='MODEL_NOT_IMPLEMENTED'),None)
    try:
        geometry=model_geometry(seed,ledger)
    except EvidenceError as e:
        return (Gate(name='model',status=Grade.UNKNOWN,reason='MODEL_UNVERIFIED:'+str(e),evidence_ids=refs),None)
    except ValueError as e:
        return (Gate(name='model',status=Grade.FAIL,reason=str(e),evidence_ids=refs),None)
    return Gate(name='model',status=Grade.PASS,reason='SCOPED_MODEL_PROOF',evidence_ids=refs),geometry
