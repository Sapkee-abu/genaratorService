# TASK 3: Fix Education Semantic Duplicates + Derive Table 1.1 Ordering from Real MongoDB Roles

งานนี้เป็นการแก้ต่อจากผลของ TASK 1 และ TASK 2 ที่รันผ่านแล้ว

IMPORTANT:
ห้ามแก้ MongoDB source data
ห้าม hardcode รายชื่อ 5 คน
ห้าม hardcode ว่าใครเป็น programmeResponsible
ห้ามตัดสิน duplicate จากข้อความที่เห็นใน UI เพียงอย่างเดียว
ต้องตรวจข้อมูลจริงจาก MongoDB และ trace กลับไปถึง Generator ก่อนแก้

==================================================
PART A — ตรวจและแก้ Education Duplicate ของ Table 1.2
==================================================

ปัจจุบัน Table 1.2 ของ:

"รศ.ดร.พีรวิชญ์ เควด"

แสดง:

1. ปร.ด. วิทยาศาสตร์เชิงคํานวณ
2. ปร.ด. ปรัชญาดุษฎีบัณฑิต (วิทยาศาสตร์เชิงคํานวณ)
3. วท.บ. วิทยาศาสตร์เชิงคํานวณ
4. วท.บ. วิทยาศาสตรบัณฑิต (วิทยาศาสตร์เชิงคำนวณ)

ผู้ใช้สงสัยว่า:

1 และ 2 = วุฒิเดียวกันที่ถูกเก็บคนละ representation
3 และ 4 = วุฒิเดียวกันที่ถูกเก็บคนละ representation

ห้ามสรุปว่า duplicate เพียงเพราะข้อความคล้ายกัน

ให้ตรวจ MongoDB จริงจาก collection:

educations

โดยใช้:

personId
degree
field
graduationYear
institution
_id
timestamp

และตรวจ source/reference ที่ Generator ใช้จริงด้วย

--------------------------------------------------
A1. Duplicate classification
--------------------------------------------------

สำหรับ education ของทุกคนที่ถูกนำไปใช้ใน Table 1.2 ให้จัดกลุ่ม:

A = คนละวุฒิจริง
B = คนเดียวกัน แต่ representation ต่างกันของวุฒิเดียวกัน
C = source record duplicate จริง
D = ข้อมูลไม่เพียงพอที่จะสรุป
E = Generator duplicate

ห้าม merge:
- คนละ personId
- คนละวุฒิจริง
- คนละปี/สถาบันที่บ่งชี้ว่าเป็นการศึกษาคนละรายการ
- ข้อมูลที่ยังพิสูจน์ไม่ได้

--------------------------------------------------
A2. ตรวจกรณี พีรวิชญ์ โดยเฉพาะ
--------------------------------------------------

ต้องแสดง Mongo record ของทั้ง 4 รายการก่อนตัดสิน เช่น:

education #1
_id:
personId:
degree:
field:
graduationYear:
institution:

education #2
...

education #3
...

education #4
...

แล้วสรุปอย่างชัดเจนว่า:

1 ↔ 2:
SAME EDUCATION / DISTINCT EDUCATION / UNKNOWN

3 ↔ 4:
SAME EDUCATION / DISTINCT EDUCATION / UNKNOWN

พร้อมเหตุผลจาก field จริงใน MongoDB

ห้ามตัดสินจากข้อความที่ render ในหน้าเว็บเพียงอย่างเดียว

--------------------------------------------------
A3. ถ้าเป็น duplicate representation จริง
--------------------------------------------------

ถ้าพิสูจน์ได้ว่า:

1 และ 2 = education เดียวกัน
3 และ 4 = education เดียวกัน

ให้แสดงใน Table 1.2 เพียงครั้งเดียวต่อวุฒิจริง

ตัวอย่าง:

1. ปร.ด. วิทยาศาสตร์เชิงคํานวณ
2. วท.บ. วิทยาศาสตร์เชิงคํานวณ

แต่:

ห้ามลบ Mongo record
ห้าม update Mongo
ห้ามย้าย education ไป person อื่น

ให้เก็บ source references ของ record ที่ถูก merge ไว้ทั้งหมด

เช่น:

sourceReferences:
[
  education_record_1,
  education_record_2
]

Web Reference ต้องสามารถเปิดดู source records ทั้งหมดที่นำไปสู่ displayed value ได้

--------------------------------------------------
A4. ถ้าเป็นคนละวุฒิจริง
--------------------------------------------------

ถ้าตรวจแล้วพบว่าเป็นคนละ education จริง:

ให้แสดงทั้งคู่เหมือนเดิม

ห้าม dedup เพียงเพราะ degree/field มีข้อความคล้ายกัน

--------------------------------------------------
A5. Global audit
--------------------------------------------------

ห้ามแก้เฉพาะพีรวิชญ์แล้วจบ

ต้อง audit education ของทุก person ที่ถูกใช้ใน Table 1.2 อีกครั้ง

รายงาน:

- total education records
- total persons
- duplicate representation groups
- confirmed source duplicates
- distinct education
- uncertain groups
- generator duplicates
- affected persons
- Mongo _id ของทุก record
- final display decision

==================================================
PART B — Table 1.1 ต้องอิง ROLE จริงจาก MongoDB
==================================================

ปัญหาปัจจุบัน:

Table 1.1 มี 2 กลุ่ม:

1. อาจารย์ผู้รับผิดชอบหลักสูตร
2. อาจารย์ประจำหลักสูตร

จากข้อมูลจริง:
อาจารย์ผู้รับผิดชอบหลักสูตรทั้ง 5 คน
มี role ใน MongoDB เป็นทั้ง:

programmeResponsible
และ
programmeStaff

ดังนั้นในกลุ่ม "อาจารย์ประจำหลักสูตร"
ต้องนำคนที่มี role programmeResponsible มาก่อน

ผลที่ต้องการ:

Group: อาจารย์ประจำหลักสูตร

1–5 = คนที่เป็น programmeResponsible จริง
6–13 = programmeStaff ที่เหลือ

IMPORTANT:
ห้าม hardcode ว่า "5 คนแรก"

ต้อง derive จาก MongoDB appointments

--------------------------------------------------
B1. Source of Truth
--------------------------------------------------

ใช้ collection:

appointments

โดยตรวจ:

curriculumId
personId
role
roleName
status
effectiveDate
appointmentOrder
timestamp

Role ที่ต้องใช้:

programmeResponsible
programmeStaff

ตาม Data Schema ที่กำหนดไว้

ห้ามอ่าน role จาก:
- persons
- ชื่อคน
- ลำดับใน source ที่ดึงมา
- ข้อความจาก prompt
- จำนวน 5 คนที่ผู้ใช้พูด

--------------------------------------------------
B2. หา programmeResponsible จริง
--------------------------------------------------

Query appointments ของ curriculum ปัจจุบัน

filter:

curriculumId = current curriculum
status = active

หา:

role = "programmeResponsible"

สร้าง set ของ personId:

responsiblePersonIds

--------------------------------------------------
B3. หา programmeStaff จริง
--------------------------------------------------

จาก appointments:

role = "programmeStaff"
status = active

สร้าง:

staffPersonIds

--------------------------------------------------
B4. Determine dual-role
--------------------------------------------------

ถ้า personId อยู่ทั้ง:

responsiblePersonIds
และ
staffPersonIds

ถือว่าเป็น:

programmeResponsible + programmeStaff

คนกลุ่มนี้ต้องอยู่ต้นของ section:

"อาจารย์ประจำหลักสูตร"

--------------------------------------------------
B5. Ordering
--------------------------------------------------

Table 1.1 ต้องจัดลำดับดังนี้:

1. active programmeResponsible ที่มี programmeStaff ด้วย
2. active programmeStaff ที่ไม่ใช่ programmeResponsible

แต่ห้าม hardcode จำนวนคน

จำนวนจะเกิดจาก query จริง

ตัวอย่างถ้า DB มี:

programmeResponsible:
A
B
C
D
E

programmeStaff:
A
B
C
D
E
F
G
H
I
J
K
L
M

ผล:

programmeStaff display:

1. A
2. B
3. C
4. D
5. E
6. F
7. G
8. H
9. I
10. J
11. K
12. L
13. M

แต่ถ้าอนาคต DB เปลี่ยนเป็น responsible 4 คน
ต้องได้ 4 คนแรก ไม่ใช่ hardcode 5

--------------------------------------------------
B6. Ordering ต้องอิง appointment data
--------------------------------------------------

สำหรับลำดับภายในแต่ละ role:

ใช้ข้อมูลจาก appointments เช่น:

appointmentOrder
effectiveDate
timestamp
หรือ field ที่ระบบปัจจุบันใช้เป็น canonical ordering

ตรวจ code เดิมก่อน

ห้ามสร้าง ordering ใหม่แบบสุ่ม
ห้ามใช้ชื่อเรียง alphabetically ถ้าเดิมระบบมี canonical appointment order

--------------------------------------------------
B7. Role checkbox ใน Table 1.2
--------------------------------------------------

Table 1.2 ต้องแสดง checkbox ตาม role จริงจาก appointments

ถ้า person มี:

programmeResponsible
+
programmeStaff

ต้องได้:

☑ อาจารย์ประจำหลักสูตร
☑ อาจารย์ผู้รับผิดชอบหลักสูตร

ถ้ามีเฉพาะ programmeStaff:

☑ อาจารย์ประจำหลักสูตร
☐ อาจารย์ผู้รับผิดชอบหลักสูตร

ถ้ามีเฉพาะ programmeResponsible:

☐ อาจารย์ประจำหลักสูตร
☑ อาจารย์ผู้รับผิดชอบหลักสูตร

ห้าม infer role จากตำแหน่งทางวิชาการ
ห้าม infer role จากชื่อ
ห้าม infer role จากลำดับ

==================================================
PART C — ห้ามกระทบส่วนที่ PASS แล้ว
==================================================

ห้ามเปลี่ยน:

- Table 1.2 numeric values 65/65
- academic position formatting
- Table 1.1 name format
- Table 1.2 name format
- education year removal
- generated_documents migration
- 1 Version = 1 document
- Version immutability
- History
- Download versioning
- Reference architecture
- Monitor
- Source MongoDB data
- ChromaDB
- MCP
- Verification
- Template structure
- Traceability Matrix removal

แก้เฉพาะ:

1. education semantic duplicate handling
2. Table 1.1 role-based ordering
3. role checkbox correctness if required by the same underlying issue

==================================================
PART D — Traceability
==================================================

หลังแก้แล้ว Web Reference ต้องยังสามารถ trace:

Table 1.2 education
→ displayed value
→ education record(s)
→ MongoDB
→ personId
→ _id

ถ้า displayed value เป็นผลจากการ merge duplicate representation:

ต้องแสดง sourceReferences ทั้งหมด

ห้ามสร้าง Traceability Matrix กลับเข้า DOCX

==================================================
PART E — TESTS
==================================================

เพิ่ม/แก้ tests อย่างน้อย:

1. test education semantic duplicate
2. test education distinct records are preserved
3. test cross-person identical education is NOT merged
4. test source duplicate references are preserved
5. test programmeResponsible is derived from appointments
6. test dual-role person is placed first in programmeStaff
7. test no hardcoded "5"
8. test role checkbox comes from appointments
9. test inactive appointment does not determine current role
10. test Table 1.2 numeric values remain 65/65
11. test source MongoDB remains unchanged
12. test Web Reference still resolves all source records

==================================================
PART F — REAL WEB E2E
==================================================

ต้องทดสอบผ่าน Real Web:

Browser
→ /api/dev/generate
→ Master Agent
→ Retrieval Manager
→ MCP
→ MongoDB / ChromaDB
→ PS Agent
→ Verification
→ Reference Mapping
→ Template Injection
→ DOCX
→ HTML Preview

ห้ามใช้ mock data
ห้ามใช้ real_generate.py เป็น Web path

==================================================
PART G — REQUIRED FINAL REPORT
==================================================

รายงานผลเป็น 2 ส่วน

PART 1 — Education Audit

แสดง table:

Person
Education IDs
Degree
Field
Year
Institution
Classification
Final display
Reason

โดยเฉพาะ:

พีรวิชญ์:
1 ↔ 2
3 ↔ 4

ต้องตอบให้ชัดว่า:
"ซ้ำจริง" หรือ "ไม่ซ้ำจริง"

พร้อมหลักฐานจาก MongoDB fields

PART 2 — Role Audit

แสดง:

person
personId
programmeResponsible
programmeStaff
status
appointment order
final Table 1.1 position

ต้องพิสูจน์ว่า Table 1.1 ordering มาจาก appointments จริง

ห้ามรายงานเพียงว่า "ผ่าน"
ต้องแสดงข้อมูลที่ใช้ตัดสิน

==================================================
SUCCESS CRITERIA
==================================================

PASS เมื่อ:

1. พีรวิชญ์ไม่มี education duplicate ที่พิสูจน์แล้วว่าเป็น representation เดียวกัน
2. ถ้า education เป็นคนละวุฒิจริง จะไม่ถูก dedup
3. MongoDB source ไม่ถูกแก้
4. Reference ยัง trace source records ได้ครบ
5. Table 1.1 ดึง role จาก appointments จริง
6. programmeResponsible + programmeStaff อยู่ต้นของ programmeStaff section ตาม role จริง
7. ไม่มี hardcoded รายชื่อหรือ hardcoded จำนวน 5
8. checkbox role ถูกต้องตาม appointments
9. Table 1.2 numeric values ยัง 65/65
10. Existing regression tests ยังผ่าน
11. Real Web E2E ผ่าน
12. Production Monitor gate ไม่ถูกแก้