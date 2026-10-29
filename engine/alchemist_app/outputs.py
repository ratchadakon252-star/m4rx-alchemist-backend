"""Guarded R&D output and versioned Journal v2, with legacy migration kept at boundary."""
from decimal import Decimal
from alchemist_next.schemas import State,Snapshot,digest
from alchemist_next.outputs import selected,legacy_journal,numeric_json

MODEL_NAMES={'MC04':'FVG (POI เท่านั้น)','MC05':'iFVG แบบปิดทะลุขอบเดิม','MC07':'Breaker แบบ FVG-linked','MC08':'Unicorn แบบ FVG contained ใน Breaker'}


def trade_card(result):
    if result.mode in (4,5) and result.sides:
        return '\n\n'.join(f'{side} CHECK\n'+trade_card(x) for side,x in result.sides.items())
    if result.mode==2:
        return f'MODE 2 | {result.readiness} | HTF CONTEXT ONLY\nไม่มี Entry / SL / TP / Order\n'+'; '.join(result.reasons)
    if result.readiness!='TRADE_CANDIDATE' or result.decision is None:
        text=f'MODE {result.mode} | {result.readiness} | NOT EXECUTABLE\n'+'; '.join(result.reasons[:8])
        if result.decision and result.readiness=='PREPARED_PLAN' and result.decision.candidates:
            c=result.decision.candidates[0];p=c.prices
            text+='\nDIAGNOSTIC ONLY: '+' | '.join(k.upper()+' '+str(p.get(k) if p.get(k) is not None else 'UNKNOWN') for k in ('entry','sl','tp1','tp2'))+' | RR '+str(c.rr1 if c.rr1 is not None else 'UNKNOWN')+'/'+str(c.rr2 if c.rr2 is not None else 'UNKNOWN')
        return text+'\nlive_ready=false; ข้อมูลที่ขาดไม่ถูกแทนด้วยราคา'
    c=selected(result.decision);p=c.prices;sign=Decimal(1) if c.seed.side=='BUY' else Decimal(-1)
    points1=sign*(p['tp1']-p['entry'])/Decimal('.01');points2=sign*(p['tp2']-p['entry'])/Decimal('.01')
    lane='ANTICIPATORY · PRECONFIRMATION_HIGH_RISK' if result.mode==9 else 'CONFIRMED'
    why='เกิด closed inversion ของ FVG เดิม' if c.seed.model_id=='MC05' else 'มี liquidity raid และ structural break เดิม'
    if result.mode==5:why+=' แล้วมี M1 closed break/FVG หลัง M5 setup; SL ยังป้องกันโครงสร้าง M5'
    return (f'{c.order} | Entry {p["entry"]} | SL {p["sl"]} ({c.stop_points:f} M4RX points)\n'
            f'TP1 {p["tp1"]} ({points1:f} points) | TP2 {p["tp2"]} ({points2:f} points) | RR {c.rr1:.2f}/{c.rr2:.2f}\n'
            f'MODE {result.mode} | {MODEL_NAMES.get(c.seed.model_id,c.seed.model_id)} | {lane} | TRADE_CANDIDATE\n'
            f'เหตุผล: {why}; Entry อิง POI, SL เลย protected swing และตรวจ targets/barriers แล้วภายใน scope\n'
            f'AS_OF_CURSOR {result.snapshot["cursor"]} | NATIVE/ANNOTATION_VALIDATED · NOT_PIXEL_VERIFIED\n'
            'Cancel: invalidation / target taken before entry / expiry | Risk: '+(', '.join(c.preferences) or 'CORE_PROVEN')+' / BROKER_UNVERIFIED | RR PROVISIONAL | '+result.release+' | live_ready=false')


def _journal_entries(result):
    if result.mode in (4,5) and result.sides:return [journal_entries(x)[0] for x in result.sides.values()]
    c=selected(result.decision) if result.readiness=='TRADE_CANDIDATE' and result.decision else None
    if result.readiness=='TRADE_CANDIDATE' and c is None:raise ValueError('NO_VALIDATED_PLAN')
    plan=None
    if c:
        plan={'direction':c.seed.side,'order_type':c.order,**{k:c.prices[k] for k in ('entry','sl','tp1','tp2')},'stop_M4RX_points':c.stop_points,'rr1':c.rr1,'rr2':c.rr2,'model_id':c.seed.model_id,'preference_deviations':list(c.preferences),'rr_basis':'GROSS_NATIVE_PRICE','evidence_refs':dict(c.seed.refs),'precision_refs':dict(c.seed.precision_refs),'invalidation':'model structure breach','expiry':'cancel on invalidation or target taken before entry; NOT_UNATTENDED_READY'}
    identity=result.decision.evaluation_id if result.decision else digest({'mode':result.mode,'sources':result.source_hashes,'state':result.readiness,'reasons':result.reasons})
    return [{'schema_version':'2.0.0-dev','record_id':identity,'record_type':'CONTEXT' if result.mode==2 else 'ANALYSIS','mode':result.mode,'readiness':result.readiness,'execution_lane':'ANTICIPATORY' if result.mode==9 else 'CONTEXT_ONLY' if result.mode==2 else 'CONFIRMED','snapshot':result.snapshot,'source_hashes':list(result.source_hashes),'plan':plan,'missing_or_blockers':[] if c else list(result.reasons),'analysis_diagnostics':list(result.reasons) if c else [],'risk_acceptance':{'lot':None,'maximum_cash_loss':None,'status':'BROKER_SPECS_SIZE_BUDGET_UNVERIFIED'},'lifecycle':'SIGNAL_CANDIDATE' if c else 'NO_ORDER','runtime':'ENGINE_RAN_LOCALLY','release':result.release,'live_ready':False}]


def legacy_export(result):
    if result.mode==2:raise ValueError('MODE2_CONTEXT_HAS_NO_LEGACY_TRADE_EXPORT')
    if result.mode in (4,5) and result.sides:return [legacy_export(x)[0] for x in result.sides.values()]
    if result.decision is None or result.snapshot is None:raise ValueError('NO_CORE_SNAPSHOT_FOR_LEGACY_EXPORT; use Journal v2')
    snapshot=Snapshot.model_validate(result.snapshot);obj=legacy_journal(result.decision,snapshot)
    obj['summary']=f'Mode{result.mode}: '+obj['summary'];obj['conditions'].append('PublicMode: '+str(result.mode))
    if result.mode==5:obj['timeframe']='M15/M5/M1'
    return [obj]


def journal_json(result):return numeric_json(journal_entries(result))


def readiness_counts(records):
    unique={r['record_id']:r for r in records}
    return {state:sum(r['readiness']==state for r in unique.values()) for state in sorted({r['readiness'] for r in unique.values()})}


def journal_entries(result):
    from .journal_schema import JournalEntry
    rows=_journal_entries(result)
    for row in rows:JournalEntry.model_validate(row)
    return rows


def migrate_legacy(row):
    from .journal_schema import JournalEntry
    import hashlib
    if not isinstance(row,dict) or row.get('status') not in {'TRADE','NO_TRADE','WAIT'}:raise ValueError('Unsupported legacy record')
    conditions=row.get('conditions',[])
    if not isinstance(conditions,list) or not all(isinstance(x,str) for x in conditions):raise ValueError('Invalid legacy conditions')
    reported=next((x.split(':',1)[1].strip() for x in conditions if x.startswith('Readiness:')),None)
    # Legacy prices and TRADE labels are history, never proof of a new validated candidate.
    readiness=reported if reported in {'PREPARED_PLAN','NO_VALID_SETUP','EXPIRED'} else 'DATA_UNVERIFIED'
    obj={'schema_version':'2.0.0-dev','record_id':hashlib.sha256(numeric_json(row).encode()).hexdigest(),'record_type':'ANALYSIS','mode':None,'readiness':readiness,'execution_lane':'UNKNOWN','snapshot':None,'source_hashes':[],'plan':None,'missing_or_blockers':['LEGACY_IMPORT_NOT_REVALIDATED','REPORTED_READINESS:'+str(reported)],'risk_acceptance':{'lot':None,'maximum_cash_loss':None,'status':'BROKER_SPECS_SIZE_BUDGET_UNVERIFIED'},'lifecycle':'NO_ORDER','runtime':'LEGACY_IMPORT_NOT_REVALIDATED','release':'PARTIAL_DEVELOPER_PREVIEW','live_ready':False,'reported_legacy':row}
    JournalEntry.model_validate(obj)
    return obj
