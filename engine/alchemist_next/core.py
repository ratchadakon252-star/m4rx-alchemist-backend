"""Annotation-fed candidate discovery and deterministic four-route evaluation."""
from .schemas import AnalysisInput, State, Grade, Decision, digest
from .ledger import Ledger, EvidenceError
from .registry import Registry
from .execution import complete
from .validator import validate, payload_digest
from .policy import POLICY

ROUTES=tuple((s,r) for s in ('BUY','SELL') for r in ('REVERSAL','CONTINUATION'))


def analyze(data: AnalysisInput, registry=None, policy=POLICY) -> Decision:
    registry=registry or Registry()
    ledger=Ledger(data.snapshot,data.evidence)
    if len({s.id for s in data.seeds})!=len(data.seeds):raise ValueError('DUPLICATE_CANDIDATE_ID')
    coverage_ok=True; coverage_reasons=[]
    for side,route in ROUTES:
        entries=[c for c in data.coverage if c.side==side and c.route==route]
        if len(entries)!=1:
            coverage_ok=False;coverage_reasons.append('SCAN_INCOMPLETE:'+side+'_'+route);continue
        c=entries[0]
        try:
            tag=ledger.tag(c.evidence_ref,'COVERAGE')
            if c.status!='COMPLETE' or c.end>data.snapshot.cursor or tag!=f'{side}_{route}_COMPLETE':raise EvidenceError('INCOMPLETE')
            if ledger.get(c.evidence_ref).at<c.end:raise EvidenceError('SCAN_NOT_AVAILABLE')
        except EvidenceError:
            coverage_ok=False;coverage_reasons.append('SCAN_INCOMPLETE:'+side+'_'+route)
    # Evaluate every supplied grounded hypothesis. Discovery of pivots from pixels is intentionally absent.
    candidates=[]
    for side,route in ROUTES:
        for seed in sorted((s for s in data.seeds if (s.side,s.route)==(side,route)),key=lambda s:s.id):
            c=complete(seed,ledger,registry,data.broker,policy)
            problems=validate(c,ledger,registry,policy)
            if c.state==State.TRADE and problems:
                status=State.NONE if any(x.status==Grade.FAIL for x in problems) else State.PREPARED
                c=c.model_copy(update={'state':status,'gates':c.gates+problems,'incomplete_fields':c.incomplete_fields+tuple(x.reason for x in problems if x.status==Grade.UNKNOWN)})
            elif c.state==State.TRADE:
                c=c.model_copy(update={'validation_digest':payload_digest(c)})
            candidates.append(c)
    valid=[c for c in candidates if c.state==State.TRADE]
    # All current enabled entry models have equal proof class. Then preferences, RR and stable ID.
    valid.sort(key=lambda c:(len(c.preferences),-(c.rr1 or 0),-(c.rr2 or 0),c.seed.id))
    reasons=list(coverage_reasons); selected=None
    discovery_ok=False
    if data.discovery_audit is not None:
        from chart_pipeline.contracts import ScanAudit
        audit=ScanAudit.model_validate(data.discovery_audit)
        expected_seeds=tuple(sorted(s.id for s in data.seeds))
        entry_scope={c.id for c in registry.cards.values() if c.enabled and c.role=='ENTRY_MODEL'}
        probe_pairs={(p.side,p.model_id) for p in audit.probes if p.route=='REVERSAL' and p.model_id in entry_scope and p.bars_examined>0 and p.end==data.snapshot.cursor and p.start==audit.span_start}
        discovery_ok=(audit.complete_in_scope and audit.status in {'CANDIDATES_FOUND','NO_CANDIDATE_AFTER_COMPLETE_SCAN'} and tuple(sorted(audit.seed_ids))==expected_seeds and set(audit.source_hashes)==set(data.snapshot.source_hashes) and audit.span_end==data.snapshot.cursor and all((side,model) in probe_pairs for side in ('BUY','SELL') for model in entry_scope))
        discovery_ok=discovery_ok and (any(p.status=='CANDIDATES_FOUND' for p in audit.probes)==bool(data.seeds)) and audit.status==('CANDIDATES_FOUND' if data.seeds else 'NO_CANDIDATE_AFTER_COMPLETE_SCAN')
        try:
            for p in audit.probes:
                for ref in p.evidence_ids:ledger.get(ref)
        except EvidenceError:discovery_ok=False
        if not discovery_ok:reasons.append('DISCOVERY_AUDIT_INSUFFICIENT_OR_MISMATCH')
    if not data.seeds and not discovery_ok:reasons.append('SCAN_NOT_PERFORMED')
    if data.snapshot.symbol!='XAUUSD' or data.snapshot.price_unit!='XAUUSD_NATIVE':
        state=State.NONE;reasons.append('UNSUPPORTED_SYMBOL_PROFILE')
    elif not coverage_ok or not data.snapshot.feed or not ({'M15','M5','M1'} if data.snapshot.execution_mode==5 else {'H1','M15','M5'})<=set(data.snapshot.timeframes):
        state=State.DATA;reasons.append('INPUT_OR_COVERAGE_UNVERIFIED')
    elif (not data.seeds and not discovery_ok) or (data.discovery_audit is not None and not discovery_ok):
        state=State.DATA
    elif valid:
        state=State.TRADE;selected=valid[0].seed.id
    elif any(c.state==State.PREPARED for c in candidates):state=State.PREPARED
    elif candidates and all(c.state==State.EXPIRED for c in candidates):state=State.EXPIRED
    elif any(c.state==State.DATA for c in candidates):state=State.DATA
    elif not any(c.enabled and c.role=='ENTRY_MODEL' for c in registry.cards.values()):
        state=State.DATA;reasons.append('NO_SOURCE_VERIFIED_ENTRY_MODEL')
    else:
        state=State.NONE
        if not data.seeds:reasons.append('NO_CANDIDATE_AFTER_COMPLETE_SCAN_IN_ENABLED_SCOPE')
    for c in candidates:
        reasons.extend(g.reason for g in c.gates if g.status in {Grade.FAIL,Grade.UNKNOWN})
    evaluation_id=digest({'snapshot':data.snapshot.snapshot_id,'evidence':ledger.visible_hash,'seeds':[s.model_dump(mode='json') for s in sorted(data.seeds,key=lambda s:s.id)],'coverage':[c.model_dump(mode='json') for c in sorted(data.coverage,key=lambda c:(c.side,c.route))],'policy':policy.hash,'registry':registry.hash,'broker':data.broker.model_dump(mode='json'),'discovery_audit':data.discovery_audit})
    return Decision(snapshot_id=data.snapshot.snapshot_id,evaluation_id=evaluation_id,policy_hash=policy.hash,state=state,selected_id=selected,
                    candidates=tuple(candidates),reasons=tuple(dict.fromkeys(reasons)),coverage=data.coverage,coverage_complete=coverage_ok,
                    historical_ids=tuple(c.seed.id for c in candidates if c.state==State.EXPIRED))
