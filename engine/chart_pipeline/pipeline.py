from .contracts import PipelineResult,ChartSource
from .adapters import adapt
from .discovery import discover,empty_audit
from alchemist_next import analyze
from alchemist_next.schemas import State
from alchemist_next.outputs import selected


def run(case_id,sources,root,mode=9,buffer=None,buffer_provenance=None,registry=None):
    if mode not in (1,9):raise ValueError('UNSUPPORTED_MODE')
    sources=tuple(ChartSource.model_validate(s) if isinstance(s,dict) else s for s in sources)
    if not sources:
        return PipelineResult(case_id=case_id,mode=mode,readiness='DATA_UNVERIFIED',reasons=('ORIGINAL_IMAGE_PAIR_UNRESOLVED','SCAN_NOT_PERFORMED'),scan=empty_audit('SCAN_NOT_RUN',registry=registry),source_ids=(),decision=None)
    adapted=tuple(adapt(s,root) for s in sources)
    issues=list(dict.fromkeys(i for a in adapted for i in a.issues))
    if any(s.symbol!='XAUUSD' for s in sources):issues.append('UNSUPPORTED_SYMBOL_PROFILE')
    if len({s.tf for s in sources})!=len(sources):issues.append('TF_CONFLICT')
    data,audit=discover(adapted,mode,buffer,buffer_provenance,registry)
    if data is None:
        issues.extend(audit.diagnostics)
        if audit.status=='SCAN_NOT_RUN':issues.append('SCAN_NOT_PERFORMED')
        return PipelineResult(case_id=case_id,mode=mode,readiness='DATA_UNVERIFIED',reasons=tuple(dict.fromkeys(issues)),scan=audit,source_ids=tuple(s.id for s in sources),decision=None)
    decision=analyze(data,registry)
    c=selected(decision)
    prices={k:c.prices[k] if c else None for k in ('entry','sl','tp1','tp2')}
    return PipelineResult(case_id=case_id,mode=mode,readiness=decision.state.value,reasons=tuple(dict.fromkeys(list(decision.reasons)+issues)),scan=audit,source_ids=tuple(s.id for s in sources),decision=decision,rr1=c.rr1 if c else None,rr2=c.rr2 if c else None,**prices)
