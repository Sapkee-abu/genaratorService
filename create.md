คุณคือ Senior Frontend Engineer

ให้สร้าง Frontend สำหรับ Generator Service ของระบบ AUN-QA SAR Generator

Technology:
- React
- TypeScript
- Vite
- React Router
- CSS architecture ที่แยกเป็นระบบ
- ใช้ component-based architecture
- Frontend ต้องแยกจาก Backend อย่างชัดเจน
- ห้ามนำ business logic ของ Generator Agent / Retrieval / MongoDB / ChromaDB มาไว้ใน Frontend

เป้าหมาย:
สร้าง Web UI สำหรับ Generator Service แบบ Standalone ก่อน
ยังไม่ต้องเชื่อม Monitor Service

==================================================
1. CURRENT DEVELOPMENT MODE
==================================================

ตอนนี้ Generator Service ยังไม่ได้รวมกับ Service อื่นใน Project เดียว

ดังนั้น Frontend รอบนี้:

DO:
- Generate
- แสดง Generated Document
- HTML Preview
- Edit
- Save Current Draft
- Download
- History
- Reference / Traceability

DO NOT:
- ไม่ต้องรอ Monitor
- ไม่ต้องเรียก Monitor
- ไม่ต้องมี Readiness page
- ไม่ต้องคำนวณ generatedReady
- ไม่ต้องสร้าง Curriculum selector หลายหลักสูตร
- ไม่ต้องทำ Import
- ไม่ต้องทำ OCR
- ไม่ต้องทำ Source Data management

Generate button สามารถกด Generate ได้โดยตรงใน Development Mode


==================================================
2. IMPORTANT FUTURE COMPATIBILITY
==================================================

แม้ตอนนี้ยังไม่ต่อ Monitor
ต้องออกแบบ Frontend ให้สามารถเพิ่ม Monitor Gate ภายหลังได้โดยไม่ต้องรื้อ UI

Future flow:

Monitor
   ↓
generatedReady
   ↓
Enable Generate Button
   ↓
User clicks Generate

Current flow:

User
   ↓
Generate Button
   ↓
Generator Backend

อย่า hardcode architecture จนไม่สามารถเพิ่ม readiness gate ภายหลัง


==================================================
3. MAIN NAVIGATION
==================================================

Frontend ต้องมี 3 หน้าหลัก:

1. Generate
2. History
3. Reference


Route:

/
  → redirect /generate

/generate
  → Generate Page

/history
  → History Page

/reference
  → Reference Page


ใช้ React Router


==================================================
4. APPLICATION LAYOUT
==================================================

สร้าง Application Layout กลาง:

AppLayout
├── Header
├── Navigation
└── Main Content

โครงสร้าง UI:

┌─────────────────────────────────────────────────────────────┐
│ AUN-QA SAR Generator                                       │
│                                                             │
│ Generate          History          Reference                │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│                    PAGE CONTENT                             │
│                                                             │
└─────────────────────────────────────────────────────────────┘


Header:
- ชื่อระบบ: AUN-QA SAR Generator
- ไม่ต้องมีข้อมูลรก
- Clean / professional
- เหมาะกับระบบมหาวิทยาลัย


Navigation:
- Generate
- History
- Reference

Active navigation ต้องเห็นชัดเจน


==================================================
5. DESIGN PRINCIPLE
==================================================

UI ต้อง:

- Clean
- Professional
- Minimal
- อ่านง่าย
- เหมาะกับระบบเอกสาร
- ไม่ใช้สีเยอะ
- ไม่ใช้ animation มากเกินไป
- ไม่ทำ Dashboard ที่มี card เยอะโดยไม่จำเป็น

เน้น:
- document workspace
- tables
- tree
- reference information
- action buttons

อย่าออกแบบเหมือน AI chat application


==================================================
6. PAGE 1 — GENERATE
==================================================

Route:

/generate


หน้านี้เป็น Main Workspace


สถานะเริ่มต้น:

┌─────────────────────────────────────────────────────────────┐
│ Generate SAR                                                │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ Curriculum                                                  │
│ วิทยาศาสตรบัณฑิต สาขาเทคโนโลยีสารสนเทศอัจฉริยะ            │
│                                                             │
│ Template                                                    │
│ Latest Template                                             │
│                                                             │
│                         [ Generate ]                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘


Curriculum:
- แสดงหลักสูตรปัจจุบัน
- ไม่มี curriculum selector
- ไม่ให้ user เลือกหลายหลักสูตร

ข้อมูล Curriculum จะมาจาก Backend API ในภายหลัง


==================================================
7. GENERATE STATE
==================================================

เมื่อกด Generate:

Button ต้องเปลี่ยนเป็น loading state

ตัวอย่าง:

Generating...

และแสดง progress/status:

✓ Load Template
✓ Parse Template
✓ Build Template Structure
● Generate Criterion
○ Verification
○ Reference Mapping
○ Template Injection
○ Prepare Preview


Frontend ไม่ต้องคำนวณ progress เอง

ถ้า Backend มี generation status API:
    ใช้ข้อมูลจาก Backend

ถ้ายังไม่มี:
    สร้าง UI state สำหรับรองรับในอนาคต


ห้าม fake progress แบบเพิ่ม 10%, 20%, 30%
ถ้า Backend ไม่ได้ส่ง progress จริง


==================================================
8. GENERATE SUCCESS
==================================================

เมื่อ Generate สำเร็จ:

หน้า Generate ต้องเปลี่ยนเป็น Document Workspace

แสดง:

Document name
Version / Draft status
Last saved
Action buttons

ตัวอย่าง:

┌─────────────────────────────────────────────────────────────┐
│ SAR_2569.docx                                               │
│                                                             │
│ Status: Current Draft                                       │
│ Last saved: 27 Sep 2026 22:40                              │
│                                                             │
│ [ Save ]                              [ Download ]          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│                  HTML DOCUMENT                              │
│                                                             │
│                  Document content                           │
│                                                             │
└─────────────────────────────────────────────────────────────┘


==================================================
9. HTML DOCUMENT PREVIEW
==================================================

Generated Document ต้องแสดงเป็น HTML

ไม่ใช่แสดง DOCX binary

Frontend ต้องมี:

<DocumentViewer />

DocumentViewer รองรับ:

- headings
- paragraphs
- tables
- lists
- checkbox
- basic text formatting
- document sections

ต้องพยายามรักษาโครงสร้างของ Generated Document


==================================================
10. DOCUMENT EDITING
==================================================

User สามารถ Edit HTML Document ได้

ต้องแยก:

DocumentViewer
DocumentEditor

Concept:

View Mode:
<DocumentViewer />

Edit Mode:
<DocumentEditor />


UI:

[ Edit ]

เมื่อกด:

[ Save ] [ Cancel ]


User ต้องสามารถแก้ไข document content ได้


==================================================
11. DO NOT USE SAVE AS VERSION
==================================================

สำคัญมาก:

Save ≠ Version

Save หมายถึง:

Current Draft

Flow:

Generate
 ↓
HTML
 ↓
Edit
 ↓
Save
 ↓
Current Draft


User สามารถ Save หลายครั้งได้

Save ห้ามสร้าง History Version


==================================================
12. DOWNLOAD CREATES VERSION
==================================================

Download เป็น Version Snapshot

Flow:

Current Draft
    ↓
Download
    ↓
Version Snapshot
    ↓
History


Frontend ต้องเรียก Backend Download API

Frontend ไม่ควรสร้าง version number เอง


Backend เป็นผู้กำหนด version


==================================================
13. UNSAVED CHANGES
==================================================

ถ้า User แก้ Document แต่ยังไม่ Save:

แสดง:

Unsaved changes


ตัวอย่าง:

● Unsaved changes

ถ้า Save แล้ว:

✓ Saved


ถ้าไม่มีการแก้:

Saved


ถ้า User กำลังจะออกจากหน้าและมี unsaved changes:

แสดง confirmation:

"You have unsaved changes. Leave without saving?"


อย่าทำ confirmation ถ้าไม่มี unsaved changes


==================================================
14. DOWNLOAD BEHAVIOR
==================================================

เมื่อ User กด Download:

Frontend:

1. เรียก Backend Download API
2. Backend สร้าง Version Snapshot
3. Backend ส่ง DOCX
4. Browser download file
5. Refresh current version/history state

Frontend ห้าม:
- สร้าง version เอง
- เพิ่ม history record เอง
- เขียน MongoDB
- แก้ generated_documents โดยตรง


==================================================
15. PAGE 2 — HISTORY
==================================================

Route:

/history


หน้าที่:

แสดง Version ที่ถูกสร้างจาก Download


UI:

┌─────────────────────────────────────────────────────────────┐
│ Generation History                                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ SAR_2569.docx                                               │
│                                                             │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Version 5                                               │ │
│ │ 27 Sep 2026 22:50                                       │ │
│ │                                                         │ │
│ │ [ Preview ] [ Download ] [ Reference ]                  │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                             │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Version 4                                               │ │
│ │ 27 Sep 2026 21:30                                       │ │
│ │                                                         │ │
│ │ [ Preview ] [ Download ] [ Reference ]                  │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                             │
└─────────────────────────────────────────────────────────────┘


==================================================
16. HISTORY RULE
==================================================

History ต้องแสดงเฉพาะ Version Snapshot

ถ้า:

Generate
→ Edit
→ Save

ยังไม่มี Version ใหม่


ถ้า:

Generate
→ Edit
→ Save
→ Download

จึงเกิด:

Version 1


ห้าม Frontend สร้าง Version จาก Save


==================================================
17. HISTORY DATA
==================================================

History data มาจาก Backend

ตัวอย่าง response:

{
  "fileName": "SAR_2569.docx",
  "versions": [
    {
      "version": 5,
      "timestamp": "...",
      "fileType": "docx"
    },
    {
      "version": 4,
      "timestamp": "...",
      "fileType": "docx"
    }
  ]
}


Frontend ห้ามเดา version


==================================================
18. HISTORY ACTIONS
==================================================

แต่ละ Version มี:

[ Preview ]
[ Download ]
[ Reference ]


Preview:
เปิด document preview ของ Version นั้น

Download:
ดาวน์โหลด Version นั้น

Reference:
เปิด Reference ของ Version นั้น


==================================================
19. PAGE 3 — REFERENCE
==================================================

Route:

/reference


หน้าที่:

ตรวจสอบโครงสร้างเอกสารและ Reference Mapping


Reference Page ต้องไม่เป็นแค่ list ของ source

ต้องเป็น Document Structure Explorer


Layout:

┌─────────────────────────────────────────────────────────────┐
│ Reference                                                  │
├───────────────────────┬─────────────────────────────────────┤
│ Document Structure    │ Reference Details                   │
│                       │                                     │
│ ▼ PS                  │ Field                               │
│   ├── Table 1.1       │ ชื่อ-นามสกุล                        │
│   ├── Table 1.2       │                                     │
│   └── Narrative       │ Value                               │
│                       │ ดร.พีรวิชญ์ เควด                    │
│ ▼ P1                  │                                     │
│ ▼ P2                  │ Source                              │
│ ▼ P3                  │ ChromaDB                            │
│ ▼ P4                  │                                     │
│ ▼ P8                  │ Document                            │
│                       │ xxx.pdf                             │
│                       │                                     │
│                       │ Page: 3                             │
│                       │ Chunk: 2                            │
└───────────────────────┴─────────────────────────────────────┘


==================================================
20. REFERENCE TREE
==================================================

Tree ต้องแสดงโครงสร้างประมาณ:

PS
├── Criterion
│   ├── Table 1.1
│   ├── Table 1.2
│   └── Narrative

P1
├── ...

P2
├── ...

P3
├── ...

P4
├── ...

P8
├── ...


Tree ต้อง expandable / collapsible


==================================================
21. REFERENCE DETAIL
==================================================

เมื่อ User คลิก:

Table 1.1
→ แสดง fields


ตัวอย่าง:

Field:
ชื่อ-นามสกุล

Value:
ดร.พีรวิชญ์ เควด

Source:
ChromaDB

Document ID:
...

Page:
3

Chunk:
2


อีก field:

Field:
ผลงานปี 2565

Value:
2

Source:
MongoDB

Collection:
academic_works

Person ID:
...


==================================================
22. SOURCE TYPE
==================================================

Reference UI ต้องรองรับ:

ChromaDB
MongoDB
Document/OCR
User Edit


Source ต้องแสดงชัดเจน


ตัวอย่าง:

Source
● ChromaDB


หรือ:

Source
● MongoDB


อย่าแสดง source เป็นข้อความกำกวม


==================================================
23. USER EDIT REFERENCE
==================================================

ถ้า User แก้ข้อมูล:

Source Value:
ปริญญาโท

User Edit:
ปริญญาเอก


Reference ต้องแสดงแยก:

Original Source
→ ปริญญาโท

User Edit
→ ปริญญาเอก


ห้ามเปลี่ยน source value เป็น user edit


==================================================
24. REFERENCE VERSION
==================================================

Reference ต้องรองรับ Version

ถ้าเข้าจาก:

History
→ Version 4
→ Reference

ต้องแสดง Reference ของ Version 4

ไม่ใช่ Version ล่าสุดเสมอ


ดังนั้น route อาจเป็น:

/reference/:version


หรือ:

/reference?version=4


เลือกแบบที่เหมาะกับ React Router


==================================================
25. COMPONENT ARCHITECTURE
==================================================

ต้องแยก Component อย่างสะอาด

ตัวอย่าง:

src/
│
├── app/
│   ├── App.tsx
│   ├── router.tsx
│   └── layout/
│       └── AppLayout.tsx
│
├── pages/
│   ├── GeneratePage/
│   │   ├── GeneratePage.tsx
│   │   └── GeneratePage.css
│   │
│   ├── HistoryPage/
│   │   ├── HistoryPage.tsx
│   │   └── HistoryPage.css
│   │
│   └── ReferencePage/
│       ├── ReferencePage.tsx
│       └── ReferencePage.css
│
├── components/
│   ├── layout/
│   │   ├── Header.tsx
│   │   └── Navigation.tsx
│   │
│   ├── generate/
│   │   ├── GenerateForm.tsx
│   │   ├── GenerateProgress.tsx
│   │   ├── DocumentWorkspace.tsx
│   │   ├── DocumentViewer.tsx
│   │   ├── DocumentEditor.tsx
│   │   ├── DocumentToolbar.tsx
│   │   └── UnsavedChangesDialog.tsx
│   │
│   ├── history/
│   │   ├── HistoryList.tsx
│   │   ├── HistoryItem.tsx
│   │   └── VersionActions.tsx
│   │
│   └── reference/
│       ├── ReferenceTree.tsx
│       ├── ReferenceTreeNode.tsx
│       ├── ReferenceDetails.tsx
│       ├── SourceBadge.tsx
│       └── ReferencePanel.tsx
│
├── services/
│   ├── generatorApi.ts
│   ├── historyApi.ts
│   └── referenceApi.ts
│
├── types/
│   ├── document.ts
│   ├── history.ts
│   ├── reference.ts
│   └── api.ts
│
├── hooks/
│   ├── useGenerate.ts
│   ├── useDocument.ts
│   ├── useHistory.ts
│   └── useReference.ts
│
├── utils/
│   └── ...
│
└── styles/
    ├── globals.css
    └── variables.css


ห้ามเอาทุกอย่างไว้ใน App.tsx


==================================================
26. API LAYER
==================================================

ห้ามเขียน fetch/axios กระจายอยู่ใน Components


ผิด:

GeneratePage.tsx
→ fetch(...)

HistoryPage.tsx
→ fetch(...)

ReferencePage.tsx
→ fetch(...)


ให้ทำ:

services/
    generatorApi.ts
    historyApi.ts
    referenceApi.ts


ตัวอย่าง:

generatorApi.generate()
generatorApi.getDocument()
generatorApi.saveDraft()
generatorApi.download()


historyApi.getHistory()


referenceApi.getReference()


Components เรียกผ่าน hooks/service layer


==================================================
27. TYPESCRIPT TYPES
==================================================

ต้องสร้าง TypeScript types

ตัวอย่าง:

type GenerationStatus =
  | "idle"
  | "generating"
  | "success"
  | "error";

type DraftStatus =
  | "saved"
  | "unsaved";

interface GeneratedDocument {
  id: string;
  fileName: string;
  html: string;
  status: DraftStatus;
  lastSavedAt?: string;
}

interface DocumentVersion {
  version: number;
  timestamp: string;
  fileName: string;
}

interface ReferenceItem {
  id: string;
  field: string;
  value: string;
  source: "chroma" | "mongodb" | "document_ocr" | "user_edit";
  sourceReference?: SourceReference;
}


อย่าใช้ any ถ้าไม่จำเป็น


==================================================
28. STATE MANAGEMENT
==================================================

สำหรับ MVP ไม่จำเป็นต้องใช้ Redux ถ้าไม่จำเป็น

สามารถใช้:

React useState
React useReducer
Custom Hooks

และ React Query/TanStack Query ถ้า Project ใช้อยู่แล้ว


แยก:

Server State
Document Editing State
UI State


อย่าเอาทุก state ไว้ global


==================================================
29. DOCUMENT EDITOR
==================================================

Editor ต้องออกแบบให้รองรับ:

- text editing
- table editing
- paragraph editing
- basic formatting

แต่ต้องไม่พยายามสร้าง Word processor เต็มรูปแบบใน MVP


ถ้า Backend ส่ง HTML ที่แก้ไขได้:
    ใช้ HTML document model ที่เหมาะสม

อย่าใช้:

contentEditable
แบบกระจายหลาย component
โดยไม่มี document state กลาง


ต้องมี single source of truth:

documentDraft


==================================================
30. SAVE FLOW
==================================================

เมื่อ User แก้:

documentDraft เปลี่ยน

status:

unsaved


กด Save:

POST/PUT draft

เมื่อสำเร็จ:

status = saved


แสดง:

✓ Saved


==================================================
31. DOWNLOAD FLOW
==================================================

เมื่อกด Download:

Frontend:

await generatorApi.download(documentId)

Backend เป็นผู้สร้าง Version Snapshot


หลัง download สำเร็จ:

refresh history


ห้าม:

history.push(newVersion)


เพราะ version ต้องมาจาก Backend


==================================================
32. ERROR HANDLING
==================================================

ทุก API ต้องมี:

loading
success
error


ตัวอย่าง Generate Error:

┌─────────────────────────────────────────┐
│ Generation Failed                       │
│                                         │
│ ไม่สามารถสร้างเอกสารได้                 │
│ กรุณาลองใหม่อีกครั้ง                    │
│                                         │
│ [ Retry ]                               │
└─────────────────────────────────────────┘


Reference Error:

ไม่สามารถโหลด Reference ได้


History Error:

ไม่สามารถโหลดประวัติเอกสารได้


ห้ามแสดง raw stack trace ให้ User


==================================================
33. EMPTY STATES
==================================================

History ไม่มีข้อมูล:

ยังไม่มีเอกสารที่ Download

Reference ไม่มีข้อมูล:

ยังไม่มี Reference สำหรับเอกสารนี้

Generate ยังไม่มี Document:

แสดง Generate form


==================================================
34. RESPONSIVE
==================================================

ต้องรองรับ:

Desktop
Tablet


Desktop เป็น priority เพราะเป็นระบบสร้างเอกสาร


Reference Page:

Desktop:
Tree 30%
Details 70%

Tablet:
Tree ด้านบน
Details ด้านล่าง


==================================================
35. ACCESSIBILITY
==================================================

ต้องมี:

- semantic HTML
- button ที่ใช้ keyboard ได้
- focus state
- aria-label เมื่อจำเป็น
- contrast ที่อ่านง่าย


Tree Reference ต้องรองรับ keyboard navigation ในระดับพื้นฐาน


==================================================
36. NO BUSINESS LOGIC IN FRONTEND
==================================================

Frontend ห้ามทำ:

- calculate PS readiness
- calculate academic work count
- merge appointments
- merge person roles
- calculate education level
- retrieve Chroma
- retrieve MongoDB
- run verification
- run AI Agent
- modify source data


สิ่งเหล่านี้เป็น Backend responsibility


Frontend มีหน้าที่:

Display
Edit Draft
Call API
Manage UI State


==================================================
37. CURRENT BACKEND API ASSUMPTION
==================================================

ถ้า Backend API ยังไม่ครบ:

สร้าง API service interface ตาม contract

อย่า hardcode fake document data ใน Component


สามารถใช้ temporary mock adapter ได้เฉพาะใน development

แต่ต้องแยก:

services/mock/
services/api/


เพื่อให้เปลี่ยนจาก Mock → Real API ได้ง่าย


==================================================
38. IMPORTANT — REAL DATA
==================================================

Backend ปัจจุบันเชื่อม Real MongoDB และ Real ChromaDB แล้ว

Frontend ไม่ต้องรู้ connection:

MongoDB
ChromaDB
MCP

Frontend รู้เพียง Generator API


Architecture:

React
  ↓
Generator API
  ↓
Generator Service
  ↓
Master
  ↓
Agents
  ↓
Retrieval
  ↓
MCP
  ↓
Mongo / Chroma


ห้าม Frontend เชื่อม MongoDB หรือ ChromaDB โดยตรง


==================================================
39. FUTURE MONITOR INTEGRATION
==================================================

ออกแบบ Generate page ให้รองรับภายหลัง:

interface GenerationGate {
  ready: boolean;
  source?: "monitor";
}


ตอนนี้:

ready = true

ในอนาคต:

GET /monitor/{curriculumId}/readiness

{
  "generatedReady": true
}


แล้วใช้:

generatedReady
→ enable/disable Generate button


แต่ห้าม implement Monitor API ตอนนี้


==================================================
40. REFERENCE UX
==================================================

Reference Page ต้องให้ความรู้สึกเหมือน:

Document Inspector

ไม่ใช่ Dashboard


ผู้ใช้สามารถ:

1. เลือก PS
2. เลือก Table
3. เลือก Field
4. ดู Value
5. ดู Source
6. ดู Evidence metadata


ตัวอย่าง:

PS
└── Table 1.1
    └── วุฒิการศึกษาสูงสุด
        │
        ├── Value: ปริญญาเอก
        ├── Source: ChromaDB
        ├── Document: xxx
        ├── Page: 3
        └── Chunk: 2


==================================================
41. VISUAL DESIGN
==================================================

ใช้ design system กลาง

กำหนด:

CSS variables:

--color-primary
--color-background
--color-surface
--color-border
--color-text
--color-muted
--color-success
--color-warning
--color-error

Spacing:

4 / 8 / 12 / 16 / 24 / 32 px


Border radius:
เล็กถึงกลาง


Shadow:
minimal


Typography:
อ่านง่าย


อย่าใช้ gradient เยอะ
อย่าใช้ animation เยอะ
อย่าใช้ card ซ้อน card จำนวนมาก


==================================================
42. FILE STRUCTURE REQUIREMENT
==================================================

Project ต้องอ่านง่าย

แยก:

pages
components
services
hooks
types
utils
styles


ห้าม:

- giant component
- duplicate API calls
- duplicate document state
- inline giant CSS
- hardcoded business rules


==================================================
43. DEVELOPMENT MOCK
==================================================

ถ้า Backend API บาง endpoint ยังไม่พร้อม:

สร้าง mock data เฉพาะ development

ตัวอย่าง:

mockGeneratedDocument
mockHistory
mockReference


แต่ต้องใช้ interface เดียวกับ Real API


ดังนั้น:

Component
   ↓
Hook
   ↓
Service Interface
   ↓
Mock API / Real API


ไม่ให้ Component รู้ว่า data มาจาก Mock หรือ Real


==================================================
44. ACCEPTANCE CRITERIA
==================================================

Frontend ถือว่าผ่านเมื่อ:

[ ] React + TypeScript project ทำงานได้

[ ] /generate เปิดได้

[ ] /history เปิดได้

[ ] /reference เปิดได้

[ ] Navigation ทำงาน

[ ] Generate button ทำงาน

[ ] Generate loading state

[ ] Generate success state

[ ] HTML Document Preview

[ ] Edit Document

[ ] Unsaved Changes state

[ ] Save Current Draft

[ ] Save ไม่สร้าง Version

[ ] Download เรียก Backend

[ ] Download เป็นจุดสร้าง Version

[ ] History แสดงเฉพาะ Downloaded Versions

[ ] Preview Version

[ ] Download Version

[ ] Reference Tree

[ ] Reference Details

[ ] Source Badge

[ ] รองรับ ChromaDB source

[ ] รองรับ MongoDB source

[ ] รองรับ Document/OCR source

[ ] รองรับ User Edit source

[ ] Reference รองรับ Version

[ ] Error states

[ ] Empty states

[ ] Responsive

[ ] ไม่มี MongoDB connection ใน Frontend

[ ] ไม่มี ChromaDB connection ใน Frontend

[ ] ไม่มี MCP connection ใน Frontend

[ ] ไม่มี AI logic ใน Frontend

[ ] ไม่มี Readiness logic ใน Frontend

[ ] ไม่มี hardcoded business data

[ ] API logic แยกจาก Components

[ ] TypeScript types แยกชัดเจน

[ ] Component structure สะอาด


==================================================
45. IMPORTANT IMPLEMENTATION RULE
==================================================

ก่อนเขียน Code:

1. ตรวจสอบ Project ปัจจุบัน
2. ตรวจสอบ package.json
3. ตรวจสอบ React/Vite setup
4. ตรวจสอบ existing components
5. ตรวจสอบ existing API conventions
6. ห้ามลบ code เดิมโดยไม่จำเป็น
7. Reuse existing infrastructure ถ้ามี
8. สร้าง folder structure ให้สะอาด

จากนั้น implement:

Phase 1:
App Layout + Routing

Phase 2:
Generate Page

Phase 3:
Document Workspace

Phase 4:
History

Phase 5:
Reference

Phase 6:
API layer

Phase 7:
Error / Loading / Empty states

Phase 8:
Responsive + polish


==================================================
46. FINAL DELIVERABLE
==================================================

หลังทำเสร็จให้รายงาน:

1. Project structure
2. Pages created
3. Components created
4. API services created
5. Types created
6. Routes
7. Current mock API
8. Real API assumptions
9. Save flow
10. Download/version flow
11. Reference flow
12. Future Monitor integration point
13. Tests/build result
14. Remaining TODO

ห้ามบอกว่า API เชื่อมจริงถ้ายังไม่ได้เชื่อมจริง
ห้ามบอกว่า Generate ทำงานจริงถ้ายังเป็น Mock