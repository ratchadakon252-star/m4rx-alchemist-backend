"""Strict file adapters. Screenshot facts stay bounded/unknown, never invented OHLC."""
from pathlib import Path
from hashlib import sha256
import csv,json
from .contracts import ChartSource,Adapted,TimedBar
from alchemist_next.schemas import Bar,Snapshot,EvidenceRecord
from decimal import Decimal


def read_bytes(source,root):
    root=Path(root).resolve();path=(root/source.path).resolve()
    if not path.is_relative_to(root):raise ValueError('SOURCE_PATH_OUTSIDE_ROOT')
    data=path.read_bytes()
    if sha256(data).hexdigest()!=source.sha256:raise ValueError('SOURCE_HASH_MISMATCH')
    return data


def adapt(source:ChartSource,root,execution_scope='P3') -> Adapted:
    data=read_bytes(source,root)
    issues=[];bars=[];excluded=[]
    if source.source_role!='SOURCE_CHART':issues.append('SOURCE_ROLE_QUARANTINED')
    if source.future_relation=='AFTER_CURSOR':issues.append('FUTURE_IMAGE_QUARANTINED')
    if source.cursor is None:issues.append('FULL_CURSOR_UNVERIFIED')
    if not source.symbol or not source.feed or source.tf not in ({'H1','M15','M5','M1','W1','D1','H4'} if execution_scope=='P4' else {'H1','M15','M5'}):issues.append('SOURCE_IDENTITY_OR_TF_UNVERIFIED')
    if source.visible_start is None or source.visible_end is None:issues.append('VISIBLE_INTERVAL_UNVERIFIED')
    if source.kind=='SCREENSHOT':
        from PIL import Image
        import io
        with Image.open(io.BytesIO(data)) as image:image.load()
        # Presence of two axis labels does not reconstruct candle open/high/low/close or close timestamps.
        issues.extend(['SCREENSHOT_NO_VERIFIED_OHLC','PRICE_PRECISION_UNVERIFIED','SCAN_NOT_RUN'])
        return Adapted(source=source,bars=(),issues=tuple(dict.fromkeys(issues)),excluded_after_cursor=(),observation_only=True)
    if source.kind=='OHLC':
        reader=csv.DictReader(data.decode('utf-8-sig').splitlines())
        needed={'opened_at','closed_at','open','high','low','close','available_at'}
        if not reader.fieldnames or not needed<=set(reader.fieldnames):raise ValueError('OHLC_COLUMNS_MISSING: '+','.join(sorted(needed)))
        if set(reader.fieldnames)!=needed:raise ValueError('UNDECLARED_OHLC_COLUMNS')
        rows=list(reader)
    else:
        doc=json.loads(data)
        if set(doc)!={'reviewer_id','precision_basis','bars','notes'}:raise ValueError('MANUAL_REVIEW_SCHEMA_MISMATCH')
        if not doc['reviewer_id'] or doc['precision_basis']!='NATIVE_OHLC_EXPORT':
            issues.append('MANUAL_REVIEW_PRECISION_UNVERIFIED');rows=[]
        else:rows=doc['bars']
    if source.price_precision!='EXACT_NATIVE':issues.append('PRICE_PRECISION_UNVERIFIED')
    all_bars=[]
    for n,row in enumerate(rows,1):
        # Invalid rows raise; neither bad rows nor conflicting duplicate bars are silently discarded.
        bar=Bar.model_validate({k:row[k] for k in ['opened_at','closed_at','open','high','low','close']})
        record=TimedBar(id=f'{source.tf}:{bar.closed_at.isoformat()}',bar=bar,available_at=row['available_at'])
        all_bars.append(record)
    times=[r.bar.closed_at for r in all_bars]
    if len(times)!=len(set(times)):raise ValueError('DUPLICATE_OHLC_TIMESTAMP')
    if times!=sorted(times):raise ValueError('OHLC_ROWS_NOT_CHRONOLOGICAL')
    if not rows:issues.append('NO_OHLC_ROWS')
    from datetime import timedelta
    minutes={'M1':1,'M5':5,'M15':15,'H1':60,'H4':240,'D1':1440,'W1':10080}.get(source.tf)
    if minutes is not None:
        if any(r.bar.closed_at-r.bar.opened_at!=timedelta(minutes=minutes) for r in all_bars):raise ValueError('BAR_DURATION_TF_MISMATCH')
    for r in all_bars:
        if source.cursor is None or r.bar.closed_at>source.cursor or r.available_at>source.cursor:
            excluded.append(r.id)
        else:bars.append(r)
    if source.cursor is not None and (source.visible_start is not None and source.visible_end is not None):
        if any(not source.visible_start<=r.bar.opened_at or r.bar.closed_at>source.visible_end for r in bars):raise ValueError('BAR_OUTSIDE_DECLARED_INTERVAL')
    if source.source_role!='SOURCE_CHART' or source.future_relation!='AS_OF_VERIFIED':issues.append('AS_OF_SOURCE_NOT_VERIFIED')
    # Exact adapter records bind a single-TF partial snapshot. Discovery rebinds to the verified three-TF snapshot.
    evidence=[]
    if not issues and source.cursor and source.symbol and source.feed and source.tf:
        partial=Snapshot(symbol=source.symbol,feed=source.feed,cursor=source.cursor,mode=9,timeframes=(source.tf,),source_hashes=(source.sha256,),quote_ref=None)
        for r in bars:
            evidence.append(EvidenceRecord(id=r.id,snapshot_id=partial.snapshot_id,source_hash=source.sha256,source_kind='MANUAL' if source.kind=='MANUAL_REVIEW' else 'OHLC',locator=f'{source.path}#closed_at={r.bar.closed_at.isoformat()}',tf=source.tf,at=r.bar.closed_at,available_at=r.available_at,state='OBSERVED',role='BAR',bar=r.bar,uncertainty=Decimal(0)))
    return Adapted(source=source,bars=tuple(bars),evidence=tuple(evidence),issues=tuple(dict.fromkeys(issues)),excluded_after_cursor=tuple(excluded),observation_only=bool(issues))
