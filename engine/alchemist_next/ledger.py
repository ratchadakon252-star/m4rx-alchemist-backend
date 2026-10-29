"""Immutable as-of ledger; unknown, future, imprecise and bad provenance stay unknown."""
from types import MappingProxyType
from .schemas import EvidenceRecord, Snapshot, digest


class EvidenceError(ValueError):
    pass


class Ledger:
    def __init__(self, snapshot: Snapshot, records: tuple[EvidenceRecord, ...]):
        self.snapshot = snapshot
        if len({r.id for r in records}) != len(records):
            raise EvidenceError('DUPLICATE_EVIDENCE_ID')
        self.records = MappingProxyType({r.id: r for r in records})

    def get(self, ref: str | None, stack=()) -> EvidenceRecord:
        if not ref or ref not in self.records:
            raise EvidenceError('MISSING_REFERENCE')
        if ref in stack:
            raise EvidenceError('DERIVATION_CYCLE')
        r = self.records[ref]
        s = self.snapshot
        if r.snapshot_id != s.snapshot_id or r.source_hash not in s.source_hashes:
            raise EvidenceError('SOURCE_OR_SNAPSHOT_MISMATCH')
        if r.source_kind == 'POLICY' and r.role not in {'STOP_BUFFER', 'EXPIRY'}:
            raise EvidenceError('POLICY_NOT_PRICE_PROOF')
        if r.role == 'SNAPSHOT_QUOTE' and r.at != s.cursor:
            raise EvidenceError('SNAPSHOT_QUOTE_TIME_MISMATCH')
        if r.source_kind == 'LEGACY_REPORT':
            raise EvidenceError('LEGACY_NOT_CHART_EVIDENCE')
        if r.tf not in s.timeframes:
            raise EvidenceError('TF_UNVERIFIED')
        if max(r.at, r.available_at) > s.cursor or (r.bar and r.bar.closed_at > s.cursor):
            raise EvidenceError('AFTER_CURSOR')
        if r.bar and r.available_at < r.bar.closed_at:
            raise EvidenceError('BAR_NOT_AVAILABLE_AT_CLOSE')
        if r.state == 'UNKNOWN':
            raise EvidenceError('EXPLICIT_UNKNOWN')
        if r.value is not None and (r.uncertainty is None or r.uncertainty != 0):
            raise EvidenceError('PRICE_PRECISION_UNVERIFIED')
        if r.source_kind == 'IMAGE' and (r.uncertainty is None or r.uncertainty != 0):
            raise EvidenceError('IMAGE_PRECISION_UNVERIFIED')
        if r.state == 'DERIVED':
            p = [self.get(x, stack + (ref,)) for x in r.parents]
            if any(x.value is None for x in p) or max(x.available_at for x in p) > r.available_at:
                raise EvidenceError('DERIVED_PARENT_UNAVAILABLE')
            a, b = (x.value for x in p)
            computed = {'ADD': a+b, 'SUB': a-b, 'MEAN': (a+b)/2}[r.formula]
            if computed != r.value:
                raise EvidenceError('DERIVATION_MISMATCH')
        return r

    def price(self, ref, role=None):
        r = self.get(ref)
        if r.value is None or (role and r.role != role):
            raise EvidenceError('PRICE_ROLE_MISMATCH')
        return r.value

    def bar(self, ref, tf='M5'):
        r = self.get(ref)
        if r.bar is None or r.role != 'BAR' or r.tf != tf:
            raise EvidenceError(tf+'_BAR_REQUIRED')
        return r.bar

    def tag(self, ref, role):
        r = self.get(ref)
        if r.tag is None or r.role != role:
            raise EvidenceError('TAG_ROLE_MISMATCH')
        return r.tag

    @property
    def visible_hash(self):
        # Future-only additions cannot alter the canonical as-of evidence hash.
        rows=[]
        for ref in sorted(self.records):
            r=self.records[ref]
            if r.at <= self.snapshot.cursor and r.available_at <= self.snapshot.cursor:
                rows.append(r.model_dump(mode='json'))
        return digest(rows)
