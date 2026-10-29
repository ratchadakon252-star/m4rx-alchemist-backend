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
