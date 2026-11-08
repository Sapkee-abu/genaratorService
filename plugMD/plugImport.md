````md
# Generator Service — Plug / Wait / Next Implementation Status

เอกสารนี้สรุปสถานะของ Generator Service โดยแยกให้ชัดเจนว่า
- ส่วนไหนทำเสร็จแล้ว
- ส่วนไหนเป็น Plug / Wait รอของจริง
- ส่วนไหนยังต้อง Implement
- เมื่อ MongoDB จริงมา ต้องตรวจสอบและแก้เฉพาะจุดใด

---

# 1. Core Generator — DONE

ส่วนหลักของ Generator Service ที่ Implement แล้ว

```text
GENERATOR SERVICE
│
├── Master Agent
│   ├── Master Prompt
│   ├── Master Logic
│   └── Master Schema
│
├── Template Parser
├── Template Structure
│
├── PS Agent
├── P1 Agent
├── P2 Agent
├── P3 Agent
├── P4 Agent
└── P8 Agent
│
├── Data Request
├── Retrieval Manager
├── Verification
├── Reference Mapping
├── Template Injection
│
├── Generated DOCX
└── HTML Preview
````

> หมายเหตุ: P2/P3/P4/P8 มีโครงสร้าง Agent แล้ว แต่ยังรอ Content / Data จริงและการทดสอบจริง

---

# 2. MongoDB — 🔌 PLUG / WAIT

## สถานะปัจจุบัน

* MongoDB Retrieval implementation ทำแล้ว
* Mock / Contract Test ผ่าน **15/15**
* Retrieval Manager รองรับ MongoDB เป็น fallback หลัง ChromaDB
* ยังไม่มี MongoDB จริงตาม Final Schema ที่เชื่อมเข้ากับระบบ
* ยังไม่มี Real E2E PASS กับ MongoDB จริง

## Final MongoDB Schema

MongoDB จริงต้องใช้ 9 Collections ตาม `dataschema.md`

```text
1. curricula
2. persons
3. educations
4. appointments
5. academic_works
6. documents
7. ps_requirements
8. data_usages
9. generated_documents
```

## เมื่อ MongoDB จริงพร้อม

ต้องตรวจสอบตามลำดับ:

```text
MongoDB Connection
        ↓
Database Name
        ↓
9 Collections
        ↓
Collection Schema
        ↓
Fields
        ↓
Relationships
        ↓
MongoDB Retrieval
        ↓
Retrieval Manager
        ↓
Criterion Agent
        ↓
Verification
        ↓
Real E2E
```

## สิ่งที่ต้องตรวจสอบ

### Connection

```text
MONGODB_URI
MONGODB_DB_NAME
```

### Collections

ตรวจว่ามีครบทั้ง 9 Collections

### Schema

ตรวจว่า Field และ Data Type สอดคล้องกับ Final Schema

### Relationships

```text
appointments
├── curriculumId → curricula._id
└── personId     → persons._id

educations
└── personId → persons._id

academic_works
└── personId → persons._id

documents
└── curriculumId → curricula._id

data_usages
└── curriculumId → curricula._id

generated_documents
└── curriculumId → curricula._id
```

## ถ้าพบปัญหาเมื่อใช้ MongoDB จริง

ให้แก้เฉพาะ Defect ที่ตรวจพบจริง เช่น:

```text
Schema ไม่ตรง
      ↓
แก้ Mapping / Query

Relationship ไม่ตรง
      ↓
แก้ Lookup / Query

Query ได้ข้อมูล
แต่ส่งไป Agent ไม่ถูกต้อง
      ↓
แก้ Retrieval / Data Mapping

Agent ได้ข้อมูล
แต่ Mapping เข้า Field ผิด
      ↓
แก้ Agent Mapping / Data Contract

Result JSON ไม่ผ่าน Verification
      ↓
ตรวจ Agent / Data / Reference / Schema
```

**ไม่ควรแก้ MongoDB Retrieval ล่วงหน้า หากยังไม่พบ Defect จาก Real MongoDB**

## สิ่งที่ห้ามทำ

```text
❌ ใช้ evidence_chunks เป็น Final Schema
❌ ใช้ evidence_documents เป็น Final Schema
❌ เพิ่ม 2 Collections นี้เข้า dataschema.md
❌ Remap Retrieval เพื่อรองรับ 2 Collections นี้
❌ Migrate ข้อมูลจาก 2 Collections นี้
❌ สร้างข้อมูลปลอมเพื่อให้ E2E PASS
❌ Bypass Verification
❌ เปลี่ยน Architecture เพียงเพื่อให้เข้ากับข้อมูล Test เดิม
```

`evidence_chunks` และ `evidence_documents` ที่พบใน Environment สำหรับการทดสอบ **ไม่ใช่ Final MongoDB Schema**

---

# 3. ChromaDB — 🔌 PLUG / WAIT

## รอ

* ChromaDB Server จริง
* Embedding Model
* ข้อมูลที่ผ่าน Embedding
* Vector Index
* Real Semantic Search

## Flow

```text
Source Document
      ↓
Embedding
      ↓
Vector
      ↓
ChromaDB
      ↓
Semantic Search
      ↓
Retrieved Text + Metadata
      ↓
Retrieval Manager
```

เมื่อ ChromaDB จริงพร้อม ต้องทดสอบว่า:

```text
Data Request
      ↓
Query Embedding
      ↓
Semantic Search
      ↓
Relevant Evidence
      ↓
Agent
```

หาก ChromaDB ไม่พบข้อมูล ระบบจึงทำ Fallback:

```text
ChromaDB
   ↓ miss / unavailable
MongoDB
   ↓ miss / unavailable
Document / OCR
```

---

# 4. Document / OCR — 🔌 PLUG / WAIT

## สถานะ

Retrieval fallback structure มีแล้ว

แต่รอระบบจริงสำหรับ:

```text
Document Extraction
OCR
Text Extraction
Document Metadata
```

## Flow

```text
Data Request
      ↓
Retrieval Manager
      ↓
Document / OCR
      ↓
Extracted Text
      ↓
Retrieved Data
      ↓
Criterion Agent
```

เมื่อระบบจริงพร้อม ต้องทดสอบกับเอกสารจริง

---

# 5. Monitor → Greenlight — 🔌 PLUG / WAIT

Monitor เป็นระบบภายนอกของ Generator

หน้าที่ของ Monitor:

```text
ตรวจสอบความพร้อมของข้อมูล
        ↓
Greenlight
        ↓
🟢
        ↓
Generator
```

Generator:

```text
รับ Greenlight
      ↓
เริ่ม Generate
```

Generator **ไม่ตรวจความครบถ้วนของข้อมูลเอง**

และ Generator ไม่ใช้ Guideline / Config เพื่อเป็นตัวตัดสินว่า Data พร้อมหรือไม่

---

# 6. P2 Agent — ⏳ WAIT

โครงสร้าง Agent มีแล้ว

รอ:

```text
P2 Prompt / Content
P2 Logic ที่สมบูรณ์
P2 Data จริง
P2 Test กับข้อมูลจริง
```

เมื่อข้อมูลจริงพร้อมจึงทดสอบ:

```text
P2 Agent
   ↓
Data Request
   ↓
Retrieval
   ↓
Result JSON
   ↓
Verification
```

---

# 7. P3 Agent — ⏳ WAIT

โครงสร้าง Agent มีแล้ว

รอ:

```text
P3 Prompt / Content
P3 Logic ที่สมบูรณ์
P3 Data จริง
P3 Test กับข้อมูลจริง
```

จากนั้นทดสอบ End-to-End ของ P3

---

# 8. P4 Agent — ⏳ WAIT

โครงสร้าง Agent มีแล้ว

รอ:

```text
P4 Prompt / Content
P4 Logic ที่สมบูรณ์
P4 Data จริง
P4 Test กับข้อมูลจริง
```

จากนั้นทดสอบ End-to-End ของ P4

---

# 9. P8 Agent — ⏳ WAIT

โครงสร้าง Agent มีแล้ว

รอ:

```text
P8 Prompt / Content
P8 Logic ที่สมบูรณ์
P8 Data จริง
P8 Test กับข้อมูลจริง
```

จากนั้นทดสอบ End-to-End ของ P8

---

# 10. Table 1.2 — ⏳ WAIT

ยังไม่ควร Implement เพิ่มจนกว่าจะมี Template DOCX จริงสำหรับตรวจสอบ

ต้องตรวจ:

```text
Template จริง
      ↓
Table 1.2 Structure
      ↓
ตรวจว่ามี Slot / Field แบบใด
      ↓
พิจารณาว่าต้องเพิ่ม Logic หรือไม่
```

ไม่ควรสร้าง Architecture สำหรับ Table 1.2 จากการคาดเดา

---

# 11. Real E2E PASS — ⏳ WAIT

ตอนนี้มีการทดสอบ Flow หลักแล้ว แต่ยังไม่สามารถยืนยัน Real E2E PASS ด้วย Source Data จริงได้

สิ่งที่ต้องพร้อม:

```text
Monitor
   ↓
🟢 Greenlight
   ↓
Master Agent
   ↓
Criterion Agent
   ↓
Data Request
   ↓
Retrieval Manager
   ↓
┌─────────────┐
│ ChromaDB    │
│ MongoDB     │
│ Document/OCR│
└─────────────┘
   ↓
Retrieved Data
   ↓
Criterion Agent
   ↓
Result JSON
   ↓
Verification
   ↓
PASS
   ↓
Reference Mapping
   ↓
Template Injection
   ↓
Generated DOCX
```

## เป้าหมายของ Real E2E

ต้องพิสูจน์ว่า:

```text
Greenlight
   ↓
Generate
   ↓
Retrieve Real Data
   ↓
Agent Generate
   ↓
Verification PASS
   ↓
Reference Mapping
   ↓
DOCX Injection
   ↓
Valid Generated DOCX
```

หาก FAIL:

```text
Verification FAIL
       ↓
Master
       ↓
SAME Agent
       ↓
Retry
```

ห้ามข้าม Verification เพื่อทำให้ E2E ผ่าน

---

# 12. Document Lifecycle — ❌ NOT IMPLEMENTED

ส่วนนี้ไม่ใช่ Plug

เป็นงานที่ต้อง Implement ต่อ

```text
Generated DOCX
      ↓
HTML Preview
      ↓
Edit
      ↓
Save
      ↓
Current Draft
      ↓
Download
      ↓
Version Snapshot
      ↓
Version History
```

## กฎ

### Save

```text
Save
 ↓
Current Draft
```

ยังไม่สร้าง Version ใหม่

### Download

```text
Download
 ↓
Version Snapshot
 ↓
generated_documents
```

### Version History

```text
Version 1
Version 2
Version 3
...
```

Version เก่าห้ามถูกเขียนทับ

### Source Data

```text
Source Data
     ↓
Generate
```

เป็นข้อมูลต้นฉบับจาก Database

User Edit:

```text
Generated Document
      ↓
User Edit
      ↓
Current Draft
```

**User Edit ห้ามเขียนกลับไปเป็น Source Data**

และเมื่อ Generate ใหม่:

```text
Generate New
     ↓
ดึง Source Data จาก Database ใหม่
```

ไม่ใช้ User Edit เป็น Source Data

---

# 13. Old Legacy Code

`criteria_agent.py` แบบ Generic ที่มีอยู่เดิมเป็น Legacy / Inactive

ปัจจุบันใช้ Criterion Agents แยก:

```text
PS Agent
P1 Agent
P2 Agent
P3 Agent
P4 Agent
P8 Agent
```

ดังนั้นไม่ต้องนำ Legacy Generic Agent กลับมาใช้ใน Active Flow

---

# 14. สรุปสถานะทั้งหมด

| ส่วน                 | สถานะ             | สิ่งที่ต้องทำต่อ                  |
| -------------------- | ----------------- | --------------------------------- |
| Master Agent         | ✅ Done            | รอ Real E2E                       |
| Template Parser      | ✅ Done            | ทดสอบกับ Template จริง            |
| Template Structure   | ✅ Done            | ทดสอบกับ Template จริง            |
| PS Agent             | ✅ Done            | ทดสอบกับ Real Data                |
| P1 Agent             | ✅ Done            | ทดสอบกับ Real Data                |
| P2 Agent             | ⏳ Wait            | Content / Data / Test             |
| P3 Agent             | ⏳ Wait            | Content / Data / Test             |
| P4 Agent             | ⏳ Wait            | Content / Data / Test             |
| P8 Agent             | ⏳ Wait            | Content / Data / Test             |
| Data Request         | ✅ Done            | Real E2E                          |
| Retrieval Manager    | ✅ Done            | Real Source Test                  |
| MongoDB Retrieval    | ✅ Done            | รอ MongoDB จริง                   |
| MongoDB จริง         | 🔌 Plug           | Connection + 9 Collections + Data |
| ChromaDB             | 🔌 Plug           | Server + Embedding + Index        |
| Document/OCR         | 🔌 Plug           | Real Extraction/OCR               |
| Monitor → Greenlight | 🔌 Plug           | Connect Monitor                   |
| Verification         | ✅ Done            | Real E2E                          |
| Reference Mapping    | ✅ Done            | Real E2E                          |
| Template Injection   | ✅ Done            | Real E2E                          |
| Generated DOCX       | ✅ Done            | Real E2E                          |
| HTML Preview         | ✅ Done            | ต่อกับ Lifecycle                  |
| Table 1.2            | ⏳ Wait            | รอ Template จริง                  |
| Document Lifecycle   | ❌ Not Implemented | Implement                         |
| Real E2E PASS        | ⏳ Wait            | รอ Source จริง                    |
| Legacy Generic Agent | ⚪ Inactive        | ไม่ต้องแก้                        |

---

# 15. Final Roadmap

```text
CURRENT STATE
│
├── Core Generator                         ✅
├── Master Agent                           ✅
├── Criterion Agent Structure              ✅
├── Data Request                           ✅
├── Retrieval Manager                      ✅
├── Verification                           ✅
├── Reference Mapping                      ✅
├── Template Injection                     ✅
├── DOCX Generation                        ✅
│
├── MongoDB Retrieval                      ✅
│     └── 15/15 Tests
│
├── MongoDB Real                           🔌
├── ChromaDB Real                          🔌
├── Document/OCR Real                      🔌
├── Monitor → Greenlight                  🔌
│
├── P2 / P3 / P4 / P8                      ⏳
├── Table 1.2                              ⏳
└── Real E2E PASS                          ⏳
│
▼
NEXT IMPLEMENTATION
│
└── Document Lifecycle                     ❌
      │
      ├── Preview
      ├── Edit
      ├── Save
      ├── Download
      └── Version History
```

## หลักการเมื่อของจริงเข้ามา

```text
ของจริงมา
   ↓
ทดสอบ
   ↓
ผ่าน
   → ไม่ต้องแก้

ไม่ผ่าน
   ↓
หาสาเหตุจาก Evidence / Log
   ↓
ระบุ Defect
   ↓
แก้เฉพาะ Defect
   ↓
Regression Test
   ↓
Real E2E ใหม่
```

**สรุป:** ตอนนี้ไม่ควรแก้ MongoDB Retrieval เพิ่มเอง เพราะส่วน Retrieval ผ่าน Contract Test แล้ว สิ่งที่รอคือ **MongoDB จริง + ChromaDB จริง + Document/OCR จริง + Monitor จริง + Content/Data ของ P2/P3/P4/P8** จากนั้นจึงทำ **Real E2E** และแก้เฉพาะ Defect ที่เกิดจากของจริง ส่วน **Document Lifecycle** เป็นงาน Implement ใหม่ ไม่ใช่ Plug.

```
```
