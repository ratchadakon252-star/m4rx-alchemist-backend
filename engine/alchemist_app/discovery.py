"""P4 native discovery overlay. Existing P3 scope remains compatible; new iFVG is explicit R&D."""
from decimal import Decimal
from copy import copy
from chart_pipeline.discovery import discover as legacy_discover,empty_audit
from chart_pipeline.contracts import Probe
from alchemist_next.schemas import EvidenceRecord,CandidateSeed
from alchemist_next.registry import Registry
from alchemist_next.ledger import Ledger,EvidenceError
from alchemist_next.models import base_model_geometry


def pivots(bars):
    out=[]
    for i in range(1,len(bars)-1):
        a,c,z=bars[i-1:i+2]
        if c.high>a.high and c.high>z.high:out.append(('HIGH',i,c.high,i+1))
        if c.low<a.low and c.low<z.low:out.append(('LOW',i,c.low,i+1))
    return out


def gaps(bars):
    out=[]
    for i in range(1,len(bars)-1):
        a,c,z=bars[i-1:i+2]
        if a.high<z.low and c.close>c.open:out.append(('BUY',i-1,i,i+1,a.high,z.low))
        if a.low>z.high and c.close<c.open:out.append(('SELL',i-1,i,i+1,z.high,a.low))
    return out


def discover(adapted,mode=1,buffer=None,buffer_provenance=None,registry=None):
    registry=registry or Registry(scope='P4')
    legacy=copy(registry);legacy.cards={k:c.model_copy(update={'enabled':False}) if k=='MC05' else c for k,c in registry.cards.items()}
    data,audit=legacy_discover(adapted,mode=9 if mode==9 else 1,buffer=buffer,buffer_provenance=buffer_provenance,registry=legacy,execution_mode=5 if mode==5 else None,allow_extended_context=True)
    if data is None:return None,audit
    tf={a.source.tf:a for a in adapted};src=tf['M5'].source;bars=[x.bar for x in tf['M5'].bars];cursor=src.cursor
    ps=pivots(bars);gs=gaps(bars);ev=list(data.evidence);seeds=list(data.seeds);probes=list(audit.probes);events=list(audit.events)
    def add(id,role,value=None,tag=None,at=None,bar=None,source=None,locator=None):
        source=source or src
        ev.append(EvidenceRecord(id=id,snapshot_id=data.snapshot.snapshot_id,source_hash=source.sha256,source_kind='MANUAL' if source.kind=='MANUAL_REVIEW' else 'OHLC',locator=locator or source.path+'#'+id,tf=source.tf,at=at or cursor,available_at=at or cursor,state='OBSERVED',role=role,value=value,tag=tag,bar=bar,uncertainty=Decimal(0)))
        return id
    counts={(s,r):0 for s in ('BUY','SELL') for r in ('REVERSAL','CONTINUATION')}
    if registry.enabled('MC05'):
        m15=[r.bar for r in tf['M15'].bars];cp=pivots(m15)
        highs=[p[2] for p in cp if p[0]=='HIGH'];lows=[p[2] for p in cp if p[0]=='LOW']
        trend='BUY' if len(highs)>=2 and len(lows)>=2 and highs[-1]>highs[-2] and lows[-1]>lows[-2] else 'SELL' if len(highs)>=2 and len(lows)>=2 and highs[-1]<highs[-2] and lows[-1]<lows[-2] else 'UNKNOWN'
        for original,c1,c2,c3,lo,hi in gs:
            side='BUY' if original=='SELL' else 'SELL'
            inversions=[j for j in range(c3+1,len(bars)) if (bars[j].close>hi if side=='BUY' else bars[j].close<lo)]
            if not inversions:continue
            iv=inversions[0];route='CONTINUATION' if trend==side else 'REVERSAL'
            candidates=[p for p in ps if p[0]==('LOW' if side=='BUY' else 'HIGH') and p[3]+1<=iv and all((bars[k].low>=p[2] if side=='BUY' else bars[k].high<=p[2]) for k in range(p[1]+1,iv+1))]
            protected=max(candidates,key=lambda p:p[1]) if candidates else None
            cid=f'{side}_MC05_gap{c3}_inv{iv}'
            refs={'c1':f'b{c1}','c2':f'b{c2}','c3':f'b{c3}','inversion':f'b{iv}'}
            if protected:
                _,pi,pv,pc=protected;refs.update(protected_left=f'b{pi-1}',protected_bar=f'b{pi}',protected_right=f'b{pi+1}')
                refs['swing']=add(cid+':swing','PROTECTED_SWING',value=pv,at=bars[pc].closed_at,locator=src.path+f'#confirmed_pivot=b{pi},right=b{pc}')
                leg=tuple(f'b{k}' for k in range(pi,iv+1))
            else:leg=()
            if buffer is not None and buffer_provenance:
                id=cid+':buffer';ev.append(EvidenceRecord(id=id,snapshot_id=data.snapshot.snapshot_id,source_hash=src.sha256,source_kind='POLICY',locator=buffer_provenance,tf='M5',at=cursor,available_at=cursor,state='OBSERVED',role='STOP_BUFFER',value=buffer,uncertainty=Decimal(0)));refs['buffer']=id
            refs['expiry']=add(cid+':expiry','EXPIRY',tag='CANCEL_ON_INVALIDATION_OR_TARGET_TAKEN')
            events.append(f'{side}:MC05_CLOSED_INVERSION:b{iv}:originalFVG=b{c1}..b{c3}')
            seeds.append(CandidateSeed(id=cid,model_id='MC05',side=side,route=route,refs=refs,leg_bar_refs=leg))
            counts[(side,route)]+=1
        for side in ('BUY','SELL'):
            for route in ('REVERSAL','CONTINUATION'):
                probes.append(Probe(side=side,route=route,model_id='MC05',start=bars[0].opened_at,end=cursor,bars_examined=len(bars),status='CANDIDATES_FOUND' if counts[(side,route)] else 'NO_CANDIDATE_AFTER_COMPLETE_SCAN',reason='iFVG closed far-boundary inversion; continuation label only with confirmed M15 trend; otherwise local reversal/HTF unknown',evidence_ids=tuple('b'+str(i) for i in range(len(bars)))))
    # Targets bind at model formation, not retrospectively to whichever liquidity remains at cursor.
    bound=[]
    for seed in seeds:
        refs=dict(seed.refs);buy=seed.side=='BUY'
        if seed.model_id=='MC05':
            a,c,z=[bars[int(refs[k][1:])] for k in ('c1','c2','c3')];lo,hi=(z.high,a.low) if buy else (a.high,z.low);formed=int(refs['inversion'][1:])
            invalid=any(x.close<lo if buy else x.close>hi for x in bars[formed+1:])
        else:
            try:lo,hi,time,_=base_model_geometry(seed,Ledger(data.snapshot,tuple(ev)))
            except (EvidenceError,ValueError):bound.append(seed);continue
            formed=max(int(refs['break'][1:]),int(refs['c3'][1:]));swing=next((e.value for e in ev if e.id==refs.get('swing')),None)
            invalid=swing is not None and any(x.low<swing if buy else x.high>swing for x in bars[formed+1:])
        entry=(lo+hi)/2 if seed.entry_rule=='CE' else hi if buy else lo
        levels=[]
        for kind,pi,pv,pc in ps:
            if kind!=('HIGH' if buy else 'LOW') or pc>formed:continue
            if not (pv>entry if buy else pv<entry):continue
            if any(x.high>=pv if buy else x.low<=pv for x in bars[pc+1:formed+1]):continue
            levels.append((abs(pv-entry),pv,pi,pc))
        levels=sorted({p[1]:p for p in levels}.values())
        for key in ('tp1','tp2'):refs.pop(key,None)
        for j,(_,pv,pi,pc) in enumerate(levels[:2],1):refs[f'tp{j}']=add(seed.id+f':p4tp{j}','TARGET',value=pv,at=bars[pc].closed_at,locator=src.path+f'#formation_bound_target=b{pi};confirmed=b{pc};formation=b{formed}')
        target_consumed=bool(levels) and any(x.high>=levels[0][1] if buy else x.low<=levels[0][1] for x in bars[formed+1:])
        touched=any(x.low<=entry<=x.high for x in bars[formed+1:])
        state='INVALID' if invalid else 'USED' if touched else 'FRESH'
        refs['poi_state']=add(seed.id+':p4poi','POI_STATE',tag=state,locator=src.path+f'#postformation=b{formed+1}..b{len(bars)-1}; intrabar fill NOT assumed')
        refs['expiry']=add(seed.id+':p4expiry','EXPIRY',tag='EXPIRED' if target_consumed else 'CANCEL_ON_INVALIDATION_OR_TARGET_TAKEN',locator='P4 formation-bound target / P1 event expiry')
        bid=[]
        for i,g in enumerate(gs):
            if g[0]==seed.side or g[3]>formed:continue
            price=g[4] if buy else g[5]
            if (price>entry if buy else price<entry) and not any(x.high>=g[5] if buy else x.low<=g[4] for x in bars[g[3]+1:]):
                bid.append(add(seed.id+f':p4barrier{i}','BARRIER',value=price,at=bars[g[3]].closed_at))
        refs['barrier_audit']=add(seed.id+':p4barrieraudit','BARRIER_AUDIT',tag='COMPLETE',locator=src.path+'#visible confirmed pivot/opposing FVG audit; NOT all ICT arrays')
        bound.append(seed.model_copy(update={'refs':refs,'barrier_refs':tuple(bid)}))
    seeds=bound
    if mode==5:
        m1=tf['M1'];bs=[r.bar for r in m1.bars]
        if not bs or bs[-1].closed_at!=cursor or any(a.closed_at!=z.opened_at for a,z in zip(bs,bs[1:])):
            return None,empty_audit('INSUFFICIENT_COVERAGE',tuple(a.source for a in adapted),('M1_COVERAGE_OR_CURSOR_UNVERIFIED',),registry)
        # Verify native M1/M5 aggregate consistency wherever a complete five-minute interval is visible.
        for mb in bars:
            group=[x for x in bs if mb.opened_at<=x.opened_at and x.closed_at<=mb.closed_at]
            if len(group)==5 and group[0].opened_at==mb.opened_at and group[-1].closed_at==mb.closed_at:
                if (group[0].open,max(x.high for x in group),min(x.low for x in group),group[-1].close)!=(mb.open,mb.high,mb.low,mb.close):
                    return None,empty_audit('INSUFFICIENT_COVERAGE',tuple(a.source for a in adapted),('M1_M5_AGGREGATION_MISMATCH',),registry)
        for i,bar in enumerate(bs):add('m1b'+str(i),'BAR',bar=bar,at=bar.closed_at,source=m1.source)
        refined=[];mps=pivots(bs);mgs=gaps(bs)
        for seed in seeds:
            try:lo,hi,formed,_=base_model_geometry(seed,Ledger(data.snapshot,tuple(ev)))
            except (EvidenceError,ValueError):refined.append(seed);continue
            found=None
            for side,c1,c2,c3,ml,mh in mgs:
                if side!=seed.side or not (lo<=ml<mh<=hi) or bs[c1].opened_at<formed:continue
                for kind,pi,pv,pc in reversed(mps):
                    if kind!=('HIGH' if side=='BUY' else 'LOW') or bs[pc].closed_at<formed:continue
                    breaks=[j for j in range(pc+1,c3+1) if bs[j].opened_at>=formed and (bs[j].close>pv if side=='BUY' else bs[j].close<pv)]
                    if not breaks:continue
                    j=breaks[0];level=add(seed.id+':m1level','M1_STRUCTURE',value=pv,at=bs[pc].closed_at,source=m1.source,locator=m1.source.path+f'#M1pivot={pi},confirmed={pc}')
                    found={'c1':'m1b'+str(c1),'c2':'m1b'+str(c2),'c3':'m1b'+str(c3),'break':'m1b'+str(j),'level':level};break
                if found:break
            refs=dict(seed.refs)
            if found:
                # Mode5 first creates its entry after M1 proof. Earlier M5 retest is not an already-filled Mode5 order.
                c3time=bs[int(found['c3'][3:])].closed_at;bt=bs[int(found['break'][3:])].closed_at;ready=max(c3time,bt)
                a=bs[int(found['c1'][3:])];z=bs[int(found['c3'][3:])]
                ml,mh=(a.high,z.low) if seed.side=='BUY' else (z.high,a.low)
                newentry=mh if seed.side=='BUY' else ml
                after=[x for x in bs if x.opened_at>=ready]
                w=next((e.value for e in ev if e.id==refs.get('swing')),None)
                invalid=w is None or any(x.low<w if seed.side=='BUY' else x.high>w for x in bs if x.closed_at>formed)
                touched=any(x.low<=newentry<=x.high for x in after)
                refs['poi_state']=add(seed.id+':m1poi','POI_STATE',tag='INVALID' if invalid else 'USED' if touched else 'FRESH',locator=m1.source.path+'#new M1 entry only active after M1 proof; prior M5 retest not a Mode5 fill')
            refined.append(seed.model_copy(update={'precision_refs':found or {},'refs':refs}))
        seeds=refined
    audit=audit.model_copy(update={'status':'CANDIDATES_FOUND' if seeds else 'NO_CANDIDATE_AFTER_COMPLETE_SCAN','seed_ids':tuple(s.id for s in seeds),'probes':tuple(probes),'events':tuple(events),'model_scope':tuple(c.id for c in registry.cards.values() if c.enabled),'unavailable_models':tuple(c.id for c in registry.cards.values() if not c.enabled),'diagnostics':('P4_SCOPED_VISIBLE_NATIVE_DISCOVERY','REAL_MARKET_VALIDATION_BLOCKED')})
    return data.model_copy(update={'evidence':tuple(ev),'seeds':tuple(seeds),'discovery_audit':audit.model_dump(mode='json')}),audit
