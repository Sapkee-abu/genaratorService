ผมต้องการให้คุณตรวจสอบ SOURCE CODE จริงของโปรเจกต์ Generator Service นี้

เป้าหมายคือผมต้องการ "ทำความเข้าใจระบบ HTML Preview"
โดยเฉพาะว่า HTML Preview ของระบบเรา:

1. ใช้หลักการอะไรในการสร้าง
2. อิงจาก Template DOCX หรือไม่
3. อิงจาก Generated DOCX หรือไม่
4. ใช้ Template Structure JSON หรือไม่
5. มี HTML Template แยกหรือไม่
6. ไฟล์ที่เกี่ยวข้องอยู่ที่ไหน
7. Folder ไหน
8. Function / Class ไหนเป็นคนทำงาน
9. ถ้าเปลี่ยน Template DOCX แล้ว HTML Preview จะเปลี่ยนตามหรือไม่
10. HTML Preview ตรงกับ Template DOCX จริงแค่ไหน

============================================================
IMPORTANT RULE
============================================================

ห้ามตอบจาก SRS อย่างเดียว
ห้ามเดา
ห้ามอนุมานจากชื่อไฟล์
ห้ามบอกว่า "น่าจะ"
ห้ามสร้าง path ขึ้นมาเอง

ต้องตรวจ SOURCE CODE จริงของ project เท่านั้น

ทุกข้อที่ตอบต้องมี:

- Exact file path
- Folder
- Class/function
- Input
- Output
- Code evidence หรืออธิบายจาก code ที่ตรวจพบ

ถ้าหาไม่พบ ให้เขียน:

NOT FOUND IN SOURCE CODE

ถ้า source code มีหลายจุด ให้แสดงทุกจุดที่เกี่ยวข้องและอธิบายว่าแต่ละจุดทำอะไร

ห้ามแก้ไข code
ห้าม refactor
ห้ามสร้างไฟล์ใหม่

นี่เป็น READ-ONLY SOURCE CODE AUDIT เท่านั้น

============================================================
PART 1 — หา Template DOCX จริง
============================================================

ค้นหา Template DOCX ที่ Generator Service ใช้จริง

ผมต้องการทราบ:

1. Template filename จริงคืออะไร
2. อยู่ folder ไหน
3. Exact path คืออะไร
4. Backend file ไหนเป็นคนโหลด Template
5. Function/Class ไหนโหลด Template
6. Template โหลดจาก:
   - local filesystem
   - MongoDB
   - HTTP/API
   - หรือที่อื่น
7. Template ถูกส่งต่อไปยัง component ไหน

ถ้ามีไฟล์ชื่อ template2.docx ให้ยืนยันจาก source code ว่า:

"template2.docx ถูกใช้งานจริง"

หรือ

"template2.docx ไม่ได้ถูกใช้งานใน active flow"

ห้ามสรุปจากชื่อไฟล์อย่างเดียว

============================================================
PART 2 — Template Parser
============================================================

ค้นหา Template Parser ตัวจริง

ตอบ:

1. File path
2. Folder
3. Class
4. Function
5. Library ที่ใช้
6. Input คืออะไร
7. Output คืออะไร
8. ใครเป็นคนเรียก Parser
9. Parser อ่านอะไรจาก DOCX บ้าง

โดยเฉพาะ:

- tables
- rows
- columns
- cells
- headers
- merged cells
- paragraphs
- formatting
- styles
- placeholder/slot

แสดงตัวอย่างโครงสร้าง JSON ที่ Parser สร้างจริงจาก source code

อธิบายด้วยภาษาง่าย ๆ ว่า:

"Parser ทำหน้าที่อะไร"

============================================================
PART 3 — Template Structure JSON
============================================================

ค้นหาว่า Template Structure JSON ถูกสร้างที่ไหนและเก็บไว้ที่ไหน

ตอบ:

- File
- Folder
- Function
- Class
- Schema/model ถ้ามี
- JSON structure

และตอบ:

Template Structure JSON ใช้ในขั้นตอนใดบ้าง?

เช่น:

Template DOCX
→ Parser
→ Template Structure JSON
→ Agent
→ Injection

หรือ flow อื่น

ต้องอิง source code จริง

============================================================
PART 4 — Template Injection
============================================================

ค้นหา code ที่นำข้อมูลจาก Agent ไปใส่ใน DOCX

ตอบ:

1. File path
2. Folder
3. Function
4. Class
5. Input
6. Output

อธิบายว่า:

Agent Result JSON
↓
Mapping
↓
Template
↓
DOCX

ทำงานอย่างไร

ตรวจด้วยว่า:

- เขียนลง cell อย่างไร
- เพิ่ม row อย่างไร
- รักษา formatting อย่างไร
- รักษา merge อย่างไร
- ใช้ template DOCX เดิมหรือสร้าง DOCX ใหม่
- Agent แตะ DOCX โดยตรงหรือไม่

============================================================
PART 5 — Generated DOCX
============================================================

ค้นหาจุดที่สร้าง Generated DOCX จริง

ตอบ:

- File path
- Folder
- Function
- Class
- Filename pattern
- Output path
- ใครเรียก function นี้
- เรียกหลัง Verification หรือก่อน Verification

สร้าง flow จริงจาก source code:

Template DOCX
↓
Template Parser
↓
Template Structure
↓
Criterion Agent
↓
Verification
↓
Reference Mapping
↓
Template Injection
↓
Generated DOCX

ถ้า flow จริงไม่เหมือนนี้ ให้แก้ตาม source code

============================================================
PART 6 — HTML PREVIEW
============================================================

นี่คือส่วนที่สำคัญที่สุด

ค้นหา SOURCE CODE ทุกจุดที่เกี่ยวข้องกับ:

- HTML Preview
- preview
- document preview
- render HTML
- HTML renderer
- DOCX renderer
- DOCX to HTML
- document conversion
- editor
- preview API

ค้นหาทั้ง:

backend/
frontend/

ตอบให้ชัด:

1. HTML Preview อยู่ไฟล์ไหน?
2. Folder ไหน?
3. Exact path คืออะไร?
4. Backend หรือ Frontend เป็นคนสร้าง HTML?
5. Function/Class ไหนเป็นคนสร้าง?
6. API endpoint ไหนเกี่ยวข้อง?
7. HTTP method อะไร?
8. Input คืออะไร?
9. Output คืออะไร?

============================================================
PART 7 — HTML ถูกสร้างจากอะไร?
============================================================

ต้องตอบคำถามนี้แบบฟันธงจาก source code:

HTML Preview ถูกสร้างจากอะไร?

เลือกหนึ่งหรือหลายข้อ:

A. Template DOCX โดยตรง

B. Generated DOCX

C. Template Structure JSON

D. Generated JSON / Result JSON

E. Current Draft

F. HTML Template แยกต่างหาก

G. React JSX/component

H. อื่น ๆ

ถ้าเป็นหลายขั้น ให้แสดงทั้งหมด

ตัวอย่าง:

Generated DOCX
↓
DOCX-to-HTML converter
↓
HTML
↓
API
↓
React Preview

หรือ:

Template Structure JSON
↓
HTML Renderer
↓
HTML
↓
React

ต้องห้ามเดา

============================================================
PART 8 — ถ้า DOCX ถูกแปลงเป็น HTML
============================================================

ถ้าระบบใช้วิธี:

DOCX
↓
HTML

ให้ระบุ:

1. Library อะไร
2. File ไหน import library
3. Function ไหนเรียก
4. Input file คืออะไร
5. Output HTML อยู่ที่ไหน
6. CSS อยู่ที่ไหน
7. รูปภาพใน DOCX จัดการอย่างไร
8. Table จัดการอย่างไร
9. Merge cell จัดการอย่างไร
10. Font/style จัดการอย่างไร

ตัวอย่าง library ที่ต้องค้นหา:

- mammoth
- LibreOffice
- pandoc
- python-docx
- docx2html
- html renderer
- OpenXML
- อื่น ๆ

อย่าสรุปว่ามี library เหล่านี้จนกว่าจะพบใน source code

============================================================
PART 9 — ถ้า HTML ไม่ได้มาจาก DOCX
============================================================

ถ้าพบว่า HTML Preview ไม่ได้แปลงจาก DOCX

ให้ตรวจว่า HTML ถูกสร้างจากอะไร

เช่น:

Template Structure JSON
หรือ
Generated JSON
หรือ
React component
หรือ
HTML template

แล้วตอบ:

1. File path
2. Folder
3. Function
4. Component
5. Input
6. Output
7. วิธีสร้าง table
8. วิธีสร้าง row
9. วิธีสร้าง column
10. วิธีจัด style

============================================================
PART 10 — FRONTEND PREVIEW
============================================================

ตรวจ React frontend

ค้นหา page/component ที่แสดง HTML Preview

ตอบ:

1. File path
2. Folder
3. Component name
4. Hook ที่ใช้
5. API ที่เรียก
6. Response ที่ได้รับ
7. HTML ถูก render อย่างไร

ตรวจว่ามี:

- iframe
- innerHTML
- dangerouslySetInnerHTML
- blob
- document parser
- custom renderer

หรือไม่

ถ้ามี ให้ระบุ exact file/function

============================================================
PART 11 — CSS
============================================================

ผมต้องการรู้ว่า "หน้าตา HTML Preview" ถูกควบคุมโดยอะไร

ค้นหา CSS จริง

ตอบ:

- CSS file path
- Folder
- class names
- component
- styles

โดยเฉพาะ:

- page size
- margin
- table border
- font
- line height
- width
- alignment
- merged cells
- page break

ตอบด้วยว่า:

CSS นี้มาจาก Template DOCX หรือเป็น CSS ที่เขียนแยกใน Web?

============================================================
PART 12 — HTML กับ Template DOCX ตรงกันหรือไม่
============================================================

ตรวจเชิงโครงสร้างจริง

เปรียบเทียบ:

Template DOCX
กับ
HTML Preview

ตรวจ:

1. จำนวน Table
2. ลำดับ Table
3. จำนวน Column
4. Header
5. จำนวน Row
6. Cell
7. Merged Cell
8. Paragraph
9. Text
10. Font
11. Border
12. Alignment
13. Width
14. Page structure

ตอบเป็นตาราง:

| ส่วน | Template DOCX | HTML Preview | ตรงกันไหม | หลักฐาน |
|---|---|---|---|---|

ห้ามใช้คำว่า "น่าจะตรง"

ถ้าตรวจไม่ได้ ให้เขียน:

NOT VERIFIED

============================================================
PART 13 — สำคัญมาก:
ถ้าเปลี่ยน Template DOCX จะเกิดอะไรขึ้น?
============================================================

ตรวจจาก source code จริง

สมมติผมเปลี่ยน:

template2.docx

เช่น:

- เพิ่ม Table
- ลบ Table
- เปลี่ยน Header
- เพิ่ม Column
- เปลี่ยน Column order
- เพิ่ม Row
- เปลี่ยน Merge
- เปลี่ยน Font

แล้ว Generate ใหม่

HTML Preview จะ:

A. เปลี่ยนตาม Template อัตโนมัติ

B. เปลี่ยนบางส่วน

C. ไม่เปลี่ยน

D. ระบบพัง

ตอบแต่ละกรณีตาม source code จริง

============================================================
PART 14 — ถ้าเปลี่ยน HTML/CSS
============================================================

สมมติแก้ CSS ของ Preview

ตอบ:

HTML Preview เปลี่ยนหรือไม่?

Generated DOCX เปลี่ยนหรือไม่?

เพราะอะไร?

ต้องอธิบาย dependency:

Template
↓
Generated DOCX
↓
HTML Preview
↓
CSS

หรือ dependency ที่ source code ใช้จริง

============================================================
PART 15 — EDIT / SAVE
============================================================

ตรวจต่อว่า User Edit ทำงานอย่างไร

Flow:

HTML Preview
↓
Edit
↓
Save

ตอบ:

1. HTML ที่แก้เก็บไว้ที่ไหน
2. Current Draft คืออะไร
3. Save endpoint ไหน
4. Backend file ไหน
5. Function ไหน
6. Save สร้าง DOCX ใหม่หรือไม่
7. Save สร้าง Version หรือไม่
8. Download ทำอะไร
9. Download สร้าง Version อย่างไร

============================================================
PART 16 — TEST / E2E
============================================================

ค้นหา test ที่เกี่ยวข้องกับ:

- preview
- HTML
- generated DOCX
- template
- editor
- save
- download

ระบุ:

- test file
- test function
- assertion

และตอบว่า:

มี test ที่พิสูจน์หรือไม่ว่า

Template DOCX
→ Generated DOCX
→ HTML Preview

มีโครงสร้างตรงกัน?

ถ้ามี แสดง test

ถ้าไม่มี:

NOT VERIFIED BY TEST

============================================================
PART 17 — FINAL ARCHITECTURE
============================================================

หลังจากตรวจ source code จริงทั้งหมดแล้ว
สร้าง diagram ที่ตรงกับ implementation จริง

ตัวอย่างรูปแบบ:

Template DOCX
   ↓
[exact parser file/function]
   ↓
Template Structure JSON
   ↓
[exact agent/master file]
   ↓
Verification
   ↓
[exact injection file/function]
   ↓
Generated DOCX
   ↓
[exact HTML renderer file/function]
   ↓
HTML
   ↓
[exact API endpoint]
   ↓
[exact React component]
   ↓
HTML Preview

ถ้า implementation จริงต่างจาก diagram นี้ ให้ใช้ของจริง

============================================================
PART 18 — FINAL ANSWER
============================================================

สรุปสุดท้ายให้ผมเข้าใจง่าย แต่ต้องอ้างอิง source code จริง

ตอบคำถาม:

1. HTML Preview คืออะไรในระบบนี้?
2. HTML Preview อิงจาก Template DOCX หรือไม่?
3. HTML Preview อิงจาก Generated DOCX หรือไม่?
4. HTML Preview ใช้ Template Structure JSON หรือไม่?
5. มี HTML Template แยกหรือไม่?
6. ตัวไหนเป็น Source of Truth ของโครงสร้างเอกสาร?
7. Template DOCX อยู่ไฟล์ไหน?
8. Template Parser อยู่ไฟล์ไหน?
9. Template Injection อยู่ไฟล์ไหน?
10. Generated DOCX อยู่ไฟล์ไหน?
11. HTML Renderer อยู่ไฟล์ไหน?
12. Preview API อยู่ไฟล์ไหน?
13. Frontend Preview Component อยู่ไฟล์ไหน?
14. CSS Preview อยู่ไฟล์ไหน?
15. ถ้าเปลี่ยน Template DOCX HTML จะเปลี่ยนตามหรือไม่?
16. HTML Preview ตรงกับ Template DOCX ในระดับใด?
17. จุดไหนที่ "ตรง"
18. จุดไหนที่ "ไม่ตรง"
19. จุดไหนที่ยัง "ไม่สามารถยืนยันได้"

============================================================
OUTPUT FORMAT
============================================================

ให้รายงานเป็น 5 ส่วน:

SECTION 1
"คำตอบสั้น ๆ"

SECTION 2
"Architecture จริงจาก Source Code"

SECTION 3
"File/Folder Map"

ตัวอย่าง:

backend/
├── ...
│   └── ...
frontend/
├── ...
│   └── ...

พร้อมบอกหน้าที่ของแต่ละไฟล์

SECTION 4
"HTML Preview ทำงานทีละขั้น"

อธิบายตั้งแต่:

Template DOCX
→ Parser
→ Structure
→ Injection
→ Generated DOCX
→ HTML
→ Frontend Preview

SECTION 5
"ตรวจว่า HTML ตรงกับ Template หรือไม่"

ใช้ตาราง:

| สิ่งที่ตรวจ | ผล | Source Evidence |
|---|---|---|

และสุดท้ายให้ตอบ:

"ถ้าผมเปลี่ยน template2.docx แล้ว Generate ใหม่ HTML Preview จะเปลี่ยนตามหรือไม่?"

โดยต้องตอบจาก source code จริงเท่านั้น