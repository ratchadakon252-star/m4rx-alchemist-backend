from decimal import Decimal
from .schemas import Gate, Grade, Candidate, State
from .ledger import EvidenceError
from .models import evaluate_model,structural_extreme,observed_poi_geometry
from .policy import POLICY


def gate(name, status, reason, *refs):
    return Gate(name=name,status=status,reason=reason,evidence_ids=tuple(x for x in refs if x))


def broker_review(broker, snapshot, prices, side, order, policy=POLICY):
    """Partial diagnostic checks only; never authorize live trading."""
    out=[]
    b=broker
    if b.bid is None or b.ask is None or b.as_of is None or not b.provenance:
        return (gate('broker_quote',Grade.UNKNOWN,'BROKER_QUOTES_UNVERIFIED'),)
    if b.symbol != snapshot.symbol or b.feed != snapshot.feed:
        out.append(gate('broker_identity',Grade.FAIL,'BROKER_IDENTITY_MISMATCH'))
    spread=b.ask-b.bid
    out.append(gate('spread_sign',Grade.PASS if 0 <= spread and b.bid>0 else Grade.FAIL,'SPREAD_SIGN_CHECK'))
    if b.max_spread is None or b.max_spread < 0:
        out.append(gate('spread_policy',Grade.UNKNOWN,'OPEN_POLICY_MAX_SPREAD'))
    else:
        out.append(gate('spread_policy',Grade.PASS if spread<=b.max_spread else Grade.FAIL,'SPREAD_LIMIT_CHECK'))
    age=(snapshot.cursor-b.as_of).total_seconds()
    if b.max_quote_age_seconds is None or b.max_quote_age_seconds < 0:
        out.append(gate('quote_age',Grade.UNKNOWN,'OPEN_POLICY_QUOTE_AGE'))
    else:
        out.append(gate('quote_age',Grade.PASS if 0<=age<=b.max_quote_age_seconds else Grade.FAIL,'QUOTE_AGE_CHECK'))
    if b.tick_size is None or b.tick_size<=0:
        out.append(gate('tick',Grade.UNKNOWN,'OPEN_POLICY_TICK'))
    else:
        out.append(gate('tick',Grade.PASS if all(v is None or v%b.tick_size==0 for v in prices.values()) else Grade.FAIL,'TICK_ALIGNMENT_CHECK'))
    e,s,t1,t2=(prices.get(k) for k in ('entry','sl','tp1','tp2'))
    if None not in (e,s,t1,t2):
        q=b.ask if side=='BUY' else b.bid
        if order=='MARKET':
            lo,hi=prices.get('poi_low'),prices.get('poi_high')
            legal=lo is not None and hi is not None and lo<=q<=hi
            e=q  # Recompute diagnostics with the actual side-specific quote, not old indicative entry.
        else:
            legal=(order=='BUY_LIMIT' and e<b.ask) or (order=='SELL_LIMIT' and e>b.bid)
        out.append(gate('broker_order',Grade.PASS if legal else Grade.FAIL,'LIVE_REQUOTE_ORDER_CHECK'))
        delta=Decimal(1) if side=='BUY' else Decimal(-1)
        risk=delta*(e-s)
        ok=risk>0 and delta*(t1-e)>0 and delta*(t2-t1)>0
        if ok:ok=delta*(t1-e)/risk>=policy.rr1_min and delta*(t2-e)/risk>=policy.rr2_min
        out.append(gate('broker_rr',Grade.PASS if ok else Grade.FAIL,'LIVE_REQUOTE_RR_CHECK'))
        if b.min_distance is None or b.min_distance<0:
            out.append(gate('broker_distance',Grade.UNKNOWN,'OPEN_POLICY_MIN_DISTANCE'))
        else:
            distances=[abs(e-s),abs(t1-e),abs(t2-e)]
            if order!='MARKET':distances.append(abs(q-e))
            out.append(gate('broker_distance',Grade.PASS if min(distances)>=b.min_distance else Grade.FAIL,'BROKER_MIN_DISTANCE_CHECK'))
    out.append(gate('live_execution',Grade.UNKNOWN,'NO_LIVE_ADAPTER_OPEN_POLICY_BUDGET_FEES_CONTRACT'))
    return tuple(out)


def complete(seed, ledger, registry, broker, policy=POLICY):
    """Evaluate all independent fields; a blocker never ends the completion sweep."""
    snap=ledger.snapshot
    gates=[]; prices={k:None for k in ('entry','swing','buffer','sl','tp1','tp2','poi_low','poi_high')}
    preferences=[]
    supported=snap.symbol=='XAUUSD' and snap.price_unit=='XAUUSD_NATIVE'
    gates.append(gate('profile',Grade.PASS if supported else Grade.FAIL,'XAUUSD_MVP' if supported else 'UNSUPPORTED_SYMBOL_PROFILE'))
    data_ok=bool(snap.feed and ({'M15','M5','M1'} if snap.execution_mode==5 else {'H1','M15','M5'})<=set(snap.timeframes))
    gates.append(gate('input',Grade.PASS if data_ok else Grade.UNKNOWN,'SNAPSHOT_IDENTITY' if data_ok else 'INPUT_UNVERIFIED'))
    mg,geom=evaluate_model(seed,ledger,registry);gates.append(mg)
    if geom is None and mg.status==Grade.UNKNOWN:
        try:geom=observed_poi_geometry(seed,ledger)
        except (EvidenceError,ValueError):pass
    if seed.route!='REVERSAL' and seed.model_id in {'MC07','MC08'}:
        gates.append(gate('route',Grade.FAIL,'MODEL_ROUTE_MISMATCH'))
    else:gates.append(gate('route',Grade.PASS,'ROUTE_DECLARED'))
    if geom:
        lo,hi,formed,closed=geom;prices['poi_low']=lo;prices['poi_high']=hi
        # Deterministically derived from known bounds; never midpoint of an arbitrary zone.
        prices['entry']=(lo+hi)/2 if seed.entry_rule=='CE' else (hi if seed.side=='BUY' else lo)
        gates.append(gate('entry',Grade.PASS,'ANCHORED_'+seed.entry_rule))
    else:
        formed=None;closed=False
        gates.append(gate('entry',Grade.UNKNOWN,'ENTRY_UNVERIFIED'))
    if seed.model_id=='MC04':
        gates.append(gate('trigger',Grade.UNKNOWN,'POI_ONLY_REQUIRES_ENTRY_MODEL'))
    elif snap.mode==9:
        gates.append(gate('trigger',Grade.NA,'NO_NEW_REACTION_REQUIRED'))
    elif geom:
        gates.append(gate('trigger',Grade.PASS if closed else Grade.UNKNOWN,'CLOSED_BREAK_CONFIRMED' if closed else 'TRIGGER_ABSENT_F3'))
    else:gates.append(gate('trigger',Grade.UNKNOWN,'TRIGGER_UNVERIFIED'))
    for name,role in (('swing','PROTECTED_SWING'),('buffer','STOP_BUFFER'),('tp1','TARGET'),('tp2','TARGET')):
        try:
            prices[name]=ledger.price(seed.refs.get(name),role)
            if prices[name]<=0:raise ValueError('NONPOSITIVE_PRICE_OR_BUFFER')
            gates.append(gate(name,Grade.PASS,'ANCHORED_'+name.upper(),seed.refs.get(name)))
        except EvidenceError as e:
            gates.append(gate(name,Grade.UNKNOWN,name.upper()+'_UNVERIFIED:'+str(e),seed.refs.get(name)))
        except ValueError as e:
            gates.append(gate(name,Grade.FAIL,str(e),seed.refs.get(name)))
    # Structural swing must be tied to the selected source variant's raid extreme.
    try:
        swing=prices['swing'];expected=structural_extreme(seed,ledger)
        if swing is None:raise EvidenceError('SWING_MISSING')
        gates.append(gate('swing_binding',Grade.PASS if swing==expected else Grade.FAIL,'OBSERVED_RAID_TO_BREAK_EXTREME_BINDING'))
    except EvidenceError as e:gates.append(gate('swing_binding',Grade.UNKNOWN,'SWING_UNVERIFIED:'+str(e)))
    if prices['swing'] is not None and prices['buffer'] is not None:
        prices['sl']=prices['swing']-prices['buffer'] if seed.side=='BUY' else prices['swing']+prices['buffer']
        gates.append(gate('sl',Grade.PASS,'DERIVED_SWING_PLUS_BUFFER',seed.refs.get('swing'),seed.refs.get('buffer')))
    else:gates.append(gate('sl',Grade.UNKNOWN,'STRUCTURAL_SL_UNVERIFIED'))
    expired=False
    try:
        state_record=ledger.get(seed.refs.get('poi_state'))
        ps=ledger.tag(seed.refs.get('poi_state'),'POI_STATE')
        if formed is None or not formed<=state_record.at<=snap.cursor:raise EvidenceError('POI_STATE_CHRONOLOGY_UNVERIFIED')
        # State is supplied as an audited annotation, not auto-detected from chart pixels.
        if ps in {'USED','INVALID'}:
            expired=True;gates.append(gate('poi',Grade.FAIL,'POI_EXPIRED_F2',state_record.id))
        elif ps=='FRESH':gates.append(gate('poi',Grade.PASS,'FRESH_ANNOTATED',state_record.id))
        else:gates.append(gate('poi',Grade.UNKNOWN,'PARTIAL_MITIGATION_OPEN_POLICY',state_record.id))
    except EvidenceError as e:gates.append(gate('poi',Grade.UNKNOWN,'POI_UNVERIFIED:'+str(e)))
    try:
        exp=ledger.get(seed.refs.get('expiry'))
        et=ledger.tag(exp.id,'EXPIRY')
        if formed is None or exp.at<formed:raise EvidenceError('EXPIRY_PRECEDES_FORMATION')
        if et=='EXPIRED':expired=True;gates.append(gate('expiry',Grade.FAIL,'EXPIRED_F2',exp.id))
        elif et=='CANCEL_ON_INVALIDATION_OR_TARGET_TAKEN':gates.append(gate('expiry',Grade.PASS,'EVENT_EXPIRY_NOT_UNATTENDED_READY',exp.id))
        else:gates.append(gate('expiry',Grade.UNKNOWN,'EXPIRY_OPEN_POLICY',exp.id))
    except EvidenceError as e:gates.append(gate('expiry',Grade.UNKNOWN,'EXPIRY_UNVERIFIED:'+str(e)))
    order='NONE'
    quote_unverified=False
    try:
        q=ledger.price(snap.quote_ref,'SNAPSHOT_QUOTE')
    except EvidenceError as ex:
        q=None
        quote_unverified=True
        gates.append(gate('order',Grade.UNKNOWN,'QUOTE_UNVERIFIED:'+str(ex),snap.quote_ref))
    if q is not None:
        e=prices['entry']
        if e is None:
            gates.append(gate('order',Grade.UNKNOWN,'ORDER_ENTRY_DEPENDENCY_UNKNOWN'))
        else:
            limit='BUY_LIMIT' if seed.side=='BUY' else 'SELL_LIMIT'
            limit_ok=e<q if seed.side=='BUY' else e>q
            market_ok=prices['poi_low']<=q<=prices['poi_high']
            wanted=seed.order_requested
            if wanted in {'AUTO',limit} and limit_ok:order=limit
            elif wanted in {'AUTO','MARKET'} and market_ok:
                order='MARKET'
                prices['entry']=q
            gates.append(gate('order',Grade.PASS if order!='NONE' else Grade.FAIL,'SNAPSHOT_ORDER_PASS' if order!='NONE' else 'ORDER_UNAVAILABLE_F8',snap.quote_ref))
    e,s,w,t1,t2=(prices[x] for x in ('entry','sl','swing','tp1','tp2'))
    rr1=rr2=stop_points=None
    if None not in (e,s,w):
        ok=(s<w<e if seed.side=='BUY' else e<w<s)
        gates.append(gate('stop_geometry',Grade.PASS if ok else Grade.FAIL,'STRUCTURAL_RISK_PASS' if ok else 'STRUCTURAL_RISK_FAIL_F4'))
    else:gates.append(gate('stop_geometry',Grade.UNKNOWN,'STRUCTURAL_SL_UNVERIFIED'))
    delta=Decimal(1) if seed.side=='BUY' else Decimal(-1)
    risk=delta*(e-s) if None not in (e,s) else None
    if risk is not None and risk>0 and supported:
        stop_points=risk/policy.point_size
        if stop_points<policy.preferred_stop_min:preferences.append('TIGHT_STOP_SPREAD_CHECK')
        if stop_points>policy.preferred_stop_max:preferences.append('WIDE_STOP_SIZE_CHECK')
    if None not in (e,s,t1,t2):
        reward1=delta*(t1-e);reward2=delta*(t2-e)
        target_ok=0<reward1<reward2
        gates.append(gate('target_geometry',Grade.PASS if target_ok else Grade.FAIL,'TARGET_GEOMETRY_CHECK'))
        if risk>0:
            rr1,rr2=reward1/risk,reward2/risk
            if supported:
                if reward1/policy.point_size!=policy.preferred_tp1:preferences.append('TP1_PREFERENCE_MISMATCH')
                if reward2/policy.point_size!=policy.preferred_tp2:preferences.append('TP2_PREFERENCE_MISMATCH')
            passed=target_ok and rr1>=policy.rr1_min and rr2>=policy.rr2_min
            gates.append(gate('rr',Grade.PASS if passed else Grade.FAIL,'RR_PROVISIONAL_PASS' if passed else 'TARGET_RR_FAIL_F5'))
        else:gates.append(gate('rr',Grade.FAIL,'NONPOSITIVE_RISK'))
    else:
        gates.extend([gate('target_geometry',Grade.UNKNOWN,'TARGET_PRICE_UNVERIFIED'),gate('rr',Grade.UNKNOWN,'RR_DEPENDENCY_UNKNOWN')])
    try:
        if ledger.tag(seed.refs.get('barrier_audit'),'BARRIER_AUDIT')!='COMPLETE':raise EvidenceError('BARRIER_SCAN_INCOMPLETE')
        if e is None or t1 is None or t2 is None:raise EvidenceError('BARRIER_PRICE_DEPENDENCY')
        barriers=[ledger.price(x,'BARRIER') for x in seed.barrier_refs]
        blocked=any((e<x<t2 if seed.side=='BUY' else t2<x<e) and x!=t1 for x in barriers)
        gates.append(gate('barriers',Grade.FAIL if blocked else Grade.PASS,'TARGET_OBSTRUCTED_F5' if blocked else 'FIRST_BARRIER_CHECKED',*seed.barrier_refs))
    except EvidenceError as ex:gates.append(gate('barriers',Grade.UNKNOWN,'BARRIER_UNVERIFIED:'+str(ex)))
    if not supported:state=State.NONE
    elif not data_ok or quote_unverified:state=State.DATA
    elif expired and mg.status==Grade.PASS:state=State.EXPIRED
    elif any(g.status==Grade.FAIL for g in gates):state=State.NONE
    elif any(g.status==Grade.UNKNOWN for g in gates):state=State.PREPARED
    else:state=State.TRADE
    card=registry.cards.get(seed.model_id)
    from .schemas import digest
    return Candidate(seed=seed,snapshot_id=snap.snapshot_id,card_hash=digest(card) if card else 'MISSING',policy_hash=policy.hash,
                     gates=tuple(gates),prices=prices,rr1=rr1,rr2=rr2,stop_points=stop_points,order=order,state=state,
                     preferences=tuple(preferences),incomplete_fields=tuple(g.name for g in gates if g.status==Grade.UNKNOWN),
                     broker_checks=broker_review(broker,snap,prices,seed.side,order,policy))
