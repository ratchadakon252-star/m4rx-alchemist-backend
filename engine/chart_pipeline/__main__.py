from pathlib import Path
from decimal import Decimal
import argparse,json
from .pipeline import run
from .contracts import ChartSource
from alchemist_next.outputs import trade_card


def main():
    p=argparse.ArgumentParser(description='P3 evidence/discovery pipeline; NO LIVE ORDERS')
    p.add_argument('sources',type=Path,help='JSON list of ChartSource objects')
    p.add_argument('--root',type=Path,default=Path('.'))
    p.add_argument('--mode',type=int,choices=[1,9],default=9)
    p.add_argument('--buffer',type=Decimal,default=None)
    p.add_argument('--buffer-provenance',default=None)
    p.add_argument('--card',action='store_true')
    a=p.parse_args();sources=[ChartSource.model_validate(x) for x in json.loads(a.sources.read_text())]
    result=run('CLI',sources,a.root,a.mode,a.buffer,a.buffer_provenance)
    if a.card and result.decision:
        # Reconstruct Snapshot from the same source inputs through the verified adapters.
        from .adapters import adapt
        from .discovery import discover
        data,_=discover(tuple(adapt(s,a.root) for s in sources),a.mode,a.buffer,a.buffer_provenance)
        print(trade_card(result.decision,data.snapshot))
    elif a.card:print(result.readiness+' | '+'; '.join(result.reasons)+' | ไม่สร้างราคาเมื่อหลักฐานยังไม่ยืนยัน')
    else:print(result.model_dump_json(indent=2))

if __name__=='__main__':main()
