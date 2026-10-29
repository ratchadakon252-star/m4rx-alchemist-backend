"""Screenshot-first preview for THE ALCHEMIST NEXT.

This is an *independent*, AI-assisted visual interpretation layer; it DOES NOT
claim to transform screenshot pixels into certified OHLC, nor to invoke the P4
price execution engine with verified bars. It only proposes and mechanically
checks hypothetical prices that the remote vision model visibly supported.
"""
from __future__ import annotations
import base64, io, json, math, os, re, urllib.error, urllib.request
from decimal import Decimal, InvalidOperation
from PIL import Image, UnidentifiedImageError

IMG_LIMIT = 4 * 1024 * 1024
ALLOWED_TF = ('H1', 'M15', 'M5', 'M1')
DEFAULT_MODEL = {'gemini': 'gemini-2.5-flash', 'openai': 'gpt-4.1-mini'}

PROMPT = '''You are THE ALCHEMIST NEXT, an ICT chart evidence reviewer for XAUUSD.
The user supplies screenshot images tagged by timeframe; each image is PRIMARY visual evidence.
Only use information ACTUALLY READABLE in the screenshot, not today's market or remembered prices.
This is a RESEARCH/PAPER-TRADING chart preview, never a live signal or validated price feed.

Check H1 market bias and external liquidity, M15 structure/POI, M5 trigger/entry; M1 when provided for precision mode.
Consider liquidity sweep, MSS/CISD with displacement, FVG/iFVG, breaker/unicorn and visible session cues.
A liquidity cluster is NOT automatically an order block. Never infer future bars. Never claim a trigger occurred if its confirmation isn't visible.
For MODE 1, confirmed only; MODE 9 anticipatory LIMIT at an already-visible POI, mark NOT CONFIRMED;
MODE 4 may show separate BUY and SELL candidates; MODE 2 context only, MUST have no setups;
MODE 5 requires visible M1 and M15/M5.

For each suggested plan, proposed prices MUST be directly readable from axes or chart labels and traceable to distinct visible structures.
If price axis or critical level isn't legible, return null prices and explain, NEVER guess. If TF image missing or incompatible, explain.
For LIMIT orders, the hypothetical order level must correspond to visible price axis. For MARKET orders, screenshot is historical; indicate hypothetical, NEVER tell a user to enter now.
Avoid generic 'WAIT' if a visible trigger exists; explain actual evidence/deficiencies.
Do not force trade plans where evidence is inadequate.

Return ONLY a JSON object with keys:
"images": object keyed H1/M15/M5/M1 with {"readable":boolean, "symbol_visible":boolean,"price_axis_readable":boolean,"observations":string};
"bias": "BUY"|"SELL"|"NEUTRAL"|"UNCERTAIN";
"narrative": string;
"liquidity_path": string;
"setups": array of objects with keys {"direction":"BUY"|"SELL", "model":string,
 "order_type":"BUY LIMIT"|"SELL LIMIT"|"BUY STOP"|"SELL STOP"|"MARKET"|"NONE",
 "trigger":"CONFIRMED"|"ANTICIPATORY"|"NOT_VISIBLE"|"UNKNOWN",
 "entry":number|null,"sl":number|null,"tp1":number|null,"tp2":number|null,
 "timeframe":string,"evidence":string,"stop_reason":string,"target_reason":string,"confidence":"LOW"|"MEDIUM"|"HIGH"};
"blockers": array of strings; "visible_chart_time": string|null.
At most 2 setups, no duplicate directions unless mode 4. All prose in Thai. Be concise and specific.'''

class VisionError(ValueError): pass

_LOCAL_PROVIDER = ''
_LOCAL_KEY = ''

def set_local_config(provider: str, api_key: str):
    """Ephemeral localhost-only setup; never persist or return secret."""
    global _LOCAL_PROVIDER, _LOCAL_KEY
    if provider not in ('gemini', 'openai'):
        raise VisionError('เลือก Gemini API หรือ OpenAI API')
    if not isinstance(api_key, str) or not (12 <= len(api_key.strip()) <= 500):
        raise VisionError('โปรดระบุ API Key ที่ถูกต้อง (อย่างน้อย 12 ตัวอักษร)')
    _LOCAL_PROVIDER, _LOCAL_KEY = provider, api_key.strip()

def vision_status():
    provider = _LOCAL_PROVIDER or os.getenv('ALCHEMIST_VISION_PROVIDER','').strip().lower()
    key = _LOCAL_KEY or os.getenv('ALCHEMIST_VISION_API_KEY','').strip()
    return {'configured':bool(key) and provider in ('gemini','openai'),'provider': provider or 'none'}

def _clean_model_reply(t):
    s = t.strip()
    if s.startswith('```'):
        s = re.sub(r'^```(?:json)?\s*', '', s)
        s = re.sub(r'\s*```$', '', s)
    try: obj = json.loads(s)
    except json.JSONDecodeError as e: raise VisionError('AI คืนผลลัพธ์ที่อ่าน JSON ไม่ได้; ลองใหม่หรือลดขนาดภาพ') from e
    if not isinstance(obj, dict): raise VisionError('ผลลัพธ์ AI ไม่ใช่ JSON object')
    return obj

def prepare_images(images, mode):
    if not isinstance(images, dict): raise VisionError('ต้องส่งรูปภาพ H1/M15/M5')
    need = ('M15','M5','M1') if mode == 5 else ('H1','M15','M5')
    for tf in need:
        if tf not in images: raise VisionError(f'ยังไม่ได้แนบภาพ {tf}')
    processed=[]; pixels=0
    for tf in ALLOWED_TF:
        if tf not in images: continue
        val=images[tf]
        if not isinstance(val,str): raise VisionError(f'{tf}: ประเภทภาพไม่ถูกต้อง')
        match=re.fullmatch(r'data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/=]+)',val)
        if not match: raise VisionError(f'{tf}: รองรับภาพ PNG, JPG หรือ WEBP เท่านั้น')
        try: raw=base64.b64decode(match.group(2),validate=True)
        except Exception as e: raise VisionError(f'{tf}: ข้อมูลภาพเสีย') from e
        if len(raw)>IMG_LIMIT: raise VisionError(f'{tf}: ภาพใหญ่เกิน 4 MB ให้ย่อภาพก่อน')
        try:
            with Image.open(io.BytesIO(raw)) as im:
                im.verify()
            with Image.open(io.BytesIO(raw)) as im:
                width,height=im.size
                if width<480 or height<250: raise VisionError(f'{tf}: ภาพเล็กเกินไป ต้องเห็นราคาและแท่งเทียนชัดเจน')
                if width*height>18_000_000: raise VisionError(f'{tf}: ภาพมีพิกเซลมากเกินไป')
        except (OSError,UnidentifiedImageError) as e: raise VisionError(f'{tf}: เปิดภาพไม่ได้') from e
        pixels+=width*height
        if pixels>35_000_000: raise VisionError('ภาพรวมกันใหญ่เกินไป')
        processed.append((tf,match.group(1),base64.b64encode(raw).decode('ascii')))
    return processed

def _request_json(url, headers, payload):
    data=json.dumps(payload,separators=(',',':')).encode('utf8')
    req=urllib.request.Request(url,data=data,headers=headers,method='POST')
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            if resp.status!=200: raise VisionError(f'Vision API HTTP {resp.status}')
            return json.load(resp)
    except urllib.error.HTTPError as e:
        # Do not expose API credentials or arbitrary upstream response bodies.
        if e.code in (401, 403):
            raise VisionError('Vision API ไม่อนุญาตให้ใช้คีย์นี้ (401/403)') from e
        if e.code == 429:
            raise VisionError('Vision API ถูกจำกัดโควตา (429)') from e

        detail = ''
        try:
            raw = e.read(4096).decode('utf-8', 'replace')
            obj = json.loads(raw)
            error_obj = obj.get('error', {}) if isinstance(obj, dict) else {}
            if isinstance(error_obj, dict):
                detail = str(error_obj.get('message', '')).replace('\r', ' ').replace('\n', ' ').strip()[:240]
        except (ValueError, AttributeError, TypeError):
            pass

        if detail:
            raise VisionError(f'Vision API HTTP {e.code}: {detail}') from e
        raise VisionError(f'Vision API ตอบ HTTP {e.code}; ตรวจโมเดลและบริการ') from e
    except urllib.error.URLError as e: raise VisionError('ติดต่อ Vision API ไม่สำเร็จ ตรวจอินเทอร์เน็ตหรือสิทธิ์เซิร์ฟเวอร์') from e
    except TimeoutError as e: raise VisionError('Vision API ตอบช้าเกินกำหนด') from e

def _list_gemini_models(api_key):
    """Return available Gemini generateContent models, preferring recent Flash models."""
    url = 'https://generativelanguage.googleapis.com/v1beta/models'
    req = urllib.request.Request(
        url,
        headers={'x-goog-api-key': api_key, 'Accept': 'application/json'},
        method='GET',
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise VisionError('Gemini ไม่อนุญาตให้ตรวจรายชื่อโมเดลด้วย API Key นี้ (401/403)') from e
        if e.code == 429:
            raise VisionError('Gemini จำกัดโควตาขณะตรวจรายชื่อโมเดล (429)') from e
        raise VisionError(f'ตรวจรายชื่อโมเดล Gemini ไม่สำเร็จ (HTTP {e.code})') from e
    except urllib.error.URLError as e:
        raise VisionError('ติดต่อ Gemini เพื่อค้นหาโมเดลสำรองไม่สำเร็จ') from e
    except (TimeoutError, json.JSONDecodeError, ValueError) as e:
        raise VisionError('Gemini คืนรายชื่อโมเดลไม่ถูกต้องหรือหมดเวลา') from e

    items = data.get('models', []) if isinstance(data, dict) else []
    candidates = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get('name', '')).strip()
        if name.startswith('models/'):
            name = name[len('models/'):]
        methods = item.get('supportedGenerationMethods', [])
        if not name.startswith('gemini-') or 'generateContent' not in methods:
            continue
        lowered = name.lower()
        # Exclude non-chat/audio/image-generation special-purpose model families.
        if any(term in lowered for term in ('embedding', 'tts', 'image', 'robotics', 'computer-use', 'live')):
            continue
        if name not in candidates:
            candidates.append(name)

    def rank(name):
        match = re.search(r'^gemini-(\d+)(?:\.(\d+))?', name.lower())
        major = int(match.group(1)) if match else 0
        minor = int(match.group(2) or 0) if match else 0
        lowered = name.lower()
        if 'flash' in lowered and 'lite' not in lowered:
            family_rank = 0
        elif 'flash' in lowered:
            family_rank = 1
        elif 'pro' in lowered:
            family_rank = 2
        else:
            family_rank = 3
        return (-major, -minor, family_rank, name)

    return sorted(candidates, key=rank)


def _gemini_generate_with_fallback(model, api_key, payload):
    """Try the configured model; if it returns 404, discover and try alternatives."""
    base = 'https://generativelanguage.googleapis.com/v1beta/models/'
    headers = {'x-goog-api-key': api_key, 'Content-Type': 'application/json'}

    def request(candidate):
        return _request_json(base + candidate + ':generateContent', headers, payload)

    fallback_error = None
    try:
        return request(model), model
    except VisionError as exc:
        if 'HTTP 404' not in str(exc):
            raise
        fallback_error = exc

    available = [candidate for candidate in _list_gemini_models(api_key) if candidate != model]
    if not available:
        raise VisionError(
            f'Gemini ตอบ HTTP 404 สำหรับโมเดล {model} และไม่พบโมเดล generateContent สำรองที่ใช้ได้'
        ) from fallback_error

    last_error = fallback_error
    # A small number of retries prevents excessive API calls while allowing fallback.
    for candidate in available[:5]:
        try:
            return request(candidate), candidate
        except VisionError as retry_error:
            last_error = retry_error
            if 'HTTP 404' in str(retry_error):
                continue
            raise

    raise VisionError(
        'Gemini ตอบ HTTP 404 กับโมเดลสำรองที่ค้นพบ ลองตรวจ API Key และรายชื่อโมเดลใน Google AI Studio'
    ) from last_error

def _query_ai(processed, mode):
    provider=_LOCAL_PROVIDER or os.getenv('ALCHEMIST_VISION_PROVIDER','').strip().lower()
    if provider not in ('gemini','openai'): raise VisionError('ยังไม่ได้ตั้งค่า AI Vision บน Backend (เลือก Gemini API หรือ OpenAI API)')
    key=_LOCAL_KEY or os.getenv('ALCHEMIST_VISION_API_KEY','').strip()
    if not key: raise VisionError('ยังไม่ได้ตั้งค่า ALCHEMIST_VISION_API_KEY บน Backend')
    model=os.getenv('ALCHEMIST_VISION_MODEL',DEFAULT_MODEL[provider]).strip()
    if not re.fullmatch(r'[A-Za-z0-9_.-]{2,90}',model): raise VisionError('ชื่อ Vision Model ไม่ถูกต้อง')
    task=f'MODE {mode} / SYMBOL XAUUSD. Images attached in order and labeled by timeframe. '
    if provider=='gemini':
        parts=[{'text':PROMPT+'\n\n'+task}]
        for tf,mime,b64 in processed:
            parts.extend([{'text':f'IMAGE TIMEFRAME: {tf}'},{'inline_data':{'mime_type':f'image/{mime}','data':b64}}])
        payload={'contents':[{'role':'user','parts':parts}],
                 'generationConfig':{'responseMimeType':'application/json','temperature':0.1,'maxOutputTokens':3500}}
        output, model = _gemini_generate_with_fallback(model, key, payload)
        try: txt=''.join(p.get('text','') for p in output['candidates'][0]['content']['parts'])
        except (KeyError,IndexError,TypeError) as e: raise VisionError('Gemini ไม่คืนข้อความวิเคราะห์ (อาจถูกบล็อก/โควตาหมด)') from e
    else:
        content=[{'type':'text','text':PROMPT+'\n\n'+task}]
        for tf,mime,b64 in processed:
            content.extend([{'type':'text','text':f'IMAGE TIMEFRAME: {tf}'},
                            {'type':'image_url','image_url':{'url':f'data:image/{mime};base64,{b64}','detail':'high'}}])
        payload={'model':model,'temperature':0.1,'max_tokens':3500,
                 'response_format':{'type':'json_object'},'messages':[{'role':'user','content':content}]}
        output=_request_json('https://api.openai.com/v1/chat/completions',
                             {'Authorization':'Bearer '+key,'Content-Type':'application/json'},payload)
        try: txt=output['choices'][0]['message']['content']
        except (KeyError,IndexError,TypeError) as e: raise VisionError('OpenAI API ไม่คืนข้อความวิเคราะห์') from e
    return _clean_model_reply(txt),provider,model

def _positive_num(value):
    if value is None or isinstance(value,bool):return None
    try: n=Decimal(str(value))
    except (InvalidOperation,ValueError):return None
    if not n.is_finite() or not Decimal('0') < n < Decimal('10000000'):return None
    return n

def _short(value,maxlen=650):
    if value is None:return ''
    return str(value).strip()[:maxlen]

def _check_plan(obj,mode):
    direction=_short(obj.get('direction'),16).upper()
    if direction not in ('BUY','SELL'):return None
    model=_short(obj.get('model'),100)
    order=_short(obj.get('order_type'),18).upper()
    if order not in ('MARKET','BUY LIMIT','SELL LIMIT','BUY STOP','SELL STOP','NONE'):order='NONE'
    trigger=_short(obj.get('trigger'),25).upper()
    if trigger not in ('CONFIRMED','ANTICIPATORY','NOT_VISIBLE','UNKNOWN'):trigger='UNKNOWN'
    evidence=_short(obj.get('evidence'))
    stop_reason=_short(obj.get('stop_reason'))
    target_reason=_short(obj.get('target_reason'))
    levels={k:_positive_num(obj.get(k)) for k in ('entry','sl','tp1','tp2')}
    issues=[]
    if mode==2:issues.append('Mode 2 เป็น HTF Context ไม่รองรับการออกแผนราคา')
    if mode==1 and trigger!='CONFIRMED':issues.append('Mode 1 ต้องมี Trigger CONFIRMED')
    if mode==9 and trigger=='ANTICIPATORY' and order not in ('BUY LIMIT','SELL LIMIT'):issues.append('Mode 9 ต้องใช้ LIMIT สำหรับแผนดัก POI')
    if trigger in ('UNKNOWN','NOT_VISIBLE'):issues.append('ยังไม่เห็นหลักฐาน Trigger / เงื่อนไขเข้าในภาพ')
    if order=='NONE' or (direction=='BUY' and order.startswith('SELL')) or (direction=='SELL' and order.startswith('BUY')):
        issues.append('ประเภทคำสั่งไม่ตรงกับทิศทาง')
    if not evidence or not stop_reason or not target_reason:issues.append('หลักฐาน Entry / SL / TP ยังไม่ครบ')
    if any(v is None for v in levels.values()):issues.append('อ่านตัวเลข Entry, SL, TP1, TP2 จากภาพได้ไม่ครบ')
    rr1=rr2=None
    if all(v is not None for v in levels.values()):
        e,s,t1,t2=(levels[k] for k in ('entry','sl','tp1','tp2'))
        if not ((direction=='BUY' and s<e<t1<=t2) or (direction=='SELL' and s>e>t1>=t2)):
            issues.append('โครงสร้าง SL/TP ผิดด้านหรือเรียงลำดับไม่ถูกต้อง')
        else:
            risk=abs(e-s)
            rr1=round(float(abs(t1-e)/risk),2)
            rr2=round(float(abs(t2-e)/risk),2)
    confidence=_short(obj.get('confidence'),8).upper()
    if confidence not in ('LOW','MEDIUM','HIGH'):confidence='LOW'
    return {'direction':direction,'model':model,'order_type':order,'trigger':trigger,
            'entry':str(levels['entry']) if levels['entry'] is not None else None,
            'sl':str(levels['sl']) if levels['sl'] is not None else None,
            'tp1':str(levels['tp1']) if levels['tp1'] is not None else None,
            'tp2':str(levels['tp2']) if levels['tp2'] is not None else None,
            'rr1':rr1,'rr2':rr2,'timeframe':_short(obj.get('timeframe'),15),
            'evidence':evidence,'stop_reason':stop_reason,'target_reason':target_reason,
            'confidence':confidence,'complete':not issues,'issues':issues}

def analyze_image_request(payload):
    mode=int(payload.get('mode',1))
    if mode not in (1,2,4,5,9):raise VisionError('รองรับ Mode 1, 2, 4, 5, 9 ในรุ่นทดสอบ')
    processed=prepare_images(payload.get('images'),mode)
    data,provider,model=_query_ai(processed,mode)
    images={}
    image_data=data.get('images') if isinstance(data.get('images'),dict) else {}
    for tf,_,_ in processed:
        node=image_data.get(tf) if isinstance(image_data.get(tf),dict) else {}
        images[tf]={'readable':node.get('readable') is True,
                    'price_axis_readable':node.get('price_axis_readable') is True,
                    'symbol_visible':node.get('symbol_visible') is True,
                    'observations':_short(node.get('observations'))}
    bias=_short(data.get('bias'),12).upper()
    if bias not in ('BUY','SELL','NEUTRAL','UNCERTAIN'):bias='UNCERTAIN'
    blockers=[_short(i,250) for i in (data.get('blockers') if isinstance(data.get('blockers'),list) else [])[:8]]
    required_tfs=('M15','M5','M1') if mode==5 else ('H1','M15','M5')
    source_ok=all(images[tf]['readable'] and images[tf]['symbol_visible'] and images[tf]['price_axis_readable'] for tf in required_tfs)
    if not source_ok:blockers.append('ภาพที่ใช้หรือแกนราคา/สัญลักษณ์อ่านได้ไม่ครบ: ราคาต้องถือว่าไม่ได้ยืนยัน')
    raw_setups=data.get('setups') if isinstance(data.get('setups'),list) else []
    plans=[_check_plan(s,mode) for s in raw_setups[:2] if isinstance(s,dict)] if mode!=2 else []
    plans=[p for p in plans if p]
    if mode!=4 and plans:plans=plans[:1]
    if not source_ok:
        for p in plans:
            p['complete']=False;p['issues'].append('ภาพ/แกนราคาอ่านไม่ครบ ห้ามใช้ราคาเป็นแผนพร้อมส่งออร์เดอร์')
    if not plans and mode!=2:blockers.append('AI ไม่พบ Setup ที่มีหลักฐานเพียงพอในภาพ (ไม่ใช่ผลยืนยันว่าไม่มีโอกาสเทรด)')
    return {'status':'ok','kind':'VISION_SCREENSHOT_PREVIEW','provider':provider,'model':model,
            'mode':mode,'bias':bias,'narrative':_short(data.get('narrative'),1600),
            'liquidity_path':_short(data.get('liquidity_path'),1000),'images':images,
            'setups':plans,'blockers':blockers,'visible_chart_time':_short(data.get('visible_chart_time'),90),
            'screenshot_only':True,'unverified':True,'live_ready':False,'real_chart_validation_passed':False,
            'engine_validation':'NOT_RUN_WITH_NATIVE_OHLC',
            'notice':'ผลอ่านภาพโดย AI เพื่อทดลองเท่านั้น ไม่ใช่ราคา OHLC ที่ยืนยันจากตลาด หรือการรัน P4 Core ด้วย Native OHLC'}
