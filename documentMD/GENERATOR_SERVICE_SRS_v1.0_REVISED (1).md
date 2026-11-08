# Software Requirements Specification (SRS)

# Generator Service --- AUN-QA / PS System

**Version:** 1.0\
**Status:** Locked Specification for Implementation\
**Service:** Generator Service

------------------------------------------------------------------------

# 1. Purpose

Generator Service มีหน้าที่สร้างเอกสาร AUN-QA / PS จาก Template DOCX
โดยใช้ข้อมูลจาก Source Data และ Evidence ที่ได้จาก Retrieval Layer ผ่าน
Criterion Agents

Generator Service อยู่ในระบบหลังจาก Monitor ประเมินความพร้อมของหลักสูตรแล้ว

**Greenlight 🟢 จาก Monitor ไม่ได้สั่งให้ Generator เริ่ม Generate อัตโนมัติ**
Greenlight หมายถึงหลักสูตรพร้อมสำหรับการ Generate และ Web UI สามารถเปิดให้ User
กดปุ่ม Generate ได้

Generator Service จะเริ่มกระบวนการ Generate **เมื่อ User กดปุ่ม Generate ผ่าน
Web UI** หลังจากได้รับสถานะ READY/Greenlight จาก Monitor

Generator Service ต้อง:

1.  รับ/ตรวจสอบสถานะ Greenlight จาก Monitor
2.  เริ่มกระบวนการ Generate เมื่อ User กด Generate ผ่าน Web UI หลังจาก
    Greenlight
3.  อ่านและวิเคราะห์ Template DOCX
4.  แปลง Template เป็น Template Structure JSON
5.  มอบหมายงานให้ Criterion Agent ที่เกี่ยวข้อง
6.  รับ Data Request จาก Criterion Agent
7.  ส่ง Data Request ให้ Retrieval Manager
8.  รับ Retrieved Data และส่งกลับ Agent ที่ร้องขอ
9.  รับ Result JSON จาก Criterion Agent
10. ส่ง Result เข้า Verification
11. Retry Agent เดิมเมื่อ Verification FAIL
12. ทำ Reference Mapping เมื่อ Verification PASS
13. Inject ข้อมูลลง Template DOCX
14. สร้าง Generated DOCX
15. แสดง HTML Web Preview
16. รองรับ Edit / Save / Download / Version History ตาม Document
    Lifecycle

Generator Service **ไม่รับผิดชอบการตรวจความครบถ้วนของข้อมูลก่อน Generate**
เพราะเป็นหน้าที่ของ Monitor

------------------------------------------------------------------------

# 2. Scope

## 2.1 In Scope

Generator Service ครอบคลุม:

``` text
Monitor → Greenlight / READY
        ↓
Web UI → Enable Generate Button
        ↓
User → Click Generate
        ↓
Generator
        ↓
Master Agent
        ↓
Template DOCX
        ↓
Template Parser
        ↓
Template Structure JSON
        ↓
Criterion Agents
        ↓
Data Request
        ↓
Retrieval Manager
        ↓
ChromaDB / MongoDB / Document-OCR
        ↓
Retrieved Data
        ↓
Criterion Agent
        ↓
Result JSON
        ↓
Verification
        ↓
Reference Mapping
        ↓
Template Injection
        ↓
Generated DOCX
        ↓
HTML Preview
        ↓
Edit / Save
        ↓
Download
        ↓
Version Snapshot
        ↓
Version History
```

## 2.2 Out of Scope

Generator Service ไม่รับผิดชอบ:

``` text
❌ ตรวจความครบถ้วนของข้อมูลก่อน Generate
❌ ตัดสิน Greenlight
❌ Import Document
❌ Parse Source Document เพื่อสร้าง Source Data
❌ สร้างหรือแก้ไข Source Data ใน MongoDB
❌ เขียน User Edit กลับเป็น Source Data
❌ สร้างข้อมูลที่ไม่มี Evidence
❌ ทำหน้าที่เป็น Monitor
```

------------------------------------------------------------------------

# 3. System Boundary

## 3.1 Input

Generator รับ:

``` text
User Generate Request จาก Web UI
Greenlight / READY จาก Monitor
Template DOCX
Source Data / Evidence ผ่าน Retrieval Manager
```

หมายเหตุ:

``` text
Greenlight / READY
        ≠
Automatic Generate
```

Greenlight มีหน้าที่ทำให้ Web UI สามารถเปิดปุ่ม Generate ได้เท่านั้น การ Generate
จะเริ่มเมื่อ User กดปุ่ม Generate

## 3.2 Output

Generator ส่งออก:

``` text
Generated DOCX
HTML Web Preview
Current Draft
Version Snapshot
Version History
Traceability / Reference Mapping
```

------------------------------------------------------------------------

# 4. High-Level Architecture

``` text
GENERATOR SERVICE
│
├── 1. ORCHESTRATION LAYER
│      └── MASTER AGENT
│            ├── Prompt
│            ├── Logic
│            └── Schema
│
├── 2. TEMPLATE LAYER
│      ├── Template DOCX
│      ├── Template Parser
│      └── Template Structure JSON
│
├── 3. CRITERION AGENT LAYER
│      ├── PS Agent
│      ├── P1 Agent
│      ├── P2 Agent
│      ├── P3 Agent
│      ├── P4 Agent
│      └── P8 Agent
│
├── 4. RETRIEVAL LAYER
│      ├── Retrieval Manager
│      ├── MCP
│      ├── ChromaDB
│      ├── MongoDB
│      └── Document/OCR
│
├── 5. GENERATION PROCESSING LAYER
│      ├── Verification
│      ├── Reference Mapping
│      └── Template Injection
│
└── 6. DOCUMENT & PRESENTATION LAYER
       ├── Generated DOCX
       ├── HTML Preview
       ├── Current Draft
       ├── Edit
       ├── Save
       ├── Download
       └── Version History
```

------------------------------------------------------------------------

# 5. Main Flow

``` text
MONITOR
   │
   │ 🟢 READY / Greenlight
   ▼
WEB UI
   │
   │ Enable Generate Button
   ▼
USER
   │
   │ Click Generate
   ▼
GENERATOR
   │
   ▼
MASTER AGENT
   │
   ├── Master Prompt
   ├── Master Logic
   └── Master Schema
   │
   ├── Fetch Template DOCX
   ▼
TEMPLATE PARSER
   ▼
TEMPLATE STRUCTURE JSON
   ▼
MASTER
   │
   ├────────────┬────────────┬────────────┬────────────┐
   ▼            ▼            ▼            ▼            ▼
 PS Agent     P1 Agent     P2 Agent     P3 Agent     P4 Agent ... P8 Agent
   │            │            │            │            │
   └────────────┴────────────┴────────────┴────────────┘
                         │
                         ▼
                    DATA REQUEST
                         │
                         ▼
                 RETRIEVAL MANAGER
                         │
              ┌──────────┼──────────┐
              ▼          ▼          ▼
           ChromaDB    MongoDB    Document/OCR
              └──────────┼──────────┘
                         ▼
                   RETRIEVED DATA
                         ▼
                       MASTER
                         ▼
                  REQUESTING AGENT
                         ▼
                    RESULT JSON
                         ▼
                       MASTER
                         ▼
                    VERIFICATION
                     │           │
                    PASS        FAIL
                     │           │
                     │           └──→ SAME AGENT RETRY
                     ▼
                REFERENCE MAPPING
                     ▼
               TEMPLATE INJECTION
                     ▼
                GENERATED DOCX
                     ▼
                HTML WEB PREVIEW
                     │
                ┌────┴────┐
                ▼         ▼
               EDIT      SAVE
                │         │
                └────┬────┘
                     ▼
                CURRENT DRAFT
                     ▼
                  DOWNLOAD
                     ▼
               VERSION SNAPSHOT
                     ▼
             generated_documents
                     ▼
                VERSION HISTORY
```

------------------------------------------------------------------------

# 6. Monitor → Greenlight

## FR-001 Curriculum Scope

ระบบใช้ **หลักสูตรเดียว** ตาม Data Schema

Generator และ Monitor ไม่ต้องรองรับการเลือกหรือสลับหลายหลักสูตร

``` text
Database
└── Curriculum
      └── Single Curriculum
```

Monitor ต้องประเมิน Readiness ของหลักสูตรเดียวนี้เท่านั้น

## FR-002 Greenlight / Readiness

Monitor เป็นผู้:

``` text
ตรวจความพร้อมของข้อมูล
ตัดสิน Readiness
ส่ง READY / NOT_READY
```

เมื่อ Monitor ส่ง:

``` text
READY / 🟢 Greenlight
```

หมายความว่า:

``` text
หลักสูตรพร้อมสำหรับการ Generate
และ Web UI สามารถเปิดปุ่ม Generate ให้ User
```

**READY / Greenlight ไม่ใช่คำสั่งให้ Generator Generate อัตโนมัติ**

## FR-003 User Generation Trigger

Flow ที่ถูกต้อง:

``` text
Monitor
   ↓
READY / Greenlight
   ↓
Web UI เปิดปุ่ม Generate
   ↓
User กด Generate
   ↓
Generator เริ่ม Generate
```

Generator จะเริ่มกระบวนการ Generate เมื่อได้รับ **User Generate Request** จาก
Web UI หลังจากสถานะ Readiness ผ่านแล้ว

Generator ห้ามเริ่ม Generate อัตโนมัติเพียงเพราะ Monitor ส่ง READY

## FR-004 Responsibility Boundary

Monitor เป็นผู้:

``` text
ตรวจความพร้อมของข้อมูล
ตัดสิน Readiness
ตรวจหลักสูตรเดียวของระบบ
ส่ง READY / NOT_READY
```

Web UI เป็นผู้:

``` text
แสดงสถานะ Readiness
เปิด/ปิดปุ่ม Generate ตามสถานะ
รับการกด Generate จาก User
ส่ง Generate Request ไปยัง Generator
```

Generator เป็นผู้:

``` text
รับ User Generate Request
ตรวจสอบ Greenlight / Readiness ตาม Contract
เริ่ม Generate
```

Generator ห้ามใช้ Config / Guideline / PS Requirement เพื่อสร้างการตัดสิน
Greenlight เอง

------------------------------------------------------------------------

## FR-005 Curriculum Identifier

Generator ต้องสามารถระบุ Curriculum เดียวของระบบให้สอดคล้องกับ Monitor
Readiness Check ได้

`curriculum_id` เป็นตัวระบุของหลักสูตรเดียวในระบบ ไม่ใช่กลไกสำหรับให้ User
เลือกหลายหลักสูตร

หากระบบมี `curriculum_id` อยู่แล้วจาก Application Context / Database
ให้ใช้ค่าดังกล่าว ไม่ต้องเพิ่ม UI สำหรับเลือก Curriculum

------------------------------------------------------------------------

# 7. Master Agent

Master Agent เป็น **Orchestrator** ของ Generator Service

## FR-003 Master Responsibilities

Master ต้อง:

1.  ควบคุม Generate Flow
2.  รับ Template DOCX
3.  เรียก Template Parser
4.  เก็บ Template Structure JSON
5.  แจกจ่าย Template Structure ที่เกี่ยวข้องให้ Criterion Agent
6.  รับ Data Request
7.  ส่ง Data Request ไป Retrieval Manager
8.  รับ Retrieved Data
9.  ส่ง Retrieved Data กลับ Agent ที่ร้องขอ
10. รับ Result JSON
11. ส่ง Result เข้า Verification
12. จัดการ Retry
13. จัดการ Reference Mapping
14. เรียก Template Injection
15. ส่งผลลัพธ์ไป Document Layer

## FR-004 Master Restrictions

Master ห้าม:

``` text
❌ สร้าง Evidence เอง
❌ แก้ Source Data
❌ เปลี่ยน User Edit เป็น Source Data
❌ bypass Verification
❌ ให้ Agent หนึ่งเรียก Agent อื่นโดยตรง
```

------------------------------------------------------------------------

# 8. Template Layer

## FR-005 Template DOCX

Generator ต้องรับ Template DOCX เป็น Input

Template ต้องถูกใช้เป็นโครงสร้างหลักของ Generated Document

## FR-006 Template Parser

Template Parser ต้องวิเคราะห์:

``` text
Document Structure
Section
Heading
Table
Row
Cell
Slot
Header
Field
Type
```

และสร้าง:

``` text
Template Structure JSON
```

## FR-007 Template Structure

Template Structure JSON ต้องเป็นข้อมูลโครงสร้าง ไม่ใช่ Prompt

ตัวอย่าง:

``` json
{
  "criterion": "PS",
  "slots": [
    {
      "slot_id": "ps_1_1",
      "type": "table",
      "headers": [
        "Name",
        "Education",
        "Role"
      ]
    }
  ]
}
```

Criterion Agent ห้ามสร้าง Slot ใหม่เอง

------------------------------------------------------------------------

# 9. Criterion Agent Layer

Generator ต้องมี Criterion Agent แยกตาม Criterion:

``` text
PS Agent
P1 Agent
P2 Agent
P3 Agent
P4 Agent
P8 Agent
```

แต่ละ Agent ต้องมี:

``` text
agent.py
prompt/system_prompt.txt
schema/output_schema.json
```

## FR-008 Agent Responsibility

แต่ละ Agent รับผิดชอบเฉพาะ Criterion ของตัวเอง

ตัวอย่าง:

``` text
PS Agent → PS
P1 Agent → P1
P2 Agent → P2
P3 Agent → P3
P4 Agent → P4
P8 Agent → P8
```

## FR-009 Agent Restrictions

Agent:

``` text
❌ ห้ามสร้างข้อมูลเอง
❌ ห้ามสร้าง Slot ใหม่
❌ ห้ามแก้ slot_id
❌ ห้ามแก้ type
❌ ห้ามแก้ header
❌ ห้ามแก้ DOCX โดยตรง
❌ ห้ามสร้างข้อมูล Criterion อื่น
❌ ห้ามเรียก Agent อื่นโดยตรง
```

Agent ต้องใช้เฉพาะ:

``` text
Template Structure
+
Retrieved Data
+
Source Metadata
+
Output Contract
```

------------------------------------------------------------------------

# 10. Data Request

## FR-010 Agent Data Requirement

Criterion Agent ต้องวิเคราะห์ว่า Field ของตัวเองต้องใช้ข้อมูลอะไร

จากนั้นสร้าง:

``` text
Data Request
```

## FR-011 Data Request Routing

``` text
Criterion Agent
      ↓
Master
      ↓
Retrieval Manager
```

Agent ห้ามเรียก ChromaDB / MongoDB / OCR โดยตรง

------------------------------------------------------------------------

# 11. Retrieval Manager

Retrieval Manager เป็น Component แยก ไม่ใช่ Agent

## FR-012 Retrieval Order

ต้องใช้ลำดับ:

``` text
1. ChromaDB
2. MongoDB
3. Document/OCR
```

## FR-013 Fallback

Fallback ต้องเกิดตามข้อมูลที่ร้องขอ

``` text
Data Request
      ↓
ChromaDB
      │
      ├── Found → Return
      │
      └── Miss / Unavailable
              ↓
          MongoDB
              │
              ├── Found → Return
              │
              └── Miss / Unavailable
                      ↓
                  Document/OCR
```

ChromaDB Vector ต้องไม่ถูกส่งไปให้ MongoDB

MongoDB ใช้ Structured Query

## FR-014 Retrieved Data

Retrieval Manager ต้องส่งข้อมูลกลับเป็นข้อมูลที่ Agent ใช้งานได้ พร้อม Source
Metadata เช่น:

``` text
source_type
source_filename
document_id
page
chunk_index
record_id
collection
```

------------------------------------------------------------------------

# 12. ChromaDB

## FR-015 Semantic Search

ChromaDB ใช้ Semantic Search

Flow:

``` text
Data Request
      ↓
Embedding
      ↓
Query Vector
      ↓
ChromaDB
      ↓
Similarity Search
      ↓
Relevant Evidence
```

## FR-016 Embedding Compatibility

Generator ต้องใช้ Embedding Model เดียวกับ Import Service

มาตรฐานปัจจุบัน:

``` text
Model:
BAAI/bge-m3

Dimension:
1024
```

Import และ Generator ต้องอยู่ใน Embedding Space เดียวกัน

หากเปลี่ยน Embedding Model ต้อง Re-index Vector ที่เกี่ยวข้อง

## FR-017 Chroma Data

Retrieved Chroma Data ต้องประกอบด้วย:

``` text
Text
Metadata
Source Reference
```

Generator ห้ามพยายามแปลง Vector กลับเป็น Text

------------------------------------------------------------------------

# 13. MongoDB

Generator ใช้ MongoDB เป็น Structured Retrieval Source

Final Schema มี 9 Collections:

``` text
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

Final Schema เป็น Source of Truth สำหรับ MongoDB fileciteturn16file0

## FR-018 Structured Query

MongoDB Retrieval ต้องเลือก Collection ตาม `data_type` และใช้ Structured
Query

ตัวอย่าง:

``` text
appointments
  ↓
curriculumId / personId / role

persons
  ↓
personId

educations
  ↓
personId

academic_works
  ↓
personId
```

## FR-019 Source Data Immutability

Generator ห้ามแก้:

``` text
persons
educations
appointments
academic_works
curricula
documents
```

จากการ Generate

------------------------------------------------------------------------

# 14. Document / OCR

Document/OCR เป็น Retrieval Fallback

ใช้เมื่อ:

``` text
ChromaDB → ไม่พบ / ใช้งานไม่ได้
MongoDB → ไม่พบ / ใช้งานไม่ได้
```

ระบบต้องสามารถคืน:

``` text
Extracted Text
Source File
Page
Metadata
```

เพื่อให้ Agent ใช้เป็น Evidence

------------------------------------------------------------------------

# 15. Result JSON

Criterion Agent ต้องส่งผลลัพธ์กลับ Master เป็น:

``` text
Result JSON
```

Result JSON ต้อง:

``` text
ตรงกับ Output Schema
ตรงกับ Template Structure
มีข้อมูลเฉพาะ Criterion
มี Source Reference
ระบุ missing / partial เมื่อข้อมูลไม่ครบ
```

Agent ห้ามเติมข้อมูลที่ไม่มีหลักฐาน

------------------------------------------------------------------------

# 16. Verification

Verification เป็น Component แยกจาก Criterion Agent

## FR-020 Verification Gate

ทุก Result JSON ต้องผ่าน Verification ก่อน Injection

``` text
Result JSON
    ↓
Verification
    │
    ├── PASS
    │
    └── FAIL
```

## FR-021 Verification PASS

เมื่อ PASS:

``` text
PASS
 ↓
Reference Mapping
 ↓
Template Injection
```

## FR-022 Verification FAIL

เมื่อ FAIL:

``` text
FAIL
 ↓
Master
 ↓
SAME Agent
 ↓
Retry
```

ห้ามเปลี่ยนไปใช้ Agent อื่นเพื่อหลบ Verification

## FR-023 Verification Bypass

ห้าม bypass Verification ไม่ว่ากรณีใด

------------------------------------------------------------------------

# 17. Retry

เมื่อ Verification FAIL:

``` text
Master
   ↓
Requesting Agent เดิม
   ↓
Data Request / Result ใหม่
   ↓
Verification
```

Retry ต้องจำกัดจำนวนครั้งตาม Configuration

เมื่อ Retry ครบและยัง FAIL:

``` text
Generation Result = Failed / Incomplete
```

และห้าม Injection ข้อมูลที่ไม่ผ่าน Verification

------------------------------------------------------------------------

# 18. Reference Mapping

Reference Mapping เป็น Component แยก

## FR-024 Source Reference

ทุก Generated Field ที่อ้างอิงข้อมูล Source ต้องสามารถ Mapping กลับไปยัง Source ได้

ตัวอย่าง:

``` text
Generated Field
      ↓
Source Reference
      ↓
MongoDB Record / Chroma Chunk / Document
```

## FR-025 User Edit Reference

ต้องแยก:

``` text
Source Data
User Edit
```

User Edit ไม่ถือเป็น Source Evidence

------------------------------------------------------------------------

# 19. Template Injection

Template Injection เป็น Component แยก

## FR-026 DOCX Injection

ต้องนำข้อมูลที่ผ่าน:

``` text
Verification
+
Reference Mapping
```

เข้า Template DOCX

## FR-027 Template Preservation

ต้องรักษาโครงสร้าง Template ที่มีอยู่ เช่น:

``` text
Section
Heading
Table
Header
Formatting
```

ห้ามสร้าง DOCX ใหม่โดยไม่จำเป็นจนทำให้ Template Structure หาย

## FR-028 Agent Restriction

Criterion Agent ห้ามแก้ DOCX โดยตรง

เฉพาะ Template Injection เท่านั้นที่แก้ DOCX

------------------------------------------------------------------------

# 20. Generated DOCX

Output หลัก:

``` text
Generated DOCX
```

ต้องมี:

``` text
Template Structure
+
Verified Content
+
Reference Mapping
```

และต้องสามารถเปิดใช้งานเป็น DOCX ที่ valid ได้

------------------------------------------------------------------------

# 21. HTML Web Preview

หลัง Generated DOCX ต้องสามารถสร้าง:

``` text
HTML Web Preview
```

เพื่อให้ผู้ใช้ตรวจสอบเอกสารก่อนการ Save / Download

Flow:

``` text
Generated DOCX
      ↓
HTML Preview
```

------------------------------------------------------------------------

# 22. Document Lifecycle

Document Lifecycle เป็นส่วนของ Generator Service

``` text
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

------------------------------------------------------------------------

# 23. Edit

ผู้ใช้สามารถแก้ไข Generated Document ผ่าน Web Preview / Editor

User Edit ต้องถูกเก็บเป็น:

``` text
Current Draft
```

ไม่ใช่ Source Data

------------------------------------------------------------------------

# 24. Save

## FR-029 Save

Save ต้อง:

``` text
Current Document
      ↓
Current Draft
```

Save ยังไม่สร้าง Version ใหม่

------------------------------------------------------------------------

# 25. Download

## FR-030 Download

เมื่อผู้ใช้ Download:

``` text
Current Draft
      ↓
Version Snapshot
      ↓
Generated File
```

Download ต้องสร้าง Version ตาม Lifecycle ที่กำหนด

------------------------------------------------------------------------

# 26. Version History

## FR-031 Version Persistence

Version เก่าห้ามถูกเขียนทับ

ตัวอย่าง:

``` text
generated/
├── PS-2569-v1.docx
├── PS-2569-v2.docx
└── PS-2569-v3.docx
```

MongoDB ใช้:

``` text
generated_documents
```

สำหรับเก็บข้อมูล Generated Document และ Version ตาม Final Data Schema
fileciteturn16file0

## FR-032 Version Snapshot

แต่ละ Version ต้องมี:

``` text
path
timestamp
```

ตาม Data Schema

------------------------------------------------------------------------

# 27. Generate New

เมื่อ Generate ใหม่:

``` text
Generate New
      ↓
Source Data จาก Database / Retrieval ใหม่
```

ห้าม:

``` text
Current Draft
      ↓
Generate New
```

User Edit จาก Document เดิมไม่ถือเป็น Source Data สำหรับ Generate รอบใหม่

------------------------------------------------------------------------

# 28. Source Data Immutability

หลักการสำคัญ:

``` text
SOURCE DATA
     │
     ├── MongoDB
     ├── ChromaDB
     └── Document/OCR
```

Generator สามารถ:

``` text
READ
```

แต่ไม่สามารถแก้ Source Data จากกระบวนการ Generate

ยกเว้นข้อมูลที่เป็น Generated Document / Version ตาม Lifecycle

------------------------------------------------------------------------

# 29. User Edit Boundary

``` text
SOURCE DATA
     │
     ▼
GENERATOR
     │
     ▼
GENERATED DOCUMENT
     │
     ▼
USER EDIT
     │
     ▼
CURRENT DRAFT
```

User Edit ห้ามย้อนกลับ:

``` text
User Edit
   ✕
   ↓
persons
educations
appointments
academic_works
```

------------------------------------------------------------------------

# 30. Traceability

ระบบต้องสามารถติดตาม:

``` text
Generated Content
      ↓
Result JSON
      ↓
Reference Mapping
      ↓
Source Evidence
      ↓
Source Document / Mongo Record
```

สำหรับ Chroma:

``` text
Generated Content
      ↓
Chunk
      ↓
document_id
      ↓
filename
      ↓
page
```

สำหรับ MongoDB:

``` text
Generated Content
      ↓
Record
      ↓
collection
      ↓
record_id
```

------------------------------------------------------------------------

# 31. Table 1.2

Table 1.2 ยังเป็น Requirement ที่ต้องตรวจสอบกับ Template จริง

ระบบห้ามสร้าง Logic เฉพาะสำหรับ Table 1.2 จากการคาดเดา

เมื่อ Template จริงพร้อม:

``` text
Template
   ↓
Inspect Table 1.2
   ↓
Determine Required Support
   ↓
Implement only if required
```

------------------------------------------------------------------------

# 32. P2 / P3 / P4 / P8

Agent Structure ต้องมี แต่ Content / Logic / Data จริงอาจยังอยู่ในสถานะ Wait
จนกว่าจะได้รับ Specification และ Source Data ที่พร้อม

``` text
P2 Agent → Wait for final content/data
P3 Agent → Wait for final content/data
P4 Agent → Wait for final content/data
P8 Agent → Wait for final content/data
```

ไม่อนุญาตให้สร้าง Content จากการคาดเดา

------------------------------------------------------------------------

# 33. MongoDB Compatibility

MongoDB Retrieval Implementation ต้องรองรับ Final MongoDB Schema

เมื่อ MongoDB จริงพร้อม ต้องทดสอบ:

``` text
Connection
 ↓
Database
 ↓
9 Collections
 ↓
Schema
 ↓
Relationships
 ↓
Query
 ↓
Retrieved Data
 ↓
Agent Input
 ↓
Verification
 ↓
Real E2E
```

หากพบ Defect:

``` text
Real MongoDB
 ↓
Observed Defect
 ↓
Root Cause
 ↓
Fix
 ↓
Regression Test
```

ห้ามแก้ Schema หรือ Architecture เพียงเพื่อให้เข้ากับข้อมูลทดสอบที่ไม่ใช่ Final Schema

------------------------------------------------------------------------

# 34. Legacy Generic Agent

Generic Criteria Agent แบบเก่าเป็น Legacy / Inactive

Active Flow ใช้:

``` text
PS Agent
P1 Agent
P2 Agent
P3 Agent
P4 Agent
P8 Agent
```

Legacy Code ไม่ควรถูกนำกลับมาเป็น Active Path โดยไม่มีการเปลี่ยน SRS

------------------------------------------------------------------------

# 35. Non-Functional Requirements

## NFR-001 Reliability

Verification ต้องเป็น Gate จริง

ห้ามส่งผลลัพธ์ที่ไม่ผ่าน Verification ไป Injection

## NFR-002 Traceability

Generated Content ต้องสามารถย้อนกลับไปยัง Source ได้

## NFR-003 Data Integrity

Source Data ต้องไม่ถูกแก้จาก User Edit หรือ Generation

## NFR-004 Maintainability

Configuration สำคัญควรแยกจาก Business Logic เช่น:

``` text
EMBEDDING_MODEL
EMBEDDING_DIMENSION
RETRY_LIMIT
CHROMA_HOST
CHROMA_PORT
MONGODB_URI
MONGODB_DB_NAME
```

## NFR-005 Logging

ต้อง Log อย่างน้อย:

``` text
Greenlight Received
Template Fetch
Template Parse
Agent Request
Data Request
Retrieval
Verification
Retry
Reference Mapping
Injection
Preview
Save
Download
Version
Error
```

------------------------------------------------------------------------

# 36. Technology / Component Requirements

``` text
Orchestration
└── Master Agent

Agent Runtime
├── PS Agent
├── P1 Agent
├── P2 Agent
├── P3 Agent
├── P4 Agent
└── P8 Agent

Template
├── DOCX
├── Template Parser
└── Template Structure JSON

Retrieval
├── Retrieval Manager
├── MCP
├── ChromaDB
├── MongoDB
└── Document/OCR

Generation
├── Verification
├── Reference Mapping
└── Template Injection

Presentation
├── DOCX
├── HTML Preview
├── Editor
└── Version History
```

------------------------------------------------------------------------

# 37. Forbidden Changes

AI / Developer ห้ามเปลี่ยนเอง:

``` text
❌ ให้ Generator ตรวจ Greenlight เอง
❌ ให้ Generator ตรวจ Data Completeness เอง
❌ เพิ่ม Guideline เป็น Completeness Gate
❌ ให้ Agent เรียก Agent อื่นโดยตรง
❌ ให้ Agent เรียก Database โดยตรง
❌ ให้ Agent แก้ DOCX โดยตรง
❌ ให้ Agent สร้าง Slot ใหม่
❌ ให้ Agent สร้างข้อมูลที่ไม่มี Evidence
❌ Bypass Verification
❌ เปลี่ยน FAIL เป็น PASS โดยไม่แก้สาเหตุ
❌ Retry ด้วย Agent อื่นแทน SAME Agent
❌ เขียน User Edit กลับ Source Data
❌ ใช้ User Edit เป็น Source Data ใน Generate รอบใหม่
❌ ใช้ Chroma Vector ไป Query MongoDB
❌ ใช้ Embedding Model คนละตัวกับ Import Service
❌ เปลี่ยน Final MongoDB Schema โดยพลการ
❌ ใช้ evidence_chunks / evidence_documents เป็น Final Schema
❌ เขียน generated_documents เป็น Source Evidence
❌ Overwrite Version เก่า
```

------------------------------------------------------------------------

# 38. Acceptance Criteria

Generator Service ถือว่าสำเร็จเมื่อ:

``` text
AC-001
รับ READY / Greenlight จาก Monitor สำหรับหลักสูตรเดียวได้

AC-002
เมื่อ Monitor ส่ง READY แล้ว Web UI สามารถเปิดปุ่ม Generate ให้ User ได้ และ Master Agent จะเริ่ม Generate เฉพาะหลัง User กด Generate

AC-003
Fetch Template DOCX ได้

AC-004
Template Parser สร้าง Template Structure JSON ได้

AC-005
Criterion Agent แต่ละตัวได้รับเฉพาะ Slot ที่เกี่ยวข้อง

AC-006
Agent สร้าง Data Request ได้

AC-007
Data Request ผ่าน Master ไป Retrieval Manager ได้

AC-008
Retrieval Manager เรียก ChromaDB ก่อน MongoDB

AC-009
MongoDB เป็น Structured Retrieval

AC-010
Document/OCR เป็น Fallback

AC-011
Retrieved Data กลับถึง Requesting Agent ได้

AC-012
Agent สร้าง Result JSON ตาม Schema ได้

AC-013
Result JSON ผ่าน Verification ได้

AC-014
Verification FAIL ทำให้ SAME Agent Retry

AC-015
Verification Bypass ไม่เกิดขึ้น

AC-016
Verification PASS ส่งต่อ Reference Mapping ได้

AC-017
Reference Mapping ระบุ Source ได้

AC-018
Template Injection สร้าง DOCX ได้

AC-019
Template Structure ไม่เสียหาย

AC-020
HTML Preview แสดง Generated Document ได้

AC-021
User Edit ถูกเก็บเป็น Current Draft

AC-022
Save ไม่สร้าง Version ใหม่

AC-023
Download สร้าง Version Snapshot

AC-024
Version เก่าไม่ถูก Overwrite

AC-025
generated_documents เก็บ Version ได้

AC-026
User Edit ไม่เขียนกลับ Source Data

AC-027
Generate New ดึง Source Data ใหม่

AC-028
Traceability สามารถย้อนกลับ Source ได้

AC-029
Generator ไม่ทำหน้าที่ตัดสิน Greenlight และ READY จาก Monitor ไม่ทำให้ Generate อัตโนมัติ

AC-030
Real E2E สามารถพิสูจน์ Generate → Verification → DOCX ได้
```

------------------------------------------------------------------------

# 39. Definition of Done

Generator Service ถือว่าเสร็จเมื่อสามารถทำ Flow นี้ได้ครบ:

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
Template Parser
   ↓
Template Structure
   ↓
Criterion Agent
   ↓
Data Request
   ↓
Retrieval Manager
   ↓
ChromaDB / MongoDB / Document-OCR
   ↓
Retrieved Data
   ↓
Requesting Agent
   ↓
Result JSON
   ↓
Verification
   │
   ├── FAIL → SAME Agent Retry
   │
   └── PASS
          ↓
    Reference Mapping
          ↓
    Template Injection
          ↓
    Generated DOCX
          ↓
    HTML Preview
          ↓
    Edit / Save
          ↓
    Current Draft
          ↓
    Download
          ↓
    Version Snapshot
          ↓
    Version History
```

------------------------------------------------------------------------

# 40. Current Implementation / Plug / Wait Status

## DONE

``` text
Master Agent
Template Parser
Template Structure
PS Agent Structure
P1 Agent Structure
P2 Agent Structure
P3 Agent Structure
P4 Agent Structure
P8 Agent Structure
Data Request
Retrieval Manager
Verification
Retry SAME Agent
Reference Mapping
Template Injection
Generated DOCX
HTML Preview
```

## PLUG / WAIT

``` text
MongoDB Real
ChromaDB Real
Document/OCR Real
Monitor → Greenlight
P2 Content/Data
P3 Content/Data
P4 Content/Data
P8 Content/Data
Table 1.2
Real E2E PASS
```

## NOT YET IMPLEMENTED

``` text
Document Lifecycle
├── Edit
├── Save / Current Draft
├── Download
└── Version History
```

------------------------------------------------------------------------

# 41. Final Responsibility Boundary

``` text
IMPORT SERVICE
    │
    ├── Source Documents
    ├── Structured Data
    └── ChromaDB Evidence
             │
             ▼
        MONITOR
             │
             └── 🟢 Greenlight
                       │
                       ▼
                GENERATOR SERVICE
                       │
                       ├── Generate
                       ├── Verify
                       ├── Reference
                       ├── Inject
                       └── Document Lifecycle
```

Generator Service พร้อมให้ Generate เมื่อได้รับ Greenlight จาก Monitor แต่จะเริ่ม
Generate จริงเมื่อ User กดปุ่ม Generate ผ่าน Web UI

Generator Service จบที่ Generated Document / Version History

------------------------------------------------------------------------

# 41.1 Production Generation Entry Point

Production Generation ต้องเริ่มจาก Web UI หลังจาก Monitor ส่ง READY /
Greenlight และ User กดปุ่ม Generate

ตัวอย่าง CLI:

``` bash
python -m master_agent.master
```

ให้ถือเป็น **Development / Test entrypoint เท่านั้น** และไม่ใช่ Production
Generation Entry Point

Production User ต้องไม่สามารถใช้ CLI เพื่อข้าม Web UI และ Readiness Flow ได้

------------------------------------------------------------------------

# 42. SRS Change Control

Version ปัจจุบัน:

``` text
SRS v1.0
```

หากต้องเปลี่ยน:

``` text
Flow
Agent Responsibility
MongoDB Responsibility
Retrieval Order
Embedding Model
Template Contract
Verification Gate
Document Lifecycle
Versioning
```

ต้องสร้าง Version ใหม่ เช่น:

``` text
SRS v1.1
SRS v2.0
```

ห้ามเปลี่ยน Implementation ให้ขัดกับ SRS v1.0 โดยไม่ปรับ Version ของ SRS
