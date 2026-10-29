import argparse,json
from pathlib import Path
from .schemas import AnalysisInput
from .core import analyze
from .outputs import trade_card,legacy_journal,numeric_json


def main():
    p=argparse.ArgumentParser(description='P2 annotation-only snapshot evaluation; no orders')
    p.add_argument('input',type=Path)
    p.add_argument('--format',choices=['canonical','card','legacy'],default='canonical')
    args=p.parse_args()
    data=AnalysisInput.model_validate_json(args.input.read_text(encoding='utf-8'))
    decision=analyze(data)
    if args.format=='canonical':print(decision.model_dump_json(indent=2))
    elif args.format=='card':print(trade_card(decision,data.snapshot))
    else:print(numeric_json(legacy_journal(decision,data.snapshot)))

if __name__=='__main__':main()
