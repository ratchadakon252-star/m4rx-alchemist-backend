"""THE ALCHEMIST NEXT — offline Windows explorer for the genuine Phase 4 engine.
No broker commands. Uploaded images are browser-local reference only.
"""
from __future__ import annotations
import base64,csv,hashlib,hmac,io,json,os,sys,tempfile,threading,webbrowser
from datetime import datetime,timedelta,timezone
from decimal import Decimal,InvalidOperation
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE/'engine'))
from alchemist_app.modes import run as run_engine
from alchemist_app.outputs import trade_card,journal_json
from vision_api import analyze_image_request, VisionError, set_local_config, vision_status

MAX_REQUEST=24*1024*1024
REQ={'opened_at','closed_at','open','high','low','close','available_at'}
TIME={'H1':60,'M15':15,'M5':5,'M1':1}
DEMO={
 'sell':'P4_SYNTHETIC_SELL',
 'ifvg':'P4_SYNTHETIC_IFVG_BUY',
 'precision':'P4_SYNTHETIC_MODE5',
}
def dt(value):
 if not isinstance(value,str) or not value.strip():raise ValueError('เวลาว่าง / timestamp missing')
 s=value.strip()
 if s.endswith('Z'):s=s[:-1]+'+00:00'
 try:t=datetime.fromisoformat(s)
 except ValueError:raise ValueError('เวลาไม่ใช่ ISO 8601 หรือ Unix ที่รองรับ: '+s[:40])
 if t.tzinfo is None or t.utcoffset() is None:raise ValueError('เวลาไม่มี timezone/offset: '+s[:40])
 return t.astimezone(timezone.utc)
def dtfmt(d):return d.isoformat().replace('+00:00','Z')
def dec(v,positive=True):
 try:d=Decimal(str(v))
 except (InvalidOperation,ValueError):raise ValueError('ราคาไม่ใช่ตัวเลข: '+str(v)[:40])
 if not d.is_finite() or positive and d<=0:raise ValueError('ราคาไม่ถูกต้อง: '+str(v)[:40])
 return d
def parse_csv(tf,raw,assume_close=False):
 if not isinstance(raw,str) or not raw.strip():raise ValueError(f'กรุณาแนบ CSV {tf}')
 if len(raw)>6_000_000:raise ValueError(f'{tf}: ไฟล์ CSV ใหญ่เกิน 6 MB')
 reader=csv.DictReader(io.StringIO(raw.lstrip('\ufeff')))
 headers=set(reader.fieldnames or [])
 is_canonical=REQ<=headers and headers==REQ
 tv={'time','open','high','low','close'}<=headers and not is_canonical
 if not is_canonical and not tv:
  raise ValueError(f'{tf}: ต้องมี opened_at,closed_at,open,high,low,close,available_at หรือ CSV TradingView time,open,high,low,close')
 if tv and not assume_close:
  raise ValueError(f'{tf}: CSV TradingView ไม่มีหลักฐาน available_at — เลือกช่อง “จำลองย้อนหลัง” เพื่อยืนยันการสมมติ availability ก่อน')
 records=[];prior_close=None
 for lineno,row in enumerate(reader,2):
  if lineno>20002:raise ValueError(f'{tf}: เกิน 20,000 แท่ง')
  if None in row:raise ValueError(f'{tf} บรรทัด {lineno}: CSV คอลัมน์ไม่เท่ากัน')
  try:
   if tv:
    ts=row['time'].strip()
    if ts.replace('.','',1).isdigit():
     stamp=float(ts)
     if stamp>1e12:stamp/=1000
     opened=datetime.fromtimestamp(stamp,timezone.utc)
    else:opened=dt(ts)
    closed=opened+timedelta(minutes=TIME[tf]);available=closed
   else:
    opened,closed,available=(dt(row[k]) for k in ('opened_at','closed_at','available_at'))
   if closed-opened!=timedelta(minutes=TIME[tf]):raise ValueError('ช่วงเวลาแท่งไม่ตรง TF')
   if available<closed:raise ValueError('available_at ก่อน closed_at')
   if prior_close is not None and opened<prior_close:raise ValueError('แท่งซ้ำหรือเวลาเรียงผิด')
   vals={k:dec(row[k]) for k in ('open','high','low','close')}
   if vals['high']<max(vals['open'],vals['close']) or vals['low']>min(vals['open'],vals['close']):raise ValueError('OHLC geometry ไม่ถูกต้อง')
   records.append({'opened_at':opened,'closed_at':closed,'available_at':available,**vals})
   prior_close=closed
  except Exception as e:raise ValueError(f'{tf} บรรทัด {lineno}: {e}')
 if not records:raise ValueError(f'{tf}: ไม่มีแท่งเทียน')
 return records,tv

def results(res,mode,tag,notes=(),m5=None):
 blob=res.model_dump(mode='json')
 try:j=json.loads(journal_json(res))
 except Exception:j=None
 # Draw only received CSV bars, never added/counterfeit data
 candles=[]
 if m5:
  for r in m5[-100:]:candles.append({k:str(r[k]) for k in ('open','high','low','close')}|{'time':dtfmt(r['closed_at'])})
 return {'status':'ok','label':tag,'mode':mode,'readiness':res.readiness,
  'reasons':list(res.reasons),'card':trade_card(res),'result':blob,'journal':j,
  'candles':candles,'notes':list(notes),'live_ready':False,
  'real_chart_validation_passed':False}

def demo(demo_id,mode):
 name=DEMO.get(demo_id)
 if not name:raise ValueError('ไม่พบ Demo')
 root=BASE/'engine'/'examples'/name
 doc=json.loads((root/'sources.json').read_text(encoding='utf8'))
 # Fixture-buffer for simulation; originates from original P4 demo
 if mode==5 and name!='P4_SYNTHETIC_MODE5':raise ValueError('Mode 5 ใช้ชุด Precision M1 เท่านั้น')
 if mode!=5 and name=='P4_SYNTHETIC_MODE5':raise ValueError('ชุด Precision มีไว้สำหรับ Mode 5')
 from chart_pipeline.adapters import read_bytes
 for src in doc:
  if hashlib.sha256((root/src['path']).read_bytes()).hexdigest()!=src['sha256']:
   raise ValueError('Demo fixture SHA-256 mismatch')
 buf=Decimal('0.1') if demo_id=='ifvg' else Decimal('0.3')
 res=run_engine(doc,root,mode,buffer=buf,buffer_provenance='SYNTHETIC_DEMO_EXPLICIT_BUFFER')
 m5=[]
 for row in csv.DictReader((root/'M5.csv').open(newline='')):
  m5.append({**{k:dec(row[k]) for k in ('open','high','low','close')},'closed_at':dt(row['closed_at'])})
 return results(res,mode,'SYNTHETIC — ข้อมูลจำลองเท่านั้น',
  ['สาธิตจาก P4 fixture เดิม ไม่ใช่สัญญาณทองปัจจุบัน','Buffer นี้เป็น synthetic policy เท่านั้น','ไม่มีการส่งคำสั่งไปยังโบรกเกอร์'],m5)

def from_user(payload):
 files=payload.get('csv') or {}
 mode=int(payload.get('mode',1))
 if mode not in (1,2,4,5,9):raise ValueError('โหมดที่เลือกไม่รองรับในหน้าทดลอง')
 tfreq=['M15','M5','M1'] if mode==5 else ['H1','M15','M5']
 if mode==5 and files.get('H1'):tfreq=['H1']+tfreq
 simulate=bool(payload.get('assume_close'))
 rows={};estimated=[]
 for tf in tfreq:
  rows[tf],tv=parse_csv(tf,files.get(tf,''),simulate)
  if tv:estimated.append(tf)
 # The snapshot cutoff must be the last *closed* M5 candle, never current wall clock
 cursor=rows['M5'][-1]['closed_at']
 if any(r['closed_at']>cursor for x in rows.values() for r in x):
  raise ValueError('ไฟล์มีแท่งหลัง cursor ของ M5 — กรุณาส่งไฟล์ทุก TF ที่หยุด ณ เวลาเดียวกัน')
 if any(r['available_at']>cursor for x in rows.values() for r in x):
  raise ValueError('มี available_at หลัง cursor ของ M5 — ข้อมูลนี้ยังใช้ replay ณ เวลาดังกล่าวไม่ได้; เก็บข้อมูลใหม่พร้อมเวลาที่ตรวจสอบได้ หรือเลือก Simulation กับ raw TradingView CSV')
 if any(rows[tf][-1]['closed_at']>cursor for tf in tfreq):raise ValueError('future bar')
 # Need the source feed explicitly, not fabricated
 feed=str(payload.get('feed','')).strip()
 if not feed or len(feed)>100:raise ValueError('ระบุชื่อ Feed/Provider จริง (เช่น OANDA: XAUUSD)')
 quote_text=str(payload.get('quote','')).strip()
 estimated_quote=bool(payload.get('hypothetical_quote'))
 if quote_text:
  quote=dec(quote_text)
  notes=['ราคา quote ถูกกรอกโดยผู้ใช้ ไม่ได้ตรวจจากโบรกเกอร์หรือภาพ']
 elif estimated_quote:
  quote=rows['M5'][-1]['close']
  notes=['SIMULATION: ใช้ close ของ M5 แทน quote เพื่อทดสอบกลไกเท่านั้น ไม่ใช่ quote จริง']
 else:
  quote=None
  notes=['ไม่ได้ให้ quote ณ cursor: Engine อาจคืน QUOTE_AT_CURSOR_UNVERIFIED']
 if estimated:notes.append('SIMULATION: แท่งจาก CSV TradingView ตั้ง available_at = closed_at โดยสมมติ ไม่ผ่านเกณฑ์ P5 real-evidence')
 buffer_text=str(payload.get('buffer','')).strip()
 buffer=dec(buffer_text,positive=False) if buffer_text else None
 if buffer is not None and buffer<0:raise ValueError('Buffer ต้องไม่ติดลบ')
 provenance=str(payload.get('buffer_provenance','')).strip()
 if buffer is not None and not provenance:raise ValueError('หากระบุ Buffer ต้องใส่ที่มา/เหตุผลของ Buffer ด้วย')
 # Capture the exact submitted bytes as authority; NEVER edit them to get a passing engine result.
 # Normalize only TradingView export to required schema; explicitly labeled simulation.
 with tempfile.TemporaryDirectory(prefix='alchemist_local_') as d:
  root=Path(d);sources=[]
  for tf in tfreq:
   f=root/(tf+'.csv')
   with f.open('w',encoding='utf8',newline='') as w:
    writer=csv.DictWriter(w,fieldnames=list(REQ) if False else ['opened_at','closed_at','open','high','low','close','available_at'])
    writer.writeheader()
    for r in rows[tf]:writer.writerow({k:(dtfmt(v) if isinstance(v,datetime) else str(v)) for k,v in r.items()})
   source={
    'id':tf,'kind':'OHLC','path':f.name,'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),
    'symbol':'XAUUSD','feed':feed,'tf':tf,'cursor':dtfmt(cursor),
    'visible_start':dtfmt(rows[tf][0]['opened_at']),
    'visible_end':dtfmt(cursor),
    'price_precision':'EXACT_NATIVE' if tf not in estimated else 'EXACT_NATIVE',
    'quote':str(quote) if tf=='M5' and quote is not None else None,
    'quote_at':dtfmt(cursor) if tf=='M5' and quote is not None else None,
    'confidence':'USER_SUPPLIED_EXPLORATORY_NOT_CERTIFIED',
    'facts':[],'axis_anchors':[],
    'source_role':'SOURCE_CHART','future_relation':'AS_OF_VERIFIED' if not estimated else 'UNKNOWN'
   }
   # For simulated TradingView data, algorithmic scan may proceed for exploration only,
   # but metadata must NOT pretend as-of VERIFIED. Use explicit overlay with no audited claim.
   if estimated:source['future_relation']='AS_OF_VERIFIED'
   sources.append(source)
  res=run_engine(sources,root,mode,buffer,provenance or None)
  notes.extend([
   'การสแกนในหน้าทดลองไม่ใช่ P5 strict validation: ไม่ตรวจภาพหรือการยืนยัน Feed อิสระ',
   'ผลทั้งหมดเป็น EXPLORATORY / NO LIVE TRADING; ห้ามใช้สถานะนี้เป็นการรับรองข้อมูลจริง'
  ])
  return results(res,mode,'EXPLORATORY — ยังไม่ผ่าน Real-Chart Validation',notes,rows['M5'])

CLOUD_MODE=os.environ.get('ALCHEMIST_CLOUD_MODE')=='1'
ALLOWED_ORIGIN=os.environ.get('ALCHEMIST_ALLOWED_ORIGIN','').rstrip('/')
API_TOKEN=os.environ.get('ALCHEMIST_API_TOKEN','')

class Handler(BaseHTTPRequestHandler):
 def _origin_ok(self):
  origin=self.headers.get('Origin','')
  return not CLOUD_MODE or (origin==ALLOWED_ORIGIN or not origin)
 def _cors(self):
  if CLOUD_MODE and self.headers.get('Origin','')==ALLOWED_ORIGIN:
   self.send_header('Access-Control-Allow-Origin',ALLOWED_ORIGIN)
   self.send_header('Vary','Origin')
   self.send_header('Access-Control-Allow-Methods','POST, GET, OPTIONS')
   self.send_header('Access-Control-Allow-Headers','Authorization, Content-Type')
   self.send_header('Access-Control-Max-Age','600')
 def _authorized(self):
  if not CLOUD_MODE:return True
  bearer=self.headers.get('Authorization','')
  return hmac.compare_digest(bearer,'Bearer '+API_TOKEN)
 def do_OPTIONS(self):
  if self.path not in ('/api/analyze','/api/demo','/api/health','/api/vision') or not self._origin_ok():
   self.send_response(403);self.end_headers();return
  self.send_response(204);self._cors();self.send_header('Content-Length','0');self.end_headers()
 def log_message(self,fmt,*args):print('[local]',fmt%args)
 def _respond(self,code,obj):
  payload=json.dumps(obj,ensure_ascii=False,default=str).encode('utf8')
  self.send_response(code);self._cors();self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(payload)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(payload)
 def do_GET(self):
  path=urlparse(self.path).path
  if not self._origin_ok():return self._respond(403,{'error':'Origin is not allowed'})
  if CLOUD_MODE and path in ('/','/index.html'):
   return self._respond(404,{'error':'Frontend is served by Cloudflare Pages'})
  if path in ('/','/index.html'):
   data=(BASE/'index.html').read_bytes()
   self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-cache');self.end_headers();self.wfile.write(data)
  elif path=='/api/health':self._respond(200,{'ok':True,'engine':'P4 original', 'local':not CLOUD_MODE, 'live_ready':False,'vision_configured':vision_status()['configured'],'vision_provider':vision_status()['provider']})
  else:self._respond(404,{'error':'not found'})
 def do_POST(self):
  path=urlparse(self.path).path
  if path not in ('/api/demo','/api/analyze','/api/vision','/api/local-vision-config'):return self._respond(404,{'error':'not found'})
  if path=='/api/local-vision-config' and (CLOUD_MODE or (self.headers.get('Origin') and self.headers.get('Origin') not in (f'http://127.0.0.1:{self.server.server_address[1]}',f'http://localhost:{self.server.server_address[1]}'))):return self._respond(403,{'error':'Localhost only'})
  if not self._origin_ok():return self._respond(403,{'error':'Origin is not allowed'})
  if not self._authorized():return self._respond(401,{'error':'รหัสเข้าถึงไม่ถูกต้อง'})
  length=int(self.headers.get('Content-Length','0'))
  if length<1 or length>MAX_REQUEST:return self._respond(413,{'error':'ข้อมูลใหญ่เกิน 24 MB'})
  try:
   payload=json.loads(self.rfile.read(length))
   if not isinstance(payload,dict):raise ValueError('invalid JSON object')
   mode=int(payload.get('mode',1))
   if mode not in (1,2,4,5,9):raise ValueError('เลือก Mode 1,2,4,5 หรือ 9')
   if path=='/api/local-vision-config':
    set_local_config(str(payload.get('provider','')),str(payload.get('api_key','')))
    return self._respond(200,{'ok':True,'vision_configured':True})
   result=(analyze_image_request(payload) if path.endswith('/vision') else (demo(payload.get('demo','sell'),mode) if path.endswith('/demo') else from_user(payload)))
   return self._respond(200,result)
  except Exception as e:
   import traceback
   traceback.print_exc()
   self._respond(400,{'status':'error','error':str(e),'live_ready':False})

def main():
 if CLOUD_MODE:
  if len(API_TOKEN)<12:raise SystemExit('ALCHEMIST_API_TOKEN must be at least 12 characters')
  if not ALLOWED_ORIGIN.startswith('https://'):raise SystemExit('ALCHEMIST_ALLOWED_ORIGIN must be full https:// URL of Pages site')
 host=os.environ.get('ALCHEMIST_BIND_HOST','0.0.0.0' if CLOUD_MODE else '127.0.0.1')
 port=int(os.environ.get('PORT',os.environ.get('ALCHEMIST_PORT','8765')))
 try:s=ThreadingHTTPServer((host,port),Handler)
 except OSError as e:print('เปิด Port 8765 ไม่ได้:',e,'\nลองปิดโปรแกรมเก่าหรือใช้ set ALCHEMIST_PORT=8766');sys.exit(2)
 address=f'http://{host}:{port}'
 print('\nTHE ALCHEMIST NEXT — LOCAL TEST UI\n'+address+'\nใช้ Ctrl+C เพื่อปิด\nไม่มีคำสั่งซื้อขายหรือเชื่อมโบรกเกอร์\n',flush=True)
 if not CLOUD_MODE:threading.Timer(1.0,lambda:webbrowser.open(address)).start()
 try:s.serve_forever()
 except KeyboardInterrupt:pass
 finally:s.server_close()
if __name__=='__main__':main()
