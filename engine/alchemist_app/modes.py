"""Public mode router. Mode3 remains explicitly blocked without an approved index profile."""
from typing import Literal
from decimal import Decimal
from chart_pipeline.contracts import ChartSource,ScanAudit
from chart_pipeline.adapters import adapt
from alchemist_next.schemas import Typed,Decision,State,Grade,Gate,digest
from alchemist_next.registry import Registry
from alchemist_next import analyze
from .discovery import discover,pivots

class ModeResult(Typed):
    mode: Literal[1,2,3,4,5,9]
    readiness: str
    reasons: tuple[str,...]
    decision: Decision | None = None
    snapshot: dict | None = None
    scan: ScanAudit | None = None
    context: tuple[dict,...] = ()
    sides: dict[str,'ModeResult'] = {}
    source_hashes: tuple[str,...] = ()
    release: Literal['PARTIAL_DEVELOPER_PREVIEW'] = 'PARTIAL_DEVELOPER_PREVIEW'
    live_ready: Literal[False] = False


def side_decision(decision,side):
    cs=[c for c in decision.candidates if c.seed.side==side]
    valid=sorted([c for c in cs if c.state==State.TRADE],key=lambda c:(len(c.preferences),-(c.rr1 or 0),-(c.rr2 or 0),c.seed.id))
    selected=None
    if not decision.coverage_complete:state=State.DATA
    elif valid:state=State.TRADE;selected=valid[0].seed.id
    elif any(c.state==State.DATA for c in cs):state=State.DATA
    elif any(c.state==State.PREPARED for c in cs):state=State.PREPARED
    elif cs and all(c.state==State.EXPIRED for c in cs):state=State.EXPIRED
    else:state=State.NONE
    reasons=tuple(dict.fromkeys([g.reason for c in cs for g in c.gates if g.status in {Grade.UNKNOWN,Grade.FAIL}]+([] if cs else ['NO_CANDIDATE_IN_ENABLED_SIDE_SCOPE'])))
    return decision.model_copy(update={'state':state,'selected_id':selected,'reasons':reasons,'evaluation_id':digest({'evaluation':decision.evaluation_id,'side':side})})



def quality_block(result,issues):
    if not issues:return result
    decision=result.decision
    if decision:
        cs=tuple(c.model_copy(update={'state':State.DATA,'validation_digest':None,'gates':c.gates+tuple(Gate(name='native_context_quality',status=Grade.UNKNOWN,reason=x) for x in issues)}) if c.state==State.TRADE else c for c in decision.candidates)
        decision=decision.model_copy(update={'state':State.DATA,'selected_id':None,'candidates':cs,'reasons':tuple(dict.fromkeys(list(decision.reasons)+list(issues)))})
    return result.model_copy(update={'readiness':'DATA_UNVERIFIED','decision':decision,'reasons':tuple(dict.fromkeys(list(result.reasons)+list(issues))),'sides':{side:quality_block(x,issues) for side,x in result.sides.items()}})

def run(sources,root,mode=1,buffer=None,buffer_provenance=None,registry=None):
    if isinstance(mode,bool) or mode not in (1,2,3,4,5,9):raise ValueError('UNSUPPORTED_MODE')
    sources=tuple(ChartSource.model_validate(s) if isinstance(s,dict) else s for s in sources)
    hashes=tuple(s.sha256 for s in sources)
    adapted=tuple(adapt(s,root,execution_scope='P4') for s in sources)
    issues=tuple(dict.fromkeys(i for a in adapted for i in a.issues))
    if mode==3:
        reason='SOURCE_SYMBOL_UNVERIFIED_FOR_MODE3' if not sources else 'BLOCKED_ASSET_PROFILE_MODE3' if sources and all(s.symbol in {'NQ','US500','US30'} for s in sources) else 'UNSUPPORTED_ASSET_FOR_MODE3'
        return ModeResult(mode=3,readiness='DATA_UNVERIFIED',reasons=(reason,'PURE_ICT_ONLY_NO_XAU_PROFILE_INHERITANCE')+issues,source_hashes=hashes)
    if mode==2:
        facts=[]
        for a in adapted:
            if a.observation_only:continue
            bars=[r.bar for r in a.bars]
            if bars:
                last=bars[-1];facts.append({'tf':a.source.tf,'last_closed_at':last.closed_at.isoformat(),'last_closed_high':str(last.high),'last_closed_low':str(last.low),'last_closed_close':str(last.close),'confirmed_pivots':[(p[0],str(p[2]),bars[p[3]].closed_at.isoformat()) for p in pivots(bars)],'source_hash':a.source.sha256,'meaning':'Observed context only; not a trade/directional guarantee'})
        return ModeResult(mode=2,readiness='DATA_UNVERIFIED' if issues or not facts else 'CONTEXT_ONLY',reasons=issues or (('HTF_CONTEXT_ONLY_NO_ORDERS',) if facts else ('NO_USABLE_HTF_CONTEXT_EVIDENCE',)),context=tuple(facts),source_hashes=hashes)
    quality=[]
    for a in adapted:
        if (mode==5 and a.source.tf=='H1') or a.observation_only or a.source.tf not in {'H1','M15'} or not a.bars or a.source.cursor is None:continue
        age=(a.source.cursor-a.bars[-1].bar.closed_at).total_seconds()
        if age>=60*(60 if a.source.tf=='H1' else 15):quality.append('STALE_'+a.source.tf+'_CONTEXT_AT_CURSOR')
    registry=registry or Registry(scope='P4')
    lane=9 if mode==9 else 5 if mode==5 else 1
    data,audit=discover(adapted,lane,buffer,buffer_provenance,registry)
    if data is None:
        reasons=list(issues)+list(audit.diagnostics)
        if not sources:reasons+=['SCAN_NOT_PERFORMED']
        if mode==5 and 'M1' not in {s.tf for s in sources}:reasons.append('MISSING_M1_EXECUTION_SOURCE')
        if any(s.symbol!='XAUUSD' for s in sources):reasons.append('UNSUPPORTED_SYMBOL_PROFILE')
        result=ModeResult(mode=mode,readiness='DATA_UNVERIFIED',reasons=tuple(dict.fromkeys(reasons or ['SCAN_NOT_PERFORMED'])),scan=audit,source_hashes=hashes)
        if mode in (4,5):result=result.model_copy(update={'sides':{side:ModeResult(mode=mode,readiness='DATA_UNVERIFIED',reasons=result.reasons,scan=audit,source_hashes=hashes) for side in ('BUY','SELL')}})
        return result
    decision=analyze(data,registry)
    base=ModeResult(mode=mode,readiness=decision.state.value,reasons=decision.reasons,decision=decision,snapshot=data.snapshot.model_dump(mode='json'),scan=audit,source_hashes=hashes)
    if mode in (4,5):
        sides={}
        for side in ('BUY','SELL'):
            sd=side_decision(decision,side);sides[side]=ModeResult(mode=mode,readiness=sd.state.value,reasons=sd.reasons,decision=sd,snapshot=base.snapshot,scan=audit,source_hashes=hashes)
        base=base.model_copy(update={'sides':sides})
    return quality_block(base,quality)
