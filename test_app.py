"""Offline smoke test of P4 original engine and Windows web layer."""
import json,traceback
from app import demo,from_user,BASE

def check():
 print('Engine source directory:',BASE/'engine')
 for id,mode in [('sell',1),('sell',2),('sell',4),('sell',9),('ifvg',9),('precision',5)]:
  result=demo(id,mode)
  assert result['status']=='ok'
  assert result['result']['live_ready'] is False
  assert result['result']['release']=='PARTIAL_DEVELOPER_PREVIEW'
  print('DEMO',id,mode,result['readiness'],repr(result['card'][:100]))
 from pathlib import Path
 sample=BASE/'engine/examples/P4_SYNTHETIC_SELL'
 original=json.loads((sample/'sources.json').read_text())
 payload={'mode':1,'feed':'P3_SYNTHETIC_NOT_MARKET','buffer':'0.30','buffer_provenance':'SYNTHETIC_DEMO','quote':'4002','csv':{tf:(sample/(tf+'.csv')).read_text() for tf in ('H1','M15','M5')}}
 result=from_user(payload)
 assert result['status']=='ok'
 print('UPLOAD canonical',result['readiness'])
 try:
  payload['csv']['M5']=payload['csv']['M5'].replace('2026-01-05T10:20:00+00:00','2026-01-06T10:20:00+00:00')
  from_user(payload)
 except ValueError as e:print('Future/invalid case blocked:',str(e)[:120])
 else:raise AssertionError('Time corruption not blocked')
 print('ALL CHECKS PASSED')
if __name__=='__main__':check()
