ได้ครับ อธิบายแบบ **ง่ายที่สุด** ให้มองว่าเรามี “วิธีเปิดระบบ” อยู่หลายแบบ และแต่ละแบบใช้ในสถานการณ์ต่างกัน
cd ~/Desktop/genaratorService-main
source .venv/bin/activate
---

# ก่อนอื่น: Backend กับ Frontend คืออะไร?

ระบบมี 2 ส่วนหลัก:

```text
Frontend
= หน้าเว็บที่เราเปิดใน Browser
        ↕
Backend
= ตัวที่ทำงาน Generate, Retrieval, MCP, Database ฯลฯ
```

ดังนั้นเวลาใช้งานเว็บ เราต้องเปิด **2 terminal**

```text
Terminal 1 → Backend
Terminal 2 → Frontend
```

---

# 1. ถ้าต้องการเปิดเว็บเพื่อใช้งานจริง

ใช้แบบ **Production จริง**

```bash
# Terminal 1
cd backend
uvicorn api_server:app --port 8010
```

แล้วเปิดอีก Terminal:

```bash
# Terminal 2
cd frontend
npm run dev
```

ภาพ:

```text
Terminal 1
Backend
localhost:8010
     ↑
     │ API
     ↓
Terminal 2
Frontend
localhost:5173
     ↑
     │
   Browser
```

### แต่มีเรื่องสำคัญ

Production จะมี **Monitor เป็นประตูตรวจสอบก่อน Generate**

ดังนั้นถ้าไม่มี:

```text
MONITOR_SERVICE_URL
```

แล้วกด Generate:

```text
Browser
   ↓
POST /api/generate
   ↓
Backend
   ↓
Monitor ?
   ↓
ไม่มี
   ↓
412
```

**412 ตรงนี้ไม่ได้แปลว่าระบบพัง**

มันหมายถึง:

> "ยังไม่พร้อมให้ Generate เพราะยังไม่มี Monitor"

นี่เป็น behavior ที่ตั้งใจไว้

---

# 2. ถ้าเราแค่ต้องการเปิดระบบเพื่อทดลอง Generate

อันนี้ง่ายกว่า

ใช้ **Development/Test Mode**

Backend:

```bash
cd backend
GENERATOR_DEV_MODE=true uvicorn api_server:app --port 8010
```

Frontend:

```bash
cd frontend
VITE_USE_MOCK_API=false VITE_DEV_GENERATE=true npm run dev
```

แล้วเปิด:

```text
http://localhost:5173
```

---

## แล้ว Development/Test ต่างจาก Production ยังไง?

ต่างตรง **ประตู Monitor**

### Production

```text
Generate
   ↓
ต้องผ่าน Monitor
   ↓
ถ้า READY
   ↓
Generator
```

### Development/Test

```text
Generate
   ↓
ข้าม Monitor
   ↓
Generator
```

ดังนั้น Development/Test **ไม่ได้หมายความว่า Generator เป็นของปลอม**

ตรงกันข้าม ในคำสั่งนี้:

```bash
GENERATOR_DEV_MODE=true
```

มันยังใช้ **Generator จริง**

เพียงแต่เปิด route พิเศษ:

```text
/api/dev/generate
```

เพื่อให้เราทดสอบ Generator โดยไม่ต้องมี Monitor

---

# 3. แล้ว Frontend ตัวนี้ใช้ Mock หรือข้อมูลจริง?

คำสั่งนี้:

```bash
VITE_USE_MOCK_API=false VITE_DEV_GENERATE=true npm run dev
```

มีความหมายว่า:

```text
VITE_USE_MOCK_API=false
        ↓
ไม่ใช้ Mock API
        ↓
ใช้ Backend จริง
```

และ:

```text
VITE_DEV_GENERATE=true
        ↓
ปุ่ม Generate ใช้
/api/dev/generate
```

ดังนั้น:

```text
Browser
   ↓
Frontend จริง
   ↓
Backend จริง
   ↓
Master Agent จริง
   ↓
Retrieval จริง
   ↓
MCP จริง
   ↓
MongoDB / Chroma จริง
```

**แต่ระวัง:** DB ที่ใช้คือ DB จริงตาม `.env`

ดังนั้น Generate / Save / Download สามารถเขียนข้อมูลจริงได้

---

# 4. ถ้าไม่อยากเปิดเว็บ แต่อยากรัน Generator โดยตรง

ใช้:

```bash
cd backend
python -m master_agent.master
```

อันนี้คือ:

```text
ไม่ผ่าน Browser
ไม่ผ่าน Frontend
ไม่ผ่าน API
        ↓
Master Agent
        ↓
Generator
```

เหมาะกับการ **ทดสอบตัว Generator โดยตรง**

ดังนั้นอย่าสับสนกับการใช้งานเว็บ

```text
Web:
Browser → Frontend → API → Master

CLI:
Terminal → Master
```

---

# 5. แล้ว `real_generate.py` คืออะไร?

```bash
cd backend
python scripts/real_generate.py
```

ตัวนี้ใช้สำหรับ **ทดสอบ Generator จริงแบบแยกจากข้อมูล Production**

ตามข้อมูลที่ให้มา มันใช้:

```text
Master จริง
+
Full flow จริง
+
Temp DB
```

ดังนั้นเหมาะกับการทดสอบว่า:

```text
Master
 ↓
Criterion Agent
 ↓
Retrieval
 ↓
MCP
 ↓
Template
 ↓
Verification
 ↓
DOCX
```

ทำงานครบหรือไม่ โดยไม่เอาไปยุ่งกับ DB จริง

---

# 6. แล้ว `browser_e2e.py` ล่ะ?

```bash
python scripts/browser_e2e.py
```

ตัวนี้ต่างจาก `real_generate.py` ตรงที่มันจำลอง **คนใช้เว็บจริง**

คือเปิด Chrome แล้วทำประมาณ:

```text
เปิดเว็บ
 ↓
กด Generate
 ↓
รอ Generator
 ↓
ดูผล
 ↓
ทำตาม flow ของเว็บ
```

ดังนั้น:

```text
real_generate.py
= ทดสอบ Backend/Generator

browser_e2e.py
= ทดสอบ Backend + Frontend + Browser flow
```

---

# 7. แล้ว Test ต่าง ๆ คืออะไร?

เช่น:

```bash
python scripts/test_lifecycle.py
```

ไม่ได้หมายถึง "เปิดระบบให้เราใช้"

แต่หมายถึง:

> ให้ Python ตรวจสอบว่า feature นี้ยังทำงานถูกต้องหรือไม่

เช่น:

```text
test_lifecycle.py
```

ตรวจเรื่อง:

```text
Generate
 ↓
Save
 ↓
Download
 ↓
Version
```

เป็นต้น

ส่วน:

```bash
npx tsc -b
```

คือให้ TypeScript ตรวจว่า Frontend มีปัญหาด้าน type/code หรือไม่

---

# 8. Migration คืออะไร?

คำสั่ง:

```bash
python scripts/migrate_generated_documents.py
```

อันนี้ **ไม่ใช่คำสั่งสำหรับเปิดระบบ**

มันเป็นคำสั่งสำหรับ **ปรับโครงสร้างข้อมูลเก่าใน Database**

เช่นก่อน migration:

```text
generated_documents
   ↓
1 document
   └── versions[]
       ├── v1
       ├── v2
       ├── v3
       └── ...
```

หลัง migration:

```text
generated_documents
   ├── document v1
   ├── document v2
   ├── document v3
   └── ...
```

คือ:

> **1 Version = 1 MongoDB Document**

ตอนนี้ production migrate ไปแล้ว ดังนั้น **ไม่ต้องรันอีก** เว้นแต่ต้องการตรวจสอบ

และถ้าจะตรวจสอบก่อน:

```bash
python scripts/migrate_generated_documents.py --dry-run
```

`--dry-run` = ดูว่าจะทำอะไร **แต่ยังไม่เขียนข้อมูล**

---

# สรุปให้จำง่ายมาก ๆ

มี 5 แบบหลัก:

| ต้องการทำอะไร                     | ใช้คำสั่ง                                            |
| --------------------------------- | ---------------------------------------------------- |
| 🌐 เปิดเว็บแบบ Production         | Backend + Frontend ปกติ                              |
| 🧪 เปิดเว็บเพื่อทดลอง Generate    | `GENERATOR_DEV_MODE=true` + `VITE_DEV_GENERATE=true` |
| ⚙️ ทดสอบ Master โดยตรง            | `python -m master_agent.master`                      |
| 🔬 ทดสอบ Generator แบบแยก DB      | `python scripts/real_generate.py`                    |
| 🌐 ทดสอบเว็บทั้ง flow ด้วย Chrome | `python scripts/browser_e2e.py`                      |

---

# ถ้าตอนนี้คุณอยาก “เปิดเว็บขึ้นมาดูเหมือนครั้งก่อน”

ให้ใช้ **ข้อ 2** ครับ:

### Terminal 1 — Backend

```bash
cd backend
GENERATOR_DEV_MODE=true uvicorn api_server:app --port 8010
```

### Terminal 2 — Frontend

```bash
cd frontend
VITE_USE_MOCK_API=false VITE_DEV_GENERATE=true npm run dev
```

แล้วเปิด:

```text
http://localhost:5173
```

จะได้:

```text
Browser
   ↓
Frontend จริง
   ↓
/api/dev/generate
   ↓
Master จริง
   ↓
Criterion Agent
   ↓
Retrieval Manager
   ↓
MCP Client
   ↓
MCP Server
   ↓
Chroma / MongoDB
   ↓
Generator
   ↓
DOCX
```

**นี่คือวิธีที่เหมาะที่สุดถ้าจุดประสงค์ตอนนี้คือ “เปิดเว็บแล้วกด Generate เพื่อดูระบบทำงานจริง”** โดยไม่ต้องตั้ง Monitor ก่อนครับ.
