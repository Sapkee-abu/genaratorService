\`\`\`\`md

**\# Generator Service --- Plug / Wait / Next Implementation Status**

เอกสารนี้สรุปสถานะของ Generator Service โดยแยกให้ชัดเจนว่า

\- ส่วนไหนทำเสร็จแล้ว

\- ส่วนไหนเป็น Plug / Wait รอของจริง

\- ส่วนไหนยังต้อง Implement

\- เมื่อ MongoDB จริงมา ต้องตรวจสอบและแก้เฉพาะจุดใด

**---**

**\# 1. Core Generator --- DONE**

ส่วนหลักของ Generator Service ที่ Implement แล้ว

\`\`\`text

GENERATOR SERVICE

│

├── Master Agent

│ ├── Master Prompt

│ ├── Master Logic

│ └── Master Schema

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

\`\`\`\`

\> หมายเหตุ: P2/P3/P4/P8 มีโครงสร้าง Agent แล้ว แต่ยังรอ Content / Data
จริงและการทดสอบจริง

**---**

**\# 2. MongoDB --- 🔌 PLUG / WAIT**

**\## สถานะปัจจุบัน**

\* MongoDB Retrieval implementation ทำแล้ว

\* Mock / Contract Test ผ่าน **\*\*15/15\*\***

\* Retrieval Manager รองรับ MongoDB เป็น fallback หลัง ChromaDB

\* ยังไม่มี MongoDB จริงตาม Final Schema ที่เชื่อมเข้ากับระบบ

\* ยังไม่มี Real E2E PASS กับ MongoDB จริง

**\## Final MongoDB Schema**

MongoDB จริงต้องใช้ 9 Collections ตาม \`dataschema.md\`

\`\`\`text

1\. curricula

2\. persons

3\. educations

4\. appointments

5\. academic_works

6\. documents

7\. ps_requirements

8\. data_usages

9\. generated_documents

\`\`\`

**\## เมื่อ MongoDB จริงพร้อม**

ต้องตรวจสอบตามลำดับ:

\`\`\`text

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

\`\`\`

**\## สิ่งที่ต้องตรวจสอบ**

**\### Connection**

\`\`\`text

MONGODB_URI

MONGODB_DB_NAME

\`\`\`

**\### Collections**

ตรวจว่ามีครบทั้ง 9 Collections

**\### Schema**

ตรวจว่า Field และ Data Type สอดคล้องกับ Final Schema

**\### Relationships**

\`\`\`text

appointments

├── curriculumId → curricula.\_id

└── personId → persons.\_id

educations

└── personId → persons.\_id

academic_works

└── personId → persons.\_id

documents

└── curriculumId → curricula.\_id

data_usages

└── curriculumId → curricula.\_id

generated_documents

└── curriculumId → curricula.\_id

\`\`\`

**\## ถ้าพบปัญหาเมื่อใช้ MongoDB จริง**

ให้แก้เฉพาะ Defect ที่ตรวจพบจริง เช่น:

\`\`\`text

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

\`\`\`

**\*\*ไม่ควรแก้ MongoDB Retrieval ล่วงหน้า หากยังไม่พบ Defect จาก Real
MongoDB\*\***

**\## สิ่งที่ห้ามทำ**

\`\`\`text

❌ ใช้ evidence_chunks เป็น Final Schema

❌ ใช้ evidence_documents เป็น Final Schema

❌ เพิ่ม 2 Collections นี้เข้า dataschema.md

❌ Remap Retrieval เพื่อรองรับ 2 Collections นี้

❌ Migrate ข้อมูลจาก 2 Collections นี้

❌ สร้างข้อมูลปลอมเพื่อให้ E2E PASS

❌ Bypass Verification

❌ เปลี่ยน Architecture เพียงเพื่อให้เข้ากับข้อมูล Test เดิม

\`\`\`

\`evidence_chunks\` และ \`evidence_documents\` ที่พบใน Environment
สำหรับการทดสอบ **\*\*ไม่ใช่ Final MongoDB Schema\*\***

**---**

**\# 3. ChromaDB --- 🔌 PLUG / WAIT**

**\## รอ**

\* ChromaDB Server จริง

\* Embedding Model

\* ข้อมูลที่ผ่าน Embedding

\* Vector Index

\* Real Semantic Search

**\## Flow**

\`\`\`text

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

\`\`\`

เมื่อ ChromaDB จริงพร้อม ต้องทดสอบว่า:

\`\`\`text

Data Request

      ↓

Query Embedding

      ↓

Semantic Search

      ↓

Relevant Evidence

      ↓

Agent

\`\`\`

หาก ChromaDB ไม่พบข้อมูล ระบบจึงทำ Fallback:

\`\`\`text

ChromaDB

↓ miss / unavailable

MongoDB

↓ miss / unavailable

Document / OCR

\`\`\`

**---**

**\# 4. Document / OCR --- 🔌 PLUG / WAIT**

**\## สถานะ**

Retrieval fallback structure มีแล้ว

แต่รอระบบจริงสำหรับ:

\`\`\`text

Document Extraction

OCR

Text Extraction

Document Metadata

\`\`\`

**\## Flow**

\`\`\`text

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

\`\`\`

เมื่อระบบจริงพร้อม ต้องทดสอบกับเอกสารจริง

**---**

\*\*# 5. Monitor → Readiness / Greenlight --- 🔌 PLUG / WAIT

Monitor เป็นระบบภายนอกของ Generator

## ขอบเขตหลักสูตร

ระบบมี **หลักสูตรเดียว** ตาม Data Schema

``` text
Database
└── Curriculum
      └── Single Curriculum
```

Monitor ต้องตรวจ Readiness ของหลักสูตรเดียวนี้เท่านั้น

ไม่ต้องมีระบบให้ User เลือกหรือสลับหลายหลักสูตร

## หน้าที่ของ Monitor

``` text
ตรวจสอบความพร้อมของข้อมูล
        ↓
READY / NOT_READY
```

เมื่อ Monitor ส่ง:

``` text
🟢 READY / Greenlight
```

หมายความว่า:

``` text
หลักสูตรพร้อมสำหรับการ Generate
และ Web UI สามารถเปิดปุ่ม Generate ให้ User
```

**READY / Greenlight ไม่ได้สั่งให้ Generator Generate อัตโนมัติ**

## Flow ที่ถูกต้อง

``` text
Monitor
   ↓
READY / Greenlight
   ↓
Web UI เปิดปุ่ม Generate
   ↓
User กด Generate
   ↓
Generator
   ↓
Master Agent
```

ดังนั้น:

``` text
READY ≠ Generate
```

User เป็นผู้ Trigger การ Generate ผ่าน Web UI

## Generator Responsibility

Generator:

``` text
รับ User Generate Request
      ↓
ตรวจสอบ Readiness / Greenlight ตาม Contract
      ↓
เริ่ม Generate
```

Generator **ไม่ตรวจความครบถ้วนของข้อมูลเอง**

และ Generator ไม่ใช้ Guideline / Config เพื่อเป็นตัวตัดสินว่า Data พร้อมหรือไม่

## curriculum_id

`curriculum_id` ใช้เป็นตัวระบุของหลักสูตรเดียวที่ Monitor ต้องตรวจ

ไม่ใช่ระบบเลือกหลายหลักสูตร และไม่ต้องเพิ่ม UI สำหรับเลือก Curriculum

หากระบบมี `curriculum_id` อยู่แล้วจาก Application Context / Database
ให้ใช้ค่าดังกล่าว

## Production Entry Point

Production User ต้อง Generate ผ่าน Web UI และผ่าน Readiness Flow เท่านั้น

ตัวอย่าง CLI:

``` bash
python -m master_agent.master
```

ให้ถือเป็น **Development / Test entrypoint เท่านั้น** และไม่ใช่ Production
Generation Entry Point

Production User ต้องไม่สามารถใช้ CLI เพื่อข้าม Web UI และ Readiness Flow ได้

------------------------------------------------------------------------

# 5.1 MCP Boundary --- 🔌 PLUG / WAIT

MCP ใช้เฉพาะในเส้นทางที่ AI Agent ต้องขอข้อมูลจาก Tools / Data Sources

ห้าม Criterion Agent เข้าถึง MongoDB / ChromaDB / Document-OCR โดยตรง

Flow ที่ล็อกแล้ว:

``` text
Criterion Agent
      ↓
Master Agent
      ↓
Retrieval Manager
      ↓
MCP
      ↓
MCP Tools
   ├── Chroma Search
   ├── Structured Mongo Query
   └── Document/OCR Retrieval
      ↓
Data Sources
```

## Responsibility

**Retrieval Manager**

``` text
Retrieval orchestration
Fallback
Normalization
Merge
```

**MCP**

``` text
AI → Tool/Data access boundary
```

Import Service และ Monitor Service ไม่จำเป็นต้องใช้ MCP ตาม Architecture
ปัจจุบัน เพราะไม่ได้เป็น AI Agent Retrieval Path

## MCP Tools ที่ Generator ต้องรองรับ

``` text
query_structured_data
retrieve_document
```

เมื่อของจริงพร้อม ต้องทดสอบ MCP Tool Contract และ Real Retrieval ต่อ

------------------------------------------------------------------------

# 5.2 Monitor Integration / Generate Gate --- 🔌 PLUG / WAIT

Monitor Integration เป็น External Contract ที่ต้องเชื่อมของจริง

แนวคิด Contract:

``` text
Web User
   ↓
Generate Request
   ↓
Generator API
   ↓
Monitor Readiness Check
   ↓
READY / NOT_READY
```

เมื่อ `READY`:

``` text
Web UI → Enable Generate Button
User → Click Generate
Generator → Start Generation
```

เมื่อ `NOT_READY`:

``` text
Web UI → Keep Generate Button Disabled
No Generation Job
Master Agent Not Called
```

Monitor unavailable / timeout / invalid response ต้องไม่ถูกตีความเป็น `READY`

### สถานะ Integration

``` text
Monitor Endpoint       🔌 Plug / Wait
HTTP Method             🔌 Plug / Wait
Request Contract        🔌 Plug / Wait
Response Contract       🔌 Plug / Wait
Auth                    🔌 Plug / Wait
Timeout / Error Contract🔌 Plug / Wait
```

เมื่อ Monitor API จริงพร้อม ต้องเชื่อมตาม Contract จริงก่อนยืนยัน Real E2E

------------------------------------------------------------------------

# 6. P2 Agent --- ⏳ WAIT\*\*

โครงสร้าง Agent มีแล้ว

รอ:

\`\`\`text

P2 Prompt / Content

P2 Logic ที่สมบูรณ์

P2 Data จริง

P2 Test กับข้อมูลจริง

\`\`\`

เมื่อข้อมูลจริงพร้อมจึงทดสอบ:

\`\`\`text

P2 Agent

↓

Data Request

↓

Retrieval

↓

Result JSON

↓

Verification

\`\`\`

**---**

**\# 7. P3 Agent --- ⏳ WAIT**

โครงสร้าง Agent มีแล้ว

รอ:

\`\`\`text

P3 Prompt / Content

P3 Logic ที่สมบูรณ์

P3 Data จริง

P3 Test กับข้อมูลจริง

\`\`\`

จากนั้นทดสอบ End-to-End ของ P3

**---**

**\# 8. P4 Agent --- ⏳ WAIT**

โครงสร้าง Agent มีแล้ว

รอ:

\`\`\`text

P4 Prompt / Content

P4 Logic ที่สมบูรณ์

P4 Data จริง

P4 Test กับข้อมูลจริง

\`\`\`

จากนั้นทดสอบ End-to-End ของ P4

**---**

**\# 9. P8 Agent --- ⏳ WAIT**

โครงสร้าง Agent มีแล้ว

รอ:

\`\`\`text

P8 Prompt / Content

P8 Logic ที่สมบูรณ์

P8 Data จริง

P8 Test กับข้อมูลจริง

\`\`\`

จากนั้นทดสอบ End-to-End ของ P8

**---**

**\# 10. Table 1.2 --- ⏳ WAIT**

ยังไม่ควร Implement เพิ่มจนกว่าจะมี Template DOCX จริงสำหรับตรวจสอบ

ต้องตรวจ:

\`\`\`text

Template จริง

      ↓

Table 1.2 Structure

      ↓

ตรวจว่ามี Slot / Field แบบใด

      ↓

พิจารณาว่าต้องเพิ่ม Logic หรือไม่

\`\`\`

ไม่ควรสร้าง Architecture สำหรับ Table 1.2 จากการคาดเดา

**---**

\*\*# 11. Real E2E PASS --- ⏳ WAIT

ตอนนี้มีการทดสอบ Flow หลักแล้ว แต่ยังไม่สามารถยืนยัน Real E2E PASS ด้วย Source Data
จริงได้

สิ่งที่ต้องพร้อม:

``` text
Monitor
   ↓
ตรวจหลักสูตรเดียว
   ↓
🟢 READY / Greenlight
   ↓
Web UI เปิดปุ่ม Generate
   ↓
User กด Generate
   ↓
Generator
   ↓
Master Agent
   ↓
Criterion Agent
   ↓
Data Request
   ↓
Retrieval Manager
   ↓
MCP
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

``` text
Monitor ตรวจหลักสูตรเดียว
   ↓
READY / Greenlight
   ↓
User กด Generate
   ↓
Retrieve Real Data ผ่าน Retrieval Manager / MCP
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

``` text
Verification FAIL
       ↓
Master
       ↓
SAME Agent
       ↓
Retry
```

ห้ามข้าม Verification เพื่อทำให้ E2E ผ่าน

------------------------------------------------------------------------

# 12. Document Lifecycle --- ❌ NOT IMPLEMENTED\*\*

ส่วนนี้ไม่ใช่ Plug

เป็นงานที่ต้อง Implement ต่อ

\`\`\`text

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

\`\`\`

**\## กฎ**

**\### Save**

\`\`\`text

Save

↓

Current Draft

\`\`\`

ยังไม่สร้าง Version ใหม่

**\### Download**

\`\`\`text

Download

↓

Version Snapshot

↓

generated_documents

\`\`\`

**\### Version History**

\`\`\`text

Version 1

Version 2

Version 3

...

\`\`\`

Version เก่าห้ามถูกเขียนทับ

**\### Source Data**

\`\`\`text

Source Data

     ↓

Generate

\`\`\`

เป็นข้อมูลต้นฉบับจาก Database

User Edit:

\`\`\`text

Generated Document

      ↓

User Edit

      ↓

Current Draft

\`\`\`

**\*\*User Edit ห้ามเขียนกลับไปเป็น Source Data\*\***

และเมื่อ Generate ใหม่:

\`\`\`text

Generate New

     ↓

ดึง Source Data จาก Database ใหม่

\`\`\`

ไม่ใช้ User Edit เป็น Source Data

**---**

**\# 13. Old Legacy Code**

\`criteria_agent.py\` แบบ Generic ที่มีอยู่เดิมเป็น Legacy / Inactive

ปัจจุบันใช้ Criterion Agents แยก:

\`\`\`text

PS Agent

P1 Agent

P2 Agent

P3 Agent

P4 Agent

P8 Agent

\`\`\`

ดังนั้นไม่ต้องนำ Legacy Generic Agent กลับมาใช้ใน Active Flow

**---**

\*\*# 14. สรุปสถานะทั้งหมด

  -------------------------------------------------------------------------
  ส่วน                       สถานะ                   สิ่งที่ทำแล้ว / สิ่งที่ต้องทำต่อ
  ------------------------- ----------------------- -----------------------
  Master Agent              ✅ Done                 Master Prompt / Logic /
                                                    Schema ทำแล้ว; รอ Real
                                                    E2E

  Template Parser           ✅ Done                 ทำแล้ว; ทดสอบกับ Template
                                                    จริง

  Template Structure        ✅ Done                 ทำแล้ว; ทดสอบกับ Template
                                                    จริง

  PS Agent                  ✅ Done                 โครงสร้าง/Flow ทำแล้ว;
                                                    ทดสอบกับ Real Data

  P1 Agent                  ✅ Done                 โครงสร้าง/Flow ทำแล้ว;
                                                    ทดสอบกับ Real Data

  P2 Agent                  ⏳ Wait                 Content / Logic / Data
                                                    / Test

  P3 Agent                  ⏳ Wait                 Content / Logic / Data
                                                    / Test

  P4 Agent                  ⏳ Wait                 Content / Logic / Data
                                                    / Test

  P8 Agent                  ⏳ Wait                 Content / Logic / Data
                                                    / Test

  Data Request              ✅ Done                 ทดสอบใน Real E2E

  Retrieval Manager         ✅ Done                 Orchestration /
                                                    fallback; ทดสอบ Real
                                                    Source

  MCP Boundary              🔌 Plug / Wait          เชื่อม MCP Tools จริง +
                                                    Contract Test

  MCP                       🔌 Plug / Wait          ทดสอบกับ MongoDB จริง
  `query_structured_data`                           

  MCP `retrieve_document`   🔌 Plug / Wait          ทดสอบกับ Document/OCR
                                                    จริง

  MongoDB Retrieval         ✅ Done                 Contract Test 15/15; รอ
                                                    MongoDB จริง

  MongoDB จริง               🔌 Plug                 Connection + 9
                                                    Collections + Schema +
                                                    Relationships + Data

  ChromaDB                  🔌 Plug                 Server + Embedding +
                                                    Vector Index + Real
                                                    Semantic Search

  Document/OCR              🔌 Plug                 Real Extraction / OCR /
                                                    Metadata

  Monitor Readiness         🔌 Plug                 Connect Monitor จริง +
                                                    Readiness Contract

  Single Curriculum         🔒 Locked               ตรวจหลักสูตรเดียว; ไม่ต้องทำ
                                                    Curriculum Selection

  `curriculum_id`           🔒 Locked               ใช้ระบุหลักสูตรเดียว;
                                                    ใช้ค่าจาก Context/DB หากมี

  READY / Greenlight        🔒 Locked               READY = เปิดให้ User
                                                    Generate ได้; ไม่ใช่ Auto
                                                    Generate

  Web Generate Button       🔌 Plug / Wait          READY → Enable;
                                                    NOT_READY → Disable

  User Generate Trigger     🔒 Locked               User ต้องกด Generate ผ่าน
                                                    Web UI

  Production Generation     🔒 Locked               Web UI เท่านั้น; CLI เป็น
  Entry                                             Development/Test

  Monitor → Generator Gate  🔌 Plug / Wait          READY/NOT_READY + error
                                                    handling + no bypass

  Verification              ✅ Done                 Real E2E

  Reference Mapping         ✅ Done                 Real E2E

  Template Injection        ✅ Done                 Real E2E

  Generated DOCX            ✅ Done                 Real E2E

  HTML Preview              ✅ Done                 ต่อกับ Document Lifecycle

  Table 1.2                 ⏳ Wait                 รอ Template จริง

  Document Lifecycle        ❌ Not Implemented      Edit / Save / Current
                                                    Draft / Download /
                                                    Version History

  Source Data Immutability  🔒 Locked               User Edit ห้ามเขียนกลับ
                                                    Source Data

  Generate New              🔒 Locked               ดึง Source Data จาก
                                                    DB/Retrieval ใหม่

  Real E2E PASS             ⏳ Wait                 รอ MongoDB + ChromaDB +
                                                    OCR + Monitor +
                                                    Content/Data จริง

  Legacy Generic Agent      ⚪ Inactive             ไม่ต้องนำกลับมาใช้

  Import → Monitor Boundary 🔒 Locked               Import จบที่ Data Ready;
                                                    Monitor เป็นเจ้าของ
                                                    Readiness

  Monitor → Generator       🔒 Locked               Monitor ให้ Readiness;
  Boundary                                          User เป็นผู้ Trigger
                                                    Generate
  -------------------------------------------------------------------------

------------------------------------------------------------------------

## สรุปความหมายของสถานะ

``` text
✅ DONE
ทำ Implementation แล้ว
เหลือการทดสอบ/เชื่อมของจริงตามที่ระบุ

🔌 PLUG / WAIT
โครงสร้าง/Contract ฝั่ง Generator เตรียมไว้แล้ว
รอ Service / Data Source / API จริงมาเชื่อม

⏳ WAIT
ยังมี Dependency สำคัญ เช่น Content / Data / Template จริง

❌ NOT IMPLEMENTED
ยังต้อง Implement ใหม่

🔒 LOCKED
เป็น Architecture / Business Rule ที่ตกลงและห้ามตีความเปลี่ยนเอง

⚪ INACTIVE
มีอยู่แต่ไม่อยู่ใน Active Flow
```

------------------------------------------------------------------------

# 15. Final Roadmap

``` text
CURRENT STATE

│
├── Core Generator                         ✅
├── Master Agent                           ✅
├── Criterion Agent Structure              ✅
├── Data Request                           ✅
├── Retrieval Manager                      ✅
├── MCP Boundary / Tool Wrappers           🔌
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
├── Monitor Readiness API                  🔌
├── Monitor → Generator Gate               🔌
│
├── Single Curriculum                      🔒
├── READY ≠ Generate                       🔒
├── User Clicks Generate                   🔒
├── Production = Web UI                    🔒
├── CLI = Development/Test Only            🔒
│
├── P2 / P3 / P4 / P8                      ⏳
├── Table 1.2                              ⏳
└── Real E2E PASS                          ⏳
│
▼
NEXT IMPLEMENTATION

├── Connect Real MongoDB                   🔌
├── Connect Real ChromaDB                  🔌
├── Connect Real Document/OCR              🔌
├── Connect Real Monitor API               🔌
├── Complete P2 / P3 / P4 / P8             ⏳
├── Validate Table 1.2                     ⏳
├── Real E2E PASS                          ⏳
│
└── Document Lifecycle                     ❌
      │
      ├── Edit
      ├── Save
      ├── Current Draft
      ├── Download
      └── Version History
```

## หลักการเมื่อของจริงเข้ามา\*\*

\`\`\`text

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

\`\`\`

**สรุป:** ตอนนี้ไม่ควรรื้อของเดิมที่ทำเป็น Plug / Wait หรือแก้ MongoDB Retrieval
ล่วงหน้า เพราะ Contract Test ผ่านแล้ว

สิ่งที่รวมและล็อกเพิ่มจากการวิเคราะห์ SRS ทั้ง 3:

``` text
IMPORT
   ↓
Data Ready
   ↓
MONITOR
   ↓
ตรวจหลักสูตรเดียว
   ↓
READY / NOT_READY
   ↓
WEB
   ↓
READY → เปิดปุ่ม Generate
   ↓
USER กด Generate
   ↓
GENERATOR
   ↓
Master → Agents → Retrieval Manager → MCP → Data Sources
   ↓
Verification → Reference Mapping → Injection
   ↓
DOCX / Preview / Lifecycle
```

ของจริงที่รอ:

``` text
MongoDB จริง
ChromaDB จริง
Document/OCR จริง
Monitor API จริง
P2/P3/P4/P8 Content/Data
Table 1.2 Template จริง
```

จากนั้นทำ Real E2E และแก้เฉพาะ Defect ที่ตรวจพบจริง

หลักการ:

``` text
ของจริงมา
   ↓
ทดสอบ
   ↓
ผ่าน
   → ไม่ต้องแก้

ไม่ผ่าน
   ↓
Evidence / Log
   ↓
ระบุ Defect
   ↓
แก้เฉพาะ Defect
   ↓
Regression Test
   ↓
Real E2E ใหม่
```

**เอกสารฉบับนี้อิงจาก Plug / Wait Status เดิมเป็นฐาน
และรวมการแก้ไข/ข้อกำหนดที่ล็อกเพิ่มภายหลัง โดยไม่รื้อสถานะเดิมโดยไม่จำเป็น**
