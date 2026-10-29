# คู่มืออัปโหลด THE ALCHEMIST Backend ไป GitHub และ Render (ภาษาไทย)

## ก่อนเริ่ม

ไฟล์ ZIP ชุดนี้ **จัดโครงสร้างพร้อมใช้งานแล้ว**: หลัง Extract All ต้องเห็น `app.py`, `Dockerfile`, `requirements.txt`, `engine/` ในชั้นแรกทันที ไม่ต้องเลือกไฟล์ทีละชิ้น.

**คำเตือน:** ใน `engine/KNOWLEDGE_SOURCES/` มีเอกสาร PDF ประมาณ 31 MB ซึ่งอาจมีข้อจำกัดการใช้งาน/ลิขสิทธิ์ กรุณาตั้ง Repository เป็น **Private** และไม่แจกจ่ายโดยไม่ได้รับอนุญาต; ขนาดไฟล์ PDF อาจเกินข้อจำกัดอัปโหลดผ่านหน้าเว็บ GitHub ดังนั้นให้ใช้ GitHub Desktop. ห้าม Commit API Key, `.env`, Token, ข้อมูลบัญชี หรือรหัสผ่าน.

## A — GitHub Desktop (ไม่ต้องพิมพ์คำสั่ง)

1. ไปที่ https://desktop.github.com/ ติดตั้ง GitHub Desktop แล้ว Sign in ด้วยบัญชีเดียวกับ GitHub ที่สร้าง Repository ไว้
2. ถ้าคุณ **สร้าง Repository บน GitHub.com แล้ว** ชื่อ `m4rx-alchemist-backend` ให้เปิด GitHub Desktop → **File → Clone repository** → เลือก Repository นั้น → **Clone**. ถ้ายังไม่เคยสร้าง ให้สร้างบน https://github.com/new และเลือก **Private** พร้อมเว้น README/.gitignore/License เป็น None แล้ว Clone
3. เปิด File Explorer ที่โฟลเดอร์ที่ได้จากการ **แตก ZIP นี้** (ชื่อโฟลเดอร์ `M4RX_ALCHEMIST_GITHUB_READY`)
4. เปิด GitHub Desktop → **Repository → Show in Explorer** เพื่อเปิดโฟลเดอร์ Repository ที่ Clone มา (ชื่อ `m4rx-alchemist-backend`)
5. จากโฟลเดอร์ที่แตก ZIP: **Ctrl+A → Ctrl+C** แล้วไปโฟลเดอร์ Repository: **Ctrl+V**. ต้องเห็น `app.py`, `Dockerfile`, `requirements.txt`, `engine/` **ในโฟลเดอร์ Repository ทันที** ไม่อยู่ซ้อนอีกชั้น
6. กลับ GitHub Desktop ที่แท็บ **Changes**. ตรวจว่า **ไม่มี `.env` / คีย์จริง** และไฟล์ PDF อยู่ใน `engine/KNOWLEDGE_SOURCES/` ตามปกติ
7. ที่ช่อง Summary ด้านล่างซ้าย พิมพ์ `Initial ALCHEMIST backend` → กด **Commit to main**
8. กด **Push origin** (หรือ Publish repository หากยังสร้างในเครื่องอย่างเดียว) รอจนเสร็จ แล้วเปิด Repository บน github.com เพื่อตรวจว่ามี `Dockerfile`, `app.py`, `engine/`
9. **อย่าเปลี่ยนเป็น Public**. ห้ามโพสต์ภาพที่เปิดเผย Keys หรือ Tokens

## B — เชื่อม Render

1. เปิด https://dashboard.render.com/ → **New → Web Service**
2. เชื่อม GitHub และเลือก Repository `m4rx-alchemist-backend` → Connect
3. Service Name: `m4rx-alchemist-backend`; Branch: `main`; Root Directory: เว้นว่าง; Runtime/Language: **Docker**; Dockerfile Path: `Dockerfile`
4. เลือก Instance ตามราคาและข้อจำกัดที่เห็น **ก่อนกด Deploy** อย่าคาดว่าจะฟรีถาวรหรือไม่มีการ Sleep
5. ตั้งค่าที่ Render → Environment/Secrets (ห้ามเขียนคีย์ลงในไฟล์ GitHub):

   - `ALCHEMIST_CLOUD_MODE` = `1`
   - `ALCHEMIST_ALLOWED_ORIGIN` = `https://m4rx-alchemist-next.pages.dev` **หรือ URL Cloudflare Pages ที่ Deploy ได้จริง** (ไม่ใส่ `/` ท้าย)
   - `ALCHEMIST_API_TOKEN` = **สุ่มรหัสยาวอย่างน้อย 32 ตัวอักษร เก็บส่วนตัว**
   - `ALCHEMIST_VISION_PROVIDER` = `gemini` หรือ `openai`
   - `ALCHEMIST_VISION_API_KEY` = **API Key ของผู้ให้บริการ Vision** (คนละเรื่องกับค่าสมาชิก Gemini Pro / ChatGPT Plus)
   - `ALCHEMIST_VISION_MODEL` = ชื่อโมเดลที่ API ของคุณมีสิทธิ์ใช้; ดูตัวอย่างใน `ENV_EXAMPLE.txt` แต่ตรวจรุ่นที่ API รองรับจริง
   - `PORT` = **ไม่ต้องเพิ่ม** หาก Render กำหนดให้เอง

6. กด Deploy แล้วดู **Logs** จน Service แสดงว่า Running/Live และทดสอบลิงก์ `https://<ชื่อบริการ>.onrender.com/api/health`. ถ้าได้ JSON `ok: true` หมายถึงเซิร์ฟเวอร์ตอบแล้ว **ไม่ได้หมายถึง AI Vision พร้อมใช้งานหรือผลตลาดผ่านการรับรอง**
7. ไปหน้าเว็บ Cloudflare Pages แล้วกำหนด Backend URL (และ Access Token ตาม UI ที่หน้าเว็บรองรับ) ให้ตรงกับ Render. อย่าปล่อยโทเคนไว้ในโค้ด HTML บน GitHub หรือ Cloudflare Pages; ให้ผู้ใช้ที่ได้รับอนุญาตกรอกในหน้าเว็บอย่างปลอดภัย

## C — ถ้ามีปัญหา

- GitHub เว็บอัปโหลด PDF ไม่สำเร็จ: ใช้ GitHub Desktop เพราะ PDF >25 MB, ยังต่ำกว่า GitHub 100 MB/ไฟล์
- Render หา `Dockerfile` ไม่พบ: เช็กว่ามีไฟล์ `Dockerfile` ใน **Root ของ Repository** ไม่ได้อยู่ใต้โฟลเดอร์ซ้อน
- Render Crash ตอน Start: ตรวจ `ALCHEMIST_API_TOKEN` (อย่างน้อย 12 อักษร) และ `ALCHEMIST_ALLOWED_ORIGIN` (`https://` URL)
- เว็บไซต์เปิดได้แต่ AI ไม่ตอบ: ตรวจ Environment Variables, API Quota/ค่าใช้จ่าย, Model API, และการเชื่อม Cloudflare URL
- Browser แสดง CORS: ต้นทางที่หน้าเว็บใช้ต้องตรงกับ `ALCHEMIST_ALLOWED_ORIGIN` **แบบตรงทุกตัวอักษร**

## ข้อจำกัดปัจจุบัน

ระบบ Vision เป็น Preview: ประเมินภาพ แต่ **ไม่ได้พิสูจน์ native OHLC จากภาพ** และยังไม่ผ่าน Independent Real-Chart Validation. ไม่ควรใช้ส่งออร์เดอร์เงินจริง
