# M4RX — THE ALCHEMIST NEXT | Backend (Developer Preview)

Python backend สำหรับเว็บไซต์ THE ALCHEMIST NEXT — IMAGE FIRST โดยอ้างอิงโค้ดจากชุด P4/P5A เดิม

> **สถานะ: Developer Preview — ไม่ใช่คำแนะนำซื้อขายหรือระบบ Live-ready**
> AI Vision อ่านภาพเพื่อช่วยทบทวนกราฟ แต่ยังไม่พิสูจน์ความแม่นยำด้วย OHLC จริงจากแหล่งเดียวกับภาพ

## ไฟล์หลัก

- `app.py` — HTTP API server (`/api/health`, `/api/vision`, `/api/demo`, `/api/analyze`)
- `vision_api.py` — ตัวเชื่อม AI Vision (ต้องตั้งค่าคีย์ API ที่ฝั่งเซิร์ฟเวอร์)
- `Dockerfile`, `requirements.txt` — ใช้ Deploy แบบ Docker บน Render หรือ Python host อื่น
- `engine/` — Core Engine, Model Cards, ไฟล์ความรู้/แหล่งอ้างอิง, ชุดทดสอบจำลอง
- `ENV_EXAMPLE.txt` — ตัวอย่างชื่อ Environment Variables (ไม่มีคีย์จริง)
- `UPLOAD_GITHUB_RENDER_TH.md` — คู่มือทีละขั้นสำหรับ GitHub Desktop และ Render

**ห้ามเปลี่ยน Repository เป็น Public โดยไม่ทบทวนไฟล์ภายใน `engine/KNOWLEDGE_SOURCES/`.**

## ทดลองใน Windows

```powershell
python -m pip install -r requirements.txt
python -m unittest test_vision -v
python test_app.py
python app.py
```

เปิด `http://127.0.0.1:8765` หากเปิดในโหมด Local สำเร็จ

## Deploy แบบ Docker

ตั้งค่า `ALCHEMIST_CLOUD_MODE=1`, `ALCHEMIST_ALLOWED_ORIGIN` เป็น URL Pages จริง, `ALCHEMIST_API_TOKEN` เป็นรหัสสุ่มยาว และกำหนดตัวเลือก Vision ตาม `ENV_EXAMPLE.txt` โดยกรอกค่าผ่าน Secrets บนบริการโฮสต์ **อย่าอัปโหลด `.env`**. โฮสต์ต้องเปิด inbound HTTP และส่ง `PORT` เข้ามา.

หน้าเว็บ Cloudflare Pages อยู่ในชุดไฟล์ **แยกต่างหาก**; ZIP นี้คือ Backend ไม่ใช่ตัวหน้าเว็บ.
