"""Deterministic M5 discovery for P2's FVG-linked Breaker / contained Unicorn ONLY.
All facts come from as-of closed OHLC. It cannot discover disabled models or pixels.
"""
from decimal import Decimal
from .contracts import Probe,ScanAudit
from alchemist_next.schemas import Snapshot,EvidenceRecord,CandidateSeed,RouteCoverage,digest
from alchemist_next.registry import Registry

ROUTES=tuple((s,r) for s in ('BUY','SELL') for r in ('REVERSAL','CONTINUATION'))


def empty_audit(status,sources=(),issues=(),registry=None):
    registry=registry or Registry()
    return ScanAudit(status=status,probes=tuple(Probe(side=s,route=r,model_id='SCOPE',start=None,end=None,bars_examined=0,status=status,reason='SCAN_NOT_PERFORMED' if status=='SCAN_NOT_RUN' else status) for s,r in ROUTES),seed_ids=(),complete_in_scope=False,source_hashes=tuple(x.sha256 for x in sources),model_scope=tuple(c.id for c in registry.cards.values() if c.enabled),unavailable_models=tuple(c.id for c in registry.cards.values() if not c.enabled),span_start=None,span_end=None,diagnostics=tuple(issues))


def discover(adapted,mode=9,buffer=None,buffer_provenance=None,registry=None,execution_mode=None,allow_extended_context=False):
    """Return AnalysisInput-ready ingredients plus probe audit. Buffer never defaults."""
    from alchemist_next.schemas import AnalysisInput
    registry=registry or Registry();sources=tuple(x.source for x in adapted)
    if not sources or any(x.observation_only for x in adapted):
        return None,empty_audit('SCAN_NOT_RUN',sources,tuple(i for a in adapted for i in a.issues),registry)
    bytf={}
    for a in adapted:
        if a.source.tf in bytf:raise ValueError('DUPLICATE_TF_SOURCE')
        bytf[a.source.tf]=a
    required={'M15','M5','M1'} if execution_mode==5 else {'H1','M15','M5'}
    if not required<=set(bytf) or (not allow_extended_context and set(bytf)!=required):
        return None,empty_audit('INSUFFICIENT_COVERAGE',sources,('MISSING_REQUIRED_TF',),registry)
    if len({(s.symbol,s.feed,s.cursor) for s in sources})!=1:
        return None,empty_audit('INSUFFICIENT_COVERAGE',sources,('SOURCE_CURSOR_OR_FEED_MISMATCH',),registry)
    m=bytf['M5'];rs=m.bars;cursor=m.source.cursor
    if len(rs)<5:return None,empty_audit('INSUFFICIENT_COVERAGE',sources,('INSUFFICIENT_CLOSED_BARS',),registry)
    # As-of quote must be explicitly native at cursor, not an earlier close re-stamped as current.
    if m.source.quote is None or m.source.quote_at!=cursor:
        return None,empty_audit('INSUFFICIENT_COVERAGE',sources,('QUOTE_AT_CURSOR_UNVERIFIED',),registry)
    if rs[-1].bar.closed_at!=cursor:
        return None,empty_audit('INSUFFICIENT_COVERAGE',sources,('CURSOR_LAST_CLOSED_BAR_MISMATCH',),registry)
    from datetime import timedelta
    if any(a.bar.closed_at!=b.bar.opened_at for a,b in zip(rs,rs[1:])):
        return None,empty_audit('INSUFFICIENT_COVERAGE',sources,('M5_BAR_GAP',),registry)
    entry_models=[c.id for c in registry.cards.values() if c.enabled and c.role=='ENTRY_MODEL']
    if not entry_models:return None,empty_audit('NO_ELIGIBLE_MODEL_IN_SCOPE',sources,('NO_ENABLED_ENTRY_MODELS',),registry)
    snap=Snapshot(symbol=m.source.symbol,feed=m.source.feed,cursor=cursor,mode=mode,execution_mode=execution_mode,timeframes=tuple(sorted(bytf)),source_hashes=tuple(s.sha256 for s in sources),quote_ref='quote')
    ev=[];source=m.source;bars=[r.bar for r in rs]
    def record(id,role,value=None,tag=None,at=None,available=None,bar=None,locator=None,kind=None):
        ev.append(EvidenceRecord(id=id,snapshot_id=snap.snapshot_id,source_hash=source.sha256,source_kind=kind or ('MANUAL' if source.kind=='MANUAL_REVIEW' else 'OHLC'),locator=locator or f'{source.path}#{id}',tf='M5',at=at or cursor,available_at=available or at or cursor,state='OBSERVED',role=role,value=value,tag=tag,bar=bar,uncertainty=Decimal(0)))
    for n,r in enumerate(rs):record(f'b{n}','BAR',bar=r.bar,at=r.bar.closed_at,available=r.available_at,locator=f'{source.path}#closed_at={r.bar.closed_at.isoformat()}')
    record('quote','SNAPSHOT_QUOTE',value=source.quote)
    # Three-candle pivots available only once their right bar closes.
    pivots=[];fvgs=[];events=[];probes=[];seeds=[]
    for i in range(1,len(bars)-1):
        a,c,z=bars[i-1:i+2]
        if c.high>a.high and c.high>z.high:pivots.append(('HIGH',i,c.high,i+1))
        if c.low<a.low and c.low<z.low:pivots.append(('LOW',i,c.low,i+1))
        if a.high<z.low and c.close>c.open:fvgs.append(('BUY',i-1,i,i+1,a.high,z.low))
        if a.low>z.high and c.close<c.open:fvgs.append(('SELL',i-1,i,i+1,z.high,a.low))
    for side,route in ROUTES:
        if route=='CONTINUATION':
            probes.append(Probe(side=side,route=route,model_id='MC03',start=bars[0].opened_at,end=cursor,bars_examined=len(bars),status='NO_ELIGIBLE_MODEL_IN_SCOPE',reason='MC03_DISABLED; no continuation ENTRY_MODEL enabled'))
            continue
        sf=[f for f in fvgs if f[0]==side]
        probes.append(Probe(side=side,route=route,model_id='MC04',start=bars[0].opened_at,end=cursor,bars_examined=len(bars),status='POI_ONLY',reason=f'{len(sf)} verified three-bar FVGs; not standalone entries',evidence_ids=tuple(f'b{f[3]}' for f in sf)))
        found_for_model={id:0 for id in entry_models}
        for ri in range(3,len(bars)-1):
            # Pick latest previously confirmed, unraided external pivot of the relevant side.
            kind='LOW' if side=='BUY' else 'HIGH';opposite='HIGH' if side=='BUY' else 'LOW'
            priors=[p for p in pivots if p[0]==kind and p[3]<ri and all((bars[k].low>=p[2] if side=='BUY' else bars[k].high<=p[2]) for k in range(p[3]+1,ri))]
            if not priors:continue
            prior=max(priors,key=lambda p:p[1]);raided=bars[ri].low<prior[2] if side=='BUY' else bars[ri].high>prior[2]
            if not raided:continue
            events.append(f'{side}:LIQUIDITY_RAID:b{ri}:prior=b{prior[1]}')
            inners=[p for p in pivots if p[0]==opposite and prior[1]<p[1] and p[3]<ri and all((bars[k].high<=p[2] if side=='BUY' else bars[k].low>=p[2]) for k in range(p[3]+1,ri))]
            if not inners:events.append(f'{side}:RAID_NO_LATEST_INNER:b{ri}');continue
            inner=max(inners,key=lambda p:p[1]);oi=inner[1];origin=bars[oi]
            if not (origin.close>origin.open if side=='BUY' else origin.close<origin.open):
                events.append(f'{side}:ORIGIN_COLOR_NOT_IN_SCOPED_VARIANT:b{oi}');continue
            breaks=[k for k in range(ri+1,len(bars)) if (bars[k].high>inner[2] if side=='BUY' else bars[k].low<inner[2])]
            if not breaks:events.append(f'{side}:NO_HISTORICAL_BREAK:b{ri}');continue
            confirmed=[k for k in breaks if (bars[k].close>inner[2] if side=='BUY' else bars[k].close<inner[2])]
            bi=(confirmed[0] if mode==1 and confirmed else breaks[0]);events.append(f'{side}:STRUCTURAL_BREAK:b{bi}:inner=b{oi}')
            linked=[f for f in sf if ri<=f[2]<=bi+1 and f[3]>=bi]
            for f in linked:
                _,c1,c2,c3,lo,hi=f
                # Must agree with P2 source-linked predicates; not all Breaker variants require this FVG.
                if bars[c2].opened_at>bars[bi].closed_at:continue
                for model in entry_models:
                    if model=='MC08' and not origin.low<=lo<hi<=origin.high:continue
                    if model not in {'MC07','MC08'}:continue
                    cid=f'{side}_{model}_raid{ri}_break{bi}_gap{c3}'
                    refs={k:f'b{n}' for k,n in [('origin',oi),('raid',ri),('break',bi),('c1',c1),('c2',c2),('c3',c3)]}
                    priorid=cid+':prior';innerid=cid+':inner'
                    record(priorid,'PRIOR_LIQUIDITY',value=prior[2],at=bars[prior[3]].closed_at,locator=f'{source.path}#pivot=b{prior[1]},confirmed=b{prior[3]}')
                    record(innerid,'INNER_SWING',value=inner[2],at=bars[inner[3]].closed_at,locator=f'{source.path}#pivot=b{oi},confirmed=b{inner[3]}')
                    refs.update(prior=priorid,inner=innerid)
                    swing=min(x.low for x in bars[ri:bi+1]) if side=='BUY' else max(x.high for x in bars[ri:bi+1])
                    record(cid+':swing','PROTECTED_SWING',value=swing,at=bars[bi].closed_at,locator=f'{source.path}#leg=b{ri}..b{bi}')
                    refs['swing']=cid+':swing'
                    if buffer is not None and buffer_provenance:
                        record(cid+':buffer','STOP_BUFFER',value=buffer,locator=buffer_provenance,kind='POLICY');refs['buffer']=cid+':buffer'
                    formed=max(bi,c3);entry=(hi if side=='BUY' else lo) if model=='MC08' else (origin.high if side=='BUY' else origin.low)
                    boundlo,boundhi=(lo,hi) if model=='MC08' else (origin.low,origin.high)
                    post=bars[formed+1:]
                    invalid=any(x.low<swing if side=='BUY' else x.high>swing for x in post)
                    touched=any(x.low<=entry<=x.high for x in post)
                    # Conservative next-bar full-range chronology: if both expiry and touch occur, no assumed fill.
                    state='INVALID' if invalid else 'USED' if touched else 'FRESH'
                    record(cid+':poi','POI_STATE',tag=state,locator=f'{source.path}#freshness=b{formed+1}..b{len(bars)-1}')
                    record(cid+':audit','SWING_AUDIT',tag='LATEST_UNBROKEN_AT_RAID',at=bars[ri].closed_at,locator=f'{source.path}#confirmed latest swing search before=b{ri}')
                    refs.update(poi_state=cid+':poi',latest_swing=cid+':audit')
                    # Opposing levels must already exist at formation and remain untaken as of cursor.
                    targets=[]
                    targetkind='HIGH' if side=='BUY' else 'LOW'
                    for pk,pi,pv,pc in pivots:
                        if pk!=targetkind or pc>formed:continue
                        favorable=pv>entry if side=='BUY' else pv<entry
                        consumed=any(x.high>=pv if side=='BUY' else x.low<=pv for x in bars[pc+1:])
                        if favorable and not consumed:targets.append((abs(pv-entry),pv,pi,pc))
                    targets=sorted({x[1]:x for x in targets}.values())
                    for j,target in enumerate(targets[:2],1):
                        _,pv,pi,pc=target;id=cid+f':tp{j}'
                        record(id,'TARGET',value=pv,at=bars[pc].closed_at,locator=f'{source.path}#unconsumed pivot=b{pi},confirmed=b{pc}')
                        refs[f'tp{j}']=id
                    # All in-scope opposing FVG boundaries/pivots are logged as potential barriers.
                    barrier_ids=[]
                    for j,op in enumerate(fvgs):
                        if op[0]==side or op[3]>formed:continue
                        price=op[4] if side=='BUY' else op[5]
                        crossed=any(x.high>=op[5] if side=='BUY' else x.low<=op[4] for x in bars[op[3]+1:])
                        if not crossed and (price>entry if side=='BUY' else price<entry):
                            id=cid+f':barrier{j}';record(id,'BARRIER',value=price,at=bars[op[3]].closed_at,locator=f'{source.path}#opposing_fvg=b{op[1]}..b{op[3]}');barrier_ids.append(id)
                    record(cid+':barriers','BARRIER_AUDIT',tag='COMPLETE',locator=f'{source.path}#scope=visible confirmed pivots/opposing FVGs; span={bars[0].opened_at.isoformat()}..{cursor.isoformat()}')
                    record(cid+':expiry','EXPIRY',tag='CANCEL_ON_INVALIDATION_OR_TARGET_TAKEN',locator='P1_EVENT_EXPIRY_POLICY; monitor explicitly; no clock/auto-cancel',kind='POLICY')
                    refs.update(barrier_audit=cid+':barriers',expiry=cid+':expiry')
                    seed=CandidateSeed(id=cid,model_id=model,side=side,route='REVERSAL',refs=refs,barrier_refs=tuple(barrier_ids),leg_bar_refs=tuple(f'b{k}' for k in range(ri,bi+1)))
                    seeds.append(seed);found_for_model[model]+=1
        for model in entry_models:probes.append(Probe(side=side,route=route,model_id=model,start=bars[0].opened_at,end=cursor,bars_examined=len(bars),status='CANDIDATES_FOUND' if found_for_model[model] else 'NO_CANDIDATE_AFTER_COMPLETE_SCAN',reason='P2_FVG_LINKED_ONLY; latest confirmed 3-bar pivots; whole-origin color variant',evidence_ids=tuple(f'b{i}' for i in range(len(bars)))))
    coverage=[]
    for side,route in ROUTES:
        id=f'coverage:{side}:{route}';record(id,'COVERAGE',tag=f'{side}_{route}_COMPLETE',locator='deterministic discovery probe log; continuation explicitly MODEL_NOT_IN_SCOPE')
        coverage.append(RouteCoverage(side=side,route=route,evidence_ref=id,start=bars[0].opened_at,end=cursor,status='COMPLETE'))
    seeds=sorted({s.id:s for s in seeds}.values(),key=lambda s:s.id)
    audit=ScanAudit(status='CANDIDATES_FOUND' if seeds else 'NO_CANDIDATE_AFTER_COMPLETE_SCAN',probes=tuple(probes),seed_ids=tuple(s.id for s in seeds),complete_in_scope=True,source_hashes=tuple(s.sha256 for s in sources),model_scope=tuple(c.id for c in registry.cards.values() if c.enabled),unavailable_models=tuple(c.id for c in registry.cards.values() if not c.enabled),span_start=bars[0].opened_at,span_end=cursor,events=tuple(events),diagnostics=('CONTINUATION_MODEL_NOT_IN_SCOPE','SCOPED_NUMERIC_SCANNER_NOT_ALL_MARKET_MODELS','NO_REAL_MARKET_OHLC_IN_P3'))
    data=AnalysisInput(snapshot=snap,evidence=tuple(ev),seeds=tuple(seeds),coverage=tuple(coverage),discovery_audit=audit.model_dump(mode='json'))
    return data,audit
