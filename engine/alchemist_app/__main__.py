from pathlib import Path
from decimal import Decimal
import argparse,json
from .modes import run
from .outputs import trade_card,journal_json,legacy_export
from alchemist_next.outputs import numeric_json


def main():
    p=argparse.ArgumentParser(description='THE ALCHEMIST P4 guarded R&D; no broker execution')
    p.add_argument('sources',type=Path)
    p.add_argument('--root',type=Path,default=Path('.'))
    p.add_argument('--mode',type=int,choices=[1,2,3,4,5,9],default=1)
    p.add_argument('--buffer',type=Decimal,default=None)
    p.add_argument('--buffer-provenance',default=None)
    p.add_argument('--format',choices=['canonical','card','journal','legacy'],default='canonical')
    a=p.parse_args();result=run(json.loads(a.sources.read_text()),a.root,a.mode,a.buffer,a.buffer_provenance)
    if a.format=='canonical':print(result.model_dump_json(indent=2))
    elif a.format=='card':print(trade_card(result))
    elif a.format=='journal':print(journal_json(result))
    else:print(numeric_json(legacy_export(result)))

if __name__=='__main__':main()
