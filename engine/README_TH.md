# THE ALCHEMIST — Phase 4 Guarded R&D

**PARTIAL_DEVELOPER_PREVIEW** สำหรับตรวจ source, models, modes และ outputs. P3 ต้นฉบับยังเป็น PARTIAL. ยังไม่มี real-chart validation pass หรือความพร้อมเทรดเงินจริง

## ผลที่รันจริง

ดู TEST_RESULTS.json และ raw logs เป็นหลัก: retained P2/P3 tests 131 ข้อ + P4 tests ใหม่ 37 ข้อ รวม **168/168 ผ่าน**. Model/mode tests เป็นข้อมูลสังเคราะห์หรือ manual fixtures ที่ติดป้ายชัด

เคสจริงเดิม 10 กลุ่ม × 6 modes = 60 primary runs และ 60 repeats: ยัง DATA_UNVERIFIED ทั้งหมด ไม่มี priced real plan. ไม่มี native market OHLC / independent ground truth เพิ่ม จึงยังวัด recall, false rejection หรือ unsafe approval ไม่ได้

## แผนที่ความสามารถ

| Mode | สิ่งที่ทำได้ในรุ่นนี้ | ขอบเขต |
|---|---|---|
| 1 | Confirmed XAUUSD H1/M15/M5 | Native/verified evidence + model-specific closed proof |
| 2 | HTF context | ไม่มี order/Entry/SL/TP; รองรับ source TF ที่ให้จริง |
| 3 | Pure ICT index router และ asset guard | **BLOCKED** จนมี approved index profile; ไม่ใช้ risk ทองแทน |
| 4 | BUY/SELL แยกอิสระ | confirmed core; ไม่บังคับ trade ทั้งสองฝั่ง |
| 5 | M15/M5/M1 precision และ BUY/SELL แยกอิสระ | M1 หลัง M5, contained FVG+closed break, native aggregation, M5 structural SL |
| 9 | Anticipatory established model | ไม่รอ future rejection; prior model/POI/swing/targets ยังต้องครบ |

P4 เปิด MC04 FVG เป็น POI-only และ entry cards MC05 iFVG, MC07 FVG-linked Breaker, MC08 contained Unicorn. MC03 generic Continuation และ cards อื่นยัง disabled/backlog. Complete scan จำกัด enabled variants และ visible native span; ไม่หมายถึงทุกโมเดลในตลาด

## ติดตั้ง dependencies และรัน

แตก ZIP แล้วเปิด terminal ในโฟลเดอร์นี้ ใช้ Python>=3.11. Environment ที่ตรวจจริงอยู่ใน TEST_RESULTS.json

```bash
python3 -m pip install -r requirements.txt
python3 tools/run_tests.py
python3 tools/run_real_cases.py
```

Windows ใช้ `python` แทน `python3` ได้ตามการติดตั้ง. ใช้ public P4 API `alchemist_app`; `alchemist_next`/`chart_pipeline` default เก็บ P3 compatibility scope ไว้เพื่อ regression จึงไม่ใช่ public mode router ของ P4

ตัวอย่างด้านล่างเป็น **SYNTHETIC เท่านั้น**; buffer เป็นค่าของ fixture ที่ระบุเอง ไม่ใช่ค่าโบรกเกอร์

```bash
python3 -m alchemist_app examples/P4_SYNTHETIC_SELL/sources.json --root examples/P4_SYNTHETIC_SELL --mode 1 --buffer .30 --buffer-provenance SYNTHETIC_ONLY_NOT_BROKER_DEFAULT --format card
python3 -m alchemist_app examples/P4_SYNTHETIC_IFVG_BUY/sources.json --root examples/P4_SYNTHETIC_IFVG_BUY --mode 9 --buffer .10 --buffer-provenance SYNTHETIC_ONLY_NOT_BROKER_DEFAULT --format journal
python3 -m alchemist_app examples/P4_SYNTHETIC_MODE5/sources.json --root examples/P4_SYNTHETIC_MODE5 --mode 5 --buffer .30 --buffer-provenance SYNTHETIC_ONLY_NOT_BROKER_DEFAULT --format card
python3 -m alchemist_app examples/P4_SYNTHETIC_SELL/sources.json --root examples/P4_SYNTHETIC_SELL --mode 2 --format canonical
```

หากไม่ส่ง buffer ช่อง SL/RR ที่พึ่ง buffer จะ UNKNOWN แต่ยังตรวจ anchors/targets/order/expiry อื่นต่อ. Native H1/M15 ที่เก่าเกินช่วง TF ณ cursor จะบล็อก current trade และเก็บ diagnostic completion. Mode5 ตรวจ M1/M5 aggregate ที่เห็นครบ และไม่ใช้ H1 optional เป็น veto

## Real screenshots และ source preservation

P3 original archive อยู่ใน BASELINE/ ทั้งไฟล์ unchanged พร้อม source book/P2/cases เดิมซ้อนอยู่ข้างใน. ไม่บรรจุ PDF และภาพซ้ำเพื่อลดขนาด. Registry อ่าน PDF จาก nested baseline พร้อมตรวจ hashes; real-case runner แตกภาพชั่วคราวจาก archive ที่ hash ตรงแล้ว

สำหรับทดลอง CLI กับภาพเดิม:

```bash
python3 tools/runtime_assets.py .runtime_cache
python3 -m alchemist_app real_sources/E05.json --root .runtime_cache --mode 9 --format card
```

ภาพชุดนี้ไม่มี calibrated candle OHLC และ full cursor ครบ จึงควรได้ DATA_UNVERIFIED พร้อมข้อขาด ไม่ใช่ราคาแต่ง. .runtime_cache ไม่อยู่ใน checkpoint. Raw real outputs อยู่ raw/P4_REAL_DECISIONS/ และ P4_REAL_CASE_RESULTS.csv

## THE ALCHEMIST สำหรับ Project

อ่าน THE_ALCHEMIST_PROJECT/THE_ALCHEMIST_PROJECT_SKILL.md แล้วใช้เป็น Project instructions พร้อม PROJECT_KNOWLEDGE_PACK.md และ CHART_SUBMISSION_GUIDE_TH.md. เป็นเอกสาร workflow/reference ที่ผู้ใช้ขอ ไม่ใช่ personal Skill ที่ติดตั้งแล้ว และไม่เชื่อมให้ Project รัน Python อัตโนมัติ

ถ้าไม่มี engine tool จริง ให้แสดง Runtime: MANUAL_REFERENCE. ถ้ามี JSON จาก engine หรือรันเครื่องมือจริงจึงแสดง ENGINE_OUTPUT_ATTACHED พร้อม version/source ตามจริง. ไม่แสร้งว่า validator รันแล้วจากการอัปโหลด Markdown

## Journal / reports / checkpoints

- Journal v2: schemas/JournalEntry.schema.json, alchemist_app.outputs.journal_entries/journal_json; canonical readiness แยกจาก legacy NO_TRADE
- Legacy migration ไม่ยก TRADE เก่าให้ validated candidate; ดู JOURNAL_MIGRATION_GUIDE.md
- Lot/max cash loss/net costs ยัง UNKNOWN; RR เป็น gross/provisional; preference deviations แสดงตรง ๆ
- RELEASE_GATE_REPORT.md และ BLOCKERS_AND_REQUESTS.md ระบุสิ่งที่ BLOCKED / NOT_MEASURABLE
- KNOWLEDGE_COVERAGE_MATRIX.md / INVENTORY / BACKLOG เก็บ scope เดิมครบ ไม่อ้าง Knowledge Complete
- CHECKPOINTS/P4_A.zip ถึง P4_D.zip เป็น stage snapshots/deltas ต้องใช้คู่กับ immutable baseline ในแพ็กเกจนี้ ไม่ใช่ standalone live release

ตรวจ ZIP ที่รับมา:

```bash
python3 tools/verify_checkpoint.py ../ALCHEMIST_CHECKPOINT_P4.zip
```

FILES_MANIFEST.csv มีขนาดและ SHA-256 ของทุก payload ยกเว้นตัว manifest เอง; CRC ครอบ manifest. Receipt ข้าง ZIP มี archive hash หลังสร้าง. อ่าน KNOWN_LIMITATIONS ก่อนงานต่อ และไม่ประกาศ Final/Live-ready จาก unit tests
