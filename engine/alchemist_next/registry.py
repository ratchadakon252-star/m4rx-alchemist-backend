from pathlib import Path
from hashlib import sha256
import zipfile
from .schemas import ModelCard, digest


P2_SHA='4c35e104caa23a56e53662dfb463aef2dc346c4cdab0d871cac4dbab74d55477'

_SOURCE_CACHE={}
P3_SHA='856530cdd7d0109b30da702fac2be51ab38de849b315da90f4f18c215cd1634f'

def verified_source_bytes(source_dir, name):
    import io
    path=source_dir/name
    if path.is_file():return path.read_bytes()
    baseline=source_dir.parent/'P2_BASELINE/ALCHEMIST_CHECKPOINT_P2.zip'
    p3=source_dir.parent/'BASELINE/ALCHEMIST_CHECKPOINT_P3.zip'
    archive=baseline if baseline.is_file() else p3
    if not archive.is_file():return None
    stat=archive.stat();key=(str(archive.resolve()),stat.st_mtime_ns,stat.st_size,name)
    if key in _SOURCE_CACHE:return _SOURCE_CACHE[key]
    raw=archive.read_bytes()
    expected=P2_SHA if archive==baseline else P3_SHA
    if sha256(raw).hexdigest()!=expected:raise ValueError('IMMUTABLE_BASELINE_HASH_MISMATCH')
    if archive==p3:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:raw=z.read('P2_BASELINE/ALCHEMIST_CHECKPOINT_P2.zip')
        if sha256(raw).hexdigest()!=P2_SHA:raise ValueError('IMMUTABLE_P2_BASELINE_HASH_MISMATCH')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        try:data=z.read('KNOWLEDGE_SOURCES/'+name)
        except KeyError:return None
    _SOURCE_CACHE[key]=data
    return data


class Registry:
    def __init__(self, directory=None, scope='P3'):
        directory = Path(directory) if directory else Path(__file__).resolve().parents[1] / 'model_cards'
        cards = [ModelCard.model_validate_json(p.read_text()) for p in sorted(directory.glob('MC*.json'))]
        if len({c.id for c in cards}) != len(cards):
            raise ValueError('Duplicate model cards')
        self.scope=scope
        cards=[c if scope in c.execution_scopes else c.model_copy(update={'enabled':False}) for c in cards]
        self.cards = {c.id: c for c in cards}
        source_dir = Path(__file__).resolve().parents[1] / 'KNOWLEDGE_SOURCES'
        verified = {}
        for c in cards:
            if c.enabled:
                for source in c.sources:
                    path = source_dir / source.file_name
                    if source.file_name not in verified:
                        data=verified_source_bytes(source_dir,source.file_name)
                        verified[source.file_name] = sha256(data).hexdigest() if data is not None else None
                    if verified[source.file_name] != source.sha256:
                        raise ValueError('VERIFIED_SOURCE_FILE_MISSING_OR_CHANGED')
        for c in cards:
            if c.enabled and any(d not in self.cards or not self.cards[d].enabled for d in c.dependencies):
                raise ValueError('Enabled dependency missing')

    def enabled(self, model_id):
        c = self.cards.get(model_id)
        return bool(c and c.enabled and c.source_status == 'VERIFIED_SCOPED')

    @property
    def hash(self):
        return digest([c.model_dump(mode='json') for c in self.cards.values()])
