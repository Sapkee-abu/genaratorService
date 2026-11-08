คุณกำลังแก้ไข Generator Service ของระบบ AUN-QA SAR Generator

เป้าหมาย:
แก้ปัญหาที่พบจาก Real End-to-End Generation โดยต้องรักษา Architecture และ Flow ที่กำหนดไว้เดิม ห้ามแก้สถาปัตยกรรมหลักโดยไม่จำเป็น

==================================================
1. ARCHITECTURE ที่ต้องรักษา
==================================================

Flow หลัก:

IMPORT
  ↓
Data Ready
  ↓
MONITOR
  ↓
GET /monitor/{curriculumId}/readiness
  ↓
{
  "generatedReady": true
}
  ↓
WEB เปิด Generate
  ↓
USER กด Generate
  ↓
GENERATOR
  ↓
MASTER AGENT
  ↓
Template DOCX
  ↓
Template Parser
  ↓
Template Structure JSON
  ↓
Criterion Agent
  ↓
Data Request
  ↓
Master
  ↓
Retrieval Manager
  ↓
MCP
  ↓
Data Sources
  ├── ChromaDB
  ├── MongoDB
  └── Document/OCR
  ↓
Retrieved Data
  ↓
Master
  ↓
Requesting Agent
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


ห้ามเปลี่ยน flow นี้

ห้ามให้ Criterion Agent:
- ติดต่อ MongoDB โดยตรง
- ติดต่อ ChromaDB โดยตรง
- อ่าน filesystem โดยตรง
- เรียก OCR โดยตรง
- แก้ DOCX โดยตรง

ต้องเป็น:

Criterion Agent
→ Master
→ Retrieval Manager
→ MCP
→ MCP Tools
→ Data Sources


==================================================
2. READINESS
==================================================

Generator ห้ามคำนวณ Readiness เอง

Generator ต้องใช้:

GET /monitor/{curriculumId}/readiness

response:

{
  "generatedReady": true
}

ถ้า generatedReady == true:
    อนุญาต Generate

ถ้า generatedReady == false:
    block Generate

ถ้า Monitor unavailable:
    block Generate

ห้าม Generator อ่าน ps_requirements เพื่อคำนวณ readiness เอง

ห้ามสร้าง readiness logic ใหม่ใน Generator


==================================================
3. RETRIEVAL ORDER — สำคัญมาก
==================================================

ต้องรักษาลำดับ:

ChromaDB → MongoDB → Document/OCR

แต่ fallback ต้องเป็น "ราย Field"

ห้ามใช้ logic แบบ:

if chroma_returned_anything:
    use_chroma_for_everything

เพราะผิด

ต้องใช้:

for each requested field:

    query Chroma

    evaluate whether Chroma evidence
    actually supports THIS field

    if sufficient evidence:
        use Chroma result

    else:
        query MongoDB

    if MongoDB does not provide sufficient data:
        fallback to Document/OCR if applicable

    if still unavailable:
        mark field as missing


ตัวอย่าง:

Person A:

highest_education_level:
    Chroma = sufficient
    => use Chroma

degree_name:
    Chroma = insufficient
    => MongoDB

academic_work_count:
    Chroma = insufficient
    => MongoDB

ดังนั้นข้อมูลหนึ่ง record สามารถมี source ต่างกันในแต่ละ field ได้


==================================================
4. IMPORTANT — "CHROMA FOUND" ต้องหมายถึงอะไร
==================================================

ห้ามถือว่า:

Chroma search returned 5 chunks
=
field found

ไม่ถูกต้อง

ต้องตรวจว่า retrieved evidence มีข้อมูลที่สนับสนุน field ที่ร้องขอจริงหรือไม่

ตัวอย่าง:

Request:
highest_education_level

Chroma chunk มี:
"ปรัชญาดุษฎีบัณฑิต (เทคโนโลยีสารสนเทศ)"

สามารถใช้เป็น evidence เพื่อหา education level ได้
ก็ต่อเมื่อ evidence/context สนับสนุนว่าเป็นระดับปริญญาเอก

แต่ถ้า chunk แค่กล่าวถึงชื่อบุคคลโดยไม่มี education information:

ถือว่า insufficient

ต้อง fallback MongoDB


==================================================
5. IMPORTANT — "วุฒิการศึกษาสูงสุด"
==================================================

Table 1.1 column:

"วุฒิการศึกษาสูงสุด"

หมายถึง "ระดับการศึกษาสูงสุด"

ตัวอย่าง output ที่ถูกต้อง:

ปริญญาเอก
ปริญญาโท
ปริญญาตรี

ห้ามตีความ column นี้เป็นชื่อปริญญาเต็ม

ห้ามทำ:

ปร.ด.
→ ปรัชญาดุษฎีบัณฑิต

วท.ม.
→ วิทยาศาสตรมหาบัณฑิต

วศ.บ.
→ วิศวกรรมศาสตรบัณฑิต

Ph.D.
→ Doctor of Philosophy

สิ่งเหล่านี้เป็น "degree name" ไม่ใช่ "highest education level"

ดังนั้นต้องแยก semantic field:

highest_education_level
=
ปริญญาเอก / ปริญญาโท / ปริญญาตรี

degree_name
=
ชื่อปริญญาจริง

field
=
สาขาวิชา


ห้ามให้ LLM เดา/ขยาย abbreviation เพื่อสร้าง highest_education_level

ต้องใช้ evidence จาก Chroma ก่อน
ถ้าไม่พอ fallback MongoDB


==================================================
6. TABLE 1.1 — PERSON IDENTITY
==================================================

Table 1.1 ต้องใช้ personId เป็น identity key

ห้ามใช้ชื่อเป็น primary key

ข้อมูล person มาจาก:

persons

โดย field ที่สำคัญ:

personId
title
firstName
lastName
fullName
academicPosition

Role ไม่ได้อยู่ใน persons

Role อยู่ใน:

appointments


==================================================
7. TABLE 1.1 — ชื่อ
==================================================

สำหรับ column:

"ชื่อ-นามสกุล"

ต้องใช้:

firstName + lastName

ห้ามใช้ fullName ถ้า fullName มี title/academic title อยู่แล้ว

ตัวอย่างปัญหาที่เกิดขึ้น:

persons.fullName:
"ผศ. ดร. สมชาย ใจดี"

แล้วระบบเอา academic title มาต่ออีกครั้ง:

"ผศ. ผศ. ดร. สมชาย ใจดี"

ห้ามเกิดกรณีนี้

ชื่อใน Table 1.1 ต้องไม่มี academic position ซ้ำ


==================================================
8. TABLE 1.1 — ACADEMIC POSITION
==================================================

Column:

"ตำแหน่งทางวิชาการ"

ต้อง map จาก:

persons.academicPosition

ต้องไม่เอาค่าจาก:

fullName

ต้องไม่ append title เข้าไปใน name field


==================================================
9. TABLE 1.1 — HIGHEST EDUCATION
==================================================

Column:

"วุฒิการศึกษาสูงสุด"

สร้าง semantic field ใหม่ให้ชัดเจน:

highest_education_level

ค่าที่ต้องการ:

ปริญญาเอก
ปริญญาโท
ปริญญาตรี

ห้ามใช้:

degree abbreviation

เป็น output โดยตรง

ห้ามขยาย abbreviation ด้วย LLM แบบเดาสุ่ม

Retrieval:

Chroma first
Mongo fallback


==================================================
10. TABLE 1.1 — DEGREE + FIELD
==================================================

Column:

"ชื่อปริญญา (สาขาวิชา)"

เป็นคนละ field กับ highest_education_level

ต้องใช้:

degree
+
field

จาก evidence

ตัวอย่าง conceptual structure:

{
  "highest_education_level": "ปริญญาเอก",
  "degree_name": "ปรัชญาดุษฎีบัณฑิต",
  "field": "เทคโนโลยีสารสนเทศ"
}

ห้ามนำ degree_name มาใส่ใน highest_education_level


==================================================
11. PERSON ROLE MERGING — สำคัญมาก
==================================================

appointments อาจมีหลาย record ต่อ person

ตัวอย่าง:

person A:
    programmeResponsible
    programmeStaff

person B:
    programmeStaff

ห้ามสร้าง person A สอง record

ต้อง aggregate ด้วย:

personId

ก่อนสร้าง Result JSON


ตัวอย่าง:

Input:

[
  {
    personId: "A",
    role: "programmeResponsible"
  },
  {
    personId: "A",
    role: "programmeStaff"
  },
  {
    personId: "B",
    role: "programmeStaff"
  }
]

ต้องกลายเป็น:

[
  {
    personId: "A",
    roles: [
      "programmeResponsible",
      "programmeStaff"
    ]
  },
  {
    personId: "B",
    roles: [
      "programmeStaff"
    ]
  }
]


==================================================
12. TABLE ORDER
==================================================

ลำดับบุคคลใน Table 1.1 และ Table 1.2 ต้อง deterministic

อันดับแรก:

คนที่มีมากกว่า 1 role

เช่น:

programmeResponsible + programmeStaff

จากนั้น:

คนที่มี role เดียว

เช่น:

programmeStaff เท่านั้น


ดังนั้น:

Group A:
roles.length > 1

Group B:
roles.length == 1


ตัวอย่าง:

A = Responsible + Staff
B = Responsible + Staff
C = Staff
D = Staff
E = Staff

Output:

A
B
C
D
E


ห้ามแยก A เป็นสอง row


==================================================
13. TABLE 1.2 — CHECKBOX
==================================================

Checkbox ต้องคำนวณจาก merged roles

ถ้า:

roles = [
  programmeResponsible,
  programmeStaff
]

ต้อง:

Responsible = checked
Staff = checked


ถ้า:

roles = [
  programmeStaff
]

ต้อง:

Responsible = unchecked
Staff = checked


ห้ามตรวจ checkbox จาก appointment record เพียง record เดียว


==================================================
14. TABLE 1.2 — PERSON ORDER
==================================================

Table 1.2 ต้องใช้ person identity และ role aggregation ชุดเดียวกับ Table 1.1

ห้ามให้ Table 1.1 ใช้ person aggregation แบบหนึ่ง
และ Table 1.2 ใช้อีกแบบหนึ่ง

สร้าง canonical person-role aggregation หนึ่งชุด

แล้วให้ทั้งสอง table ใช้ชุดเดียวกัน


==================================================
15. TABLE 1.2 — ห้ามสร้าง ROW ใหม่
==================================================

Generator ห้าม clone/create template row เองเพื่อเพิ่มจำนวนบุคคล

ต้องใช้ template blocks ที่ Parser ตรวจพบ

ถ้า:

records < template blocks

ให้ fill ตามลำดับ
และปล่อย block ที่เหลือไว้ตาม template

ถ้า:

records > template blocks

ให้ถือเป็น injection error

ห้ามสร้าง row ใหม่โดยอัตโนมัติ


==================================================
16. TABLE 1.2 — EDUCATION
==================================================

Field:

"วุฒิการศึกษา (ทุกระดับ)"

ต้องไม่ปล่อยว่างหาก source มีข้อมูล

ต้องรวบรวม education ของ person จาก:

Chroma first
Mongo fallback

โดย education ทุกระดับสามารถมีหลาย records

ตัวอย่าง:

[
  ปริญญาตรี ...
  ปริญญาโท ...
  ปริญญาเอก ...
]

ต้อง map ให้ตรงกับ field ใน Template Structure

ห้ามใช้เฉพาะ highest education มาทดแทน education ทุกระดับ


==================================================
17. TABLE 1.2 — ACADEMIC WORK
==================================================

Column ที่เกี่ยวกับ:

"จำนวนผลงานตามเกณฑ์คุณสมบัติผู้รับผิดชอบหลักสูตร
(ย้อนหลัง 5 ปีการศึกษา) พ.ศ."

ต้องเป็น "จำนวน"

ไม่ใช่ชื่อผลงาน

ห้ามใส่:

title
publication title
ชื่อบทความ

ลงในช่อง count


ต้อง aggregate academic_works ต่อ person


==================================================
18. ACADEMIC WORK COUNT
==================================================

academic_works schema มี:

personId
workType
title
publicationYear
database
quartile

ต้องใช้:

personId
workType
publicationYear

ในการ aggregate


ห้ามใช้:

educations.graduationYear

ในการนับผลงาน


สำคัญ:

graduationYear
=
ปีจบการศึกษา

publicationYear
=
ปีที่ผลงานเผยแพร่

คนละ semantic กัน


==================================================
19. FIVE-YEAR RANGE
==================================================

สำหรับ field:

"ย้อนหลัง 5 ปีการศึกษา พ.ศ."

ต้องใช้ช่วงปีที่กำหนดใน Template / Requirement จริง

จากข้อมูลที่ตรวจพบ ผู้ใช้ระบุช่วง:

2565–2569

ดังนั้นต้องไม่ให้ LLM เลือกปีเอง

ต้องสร้าง deterministic year range:

2565
2566
2567
2568
2569


จากนั้น aggregate:

personId
+
publicationYear
+
workType


ตัวอย่าง:

Person A:

2565 academic = 2
2565 creative = 1

2566 academic = 1
2566 creative = 0

...


ต้องไม่ใช้ค่าปีที่ผิดประเภท เช่น:

2022
2023
2024

โดยตรงในช่องที่ต้องเป็น พ.ศ.


==================================================
20. YEAR NORMALIZATION
==================================================

ต้องตรวจสอบ source จริงก่อนทำ normalization

ถ้า publicationYear เป็น Gregorian:

2022
2023
2024

ต้อง normalize เป็น Buddhist Era ก่อนแสดงใน field พ.ศ.

ตัวอย่าง:

2022 → 2565
2023 → 2566
2024 → 2567

แต่ห้าม assume source ทุก record เป็น Gregorian

ต้อง inspect actual data type/value

ถ้า source เป็น 2565 อยู่แล้ว:
    ต้องไม่บวก 543 ซ้ำ

ต้องมี deterministic helper เช่น:

normalize_publication_year()

และมี test สำหรับ:

2022 → 2565
2565 → 2565
2023 → 2566
2566 → 2566


ห้ามให้ LLM เป็นผู้แปลงปี


==================================================
21. WORK TYPE
==================================================

ต้องตรวจสอบค่า workType จริงจาก data source

แล้ว map เป็น category:

academic
creative

ห้ามเดา category จาก title

ถ้า workType ไม่ตรงกับ supported category:

mark as unsupported / missing

อย่านับแบบสุ่ม


==================================================
22. ACADEMIC / CREATIVE COUNT
==================================================

สำหรับแต่ละ person และแต่ละปี:

academic_count
creative_count

ต้องเป็น integer

ตัวอย่าง:

{
  "personId": "A",
  "year": 2565,
  "academic_count": 2,
  "creative_count": 1
}


ห้าม output:

"2 works"
"บทความ A, บทความ B"

หาก Template ต้องการ numeric count
ต้องส่ง numeric count


==================================================
23. CHROMA VS MONGO SOURCE TRACEABILITY
==================================================

ทุก field ที่นำมาใช้ต้องมี source metadata

ตัวอย่าง:

{
  "field": "highest_education_level",
  "value": "ปริญญาเอก",
  "source": "chroma",
  "source_reference": {
    "documentId": "...",
    "page": 3,
    "chunkIndex": 2
  }
}

ถ้า fallback:

{
  "field": "highest_education_level",
  "value": "ปริญญาเอก",
  "source": "mongodb",
  "source_reference": {
    "collection": "educations",
    "document_id": "..."
  }
}


ห้ามระบุ Chroma เป็น source หาก value จริงมาจาก Mongo


==================================================
24. SOURCE DATA VS USER EDIT
==================================================

Source Data ต้อง immutable

User Edit ห้ามเขียนกลับไป:

persons
educations
appointments
academic_works

User Edit ต้องถูกเก็บเป็น document draft/edit layer ตาม architecture เดิม

Generate ใหม่ต้องดึง Source Data ใหม่

ห้ามใช้ User Edit เป็น source ของ Generate รอบใหม่


==================================================
25. RESULT JSON
==================================================

Agent ต้องส่ง Result JSON ตาม Output Schema

ต้องไม่สร้าง slot ใหม่

ต้องไม่เปลี่ยน:

slot_id
type
headers

ต้อง map data ลง slot ที่มีอยู่ใน Template Structure


==================================================
26. DO NOT LET LLM DO DETERMINISTIC DATA AGGREGATION
==================================================

สิ่งเหล่านี้ต้องทำด้วย deterministic Python/business logic:

- merge personId
- merge roles
- sort multi-role first
- numbering
- checkbox state
- year normalization
- academic count
- creative count
- highest education level normalization
- mapping person fields
- mapping education records
- mapping work records

LLM มีหน้าที่:

- understand template semantics
- determine data requirement
- request evidence
- compose narrative if required
- map evidence to semantic fields

LLM ห้ามเป็นผู้คำนวณ count หรือ sort หลัก


==================================================
27. NUMBERING
==================================================

ตรวจสอบ Template Structure ก่อนว่า numbering ถูกออกแบบไว้อย่างไร

ถ้ามี numbering field/slot:
    populate ตาม canonical person order

ถ้า template ใช้ numbering ใน cell:
    inject number อย่าง deterministic

ตัวอย่าง:

1
2
3
...

ห้ามให้ LLM generate numbering เอง


ห้ามเปลี่ยนโครงสร้าง table เพื่อเพิ่ม numbering


==================================================
28. RETRIEVAL MANAGER
==================================================

ปรับ Retrieval Manager ให้รองรับ semantic field request

ตัวอย่าง Data Request:

{
  "personId": "...",
  "fields": [
    "academic_position",
    "full_name",
    "highest_education_level",
    "degree_name",
    "education_field",
    "education_all_levels",
    "academic_work_counts"
  ]
}


Retrieval Manager ต้อง process ทีละ field


Pseudo logic:

for field in requested_fields:

    chroma_result = search_chroma(field)

    if evidence_supports_field(chroma_result, field):
        result[field] = chroma_result
        result[field].source = "chroma"
        continue

    mongo_result = query_mongodb(field)

    if evidence_supports_field(mongo_result, field):
        result[field] = mongo_result
        result[field].source = "mongodb"
        continue

    document_result = retrieve_document_ocr(field)

    if evidence_supports_field(document_result, field):
        result[field] = document_result
        result[field].source = "document_ocr"
        continue

    result[field] = {
        "status": "missing"
    }


==================================================
29. CHROMA COLLECTION
==================================================

Real Chroma collection:

document_chunks

metadata ใช้ camelCase:

documentType
documentId
curriculumId
page
chunkIndex

Generator ต้องรองรับ metadata จริงนี้

common/chroma.py มี mapping สำหรับ:

documentId → document_id
chunkIndex → chunk_index

ห้ามสร้าง schema metadata ใหม่โดยไม่จำเป็น


==================================================
30. EMBEDDING MODEL
==================================================

Import และ Generate ต้องใช้ embedding model เดียวกัน

ปัจจุบัน Chroma ใช้:

BAAI/bge-m3

dimension:

1024

ห้าม Generator ใช้:

gemini-embedding-001

สำหรับ collection นี้

เพราะจะเกิด dimension mismatch:

expected 1024
got 3072


ต้องรักษา BGE-M3 1024 สำหรับ Chroma search


==================================================
31. MONGODB
==================================================

Real database:

aunqa_ps

collections ที่เกี่ยวข้อง:

persons
educations
appointments
academic_works
documents
ps_requirements
data_usages
generated_documents


อย่าเปลี่ยน source DB schema


==================================================
32. CANONICAL PERSON AGGREGATION
==================================================

สร้าง reusable deterministic function เช่น:

aggregate_curriculum_people()

หน้าที่:

1. อ่าน appointments
2. group by personId
3. merge roles
4. attach person record
5. attach education records
6. attach work records
7. sort multi-role first
8. sort remaining records deterministically


Conceptual output:

[
  {
    "personId": "...",
    "person": {...},
    "roles": [
      "programmeResponsible",
      "programmeStaff"
    ],
    "education": [...],
    "academicWorks": [...]
  }
]


Table 1.1 และ Table 1.2 ต้องใช้ object ชุดนี้ร่วมกัน


==================================================
33. DETERMINISTIC SORT
==================================================

Primary sort:

len(roles) descending

Secondary sort:
ใช้ deterministic person order ที่สอดคล้องกับ appointment/template requirement

ห้าม sort แบบ random

ห้ามให้ LLM เป็นผู้เรียง


==================================================
34. DO NOT MODIFY SOURCE DATA
==================================================

ห้ามแก้:

persons
educations
appointments
academic_works

เพื่อให้ output ดูถูกต้อง

ถ้า source data ผิด:
    แสดง source value ตามหลักฐาน
    หรือ mark missing/unsupported

ห้ามแก้ source DB จาก Generator


==================================================
35. TESTING REQUIREMENTS
==================================================

ก่อน Real E2E ต้องเพิ่ม unit/integration tests อย่างน้อย:


TEST 1:
person with Responsible + Staff

Expected:
one person
roles = both


TEST 2:
staff-only person

Expected:
one person
roles = staff only


TEST 3:
Table 1.1 ordering

Expected:
multi-role people first
staff-only after


TEST 4:
Table 1.2 checkbox

Responsible + Staff:
both checked

Staff only:
staff checked only


TEST 5:
highest education level

Input:
ปร.ด.

Expected semantic output:
ปริญญาเอก

แต่ต้องเกิดจาก evidence/semantic mapping
ไม่ใช่ arbitrary LLM expansion


TEST 6:
highest education must not output degree name

Input:
ปรัชญาดุษฎีบัณฑิต

Expected:
highest_education_level = ปริญญาเอก

degree_name = ปรัชญาดุษฎีบัณฑิต


TEST 7:
name duplication

Input:
fullName = "ผศ. ดร. X Y"
firstName = "X"
lastName = "Y"

Expected:
name = "X Y"

ไม่ใช่:
"ผศ. ผศ. ดร. X Y"


TEST 8:
year normalization

2022 → 2565
2565 → 2565


TEST 9:
academic work count

2 academic works
1 creative work

Expected:
academic_count = 2
creative_count = 1


TEST 10:
graduationYear must not be used as publicationYear


TEST 11:
Chroma first

Mock:
Chroma has sufficient evidence
Mongo also has data

Expected:
source = Chroma


TEST 12:
Mongo fallback

Mock:
Chroma returns irrelevant/insufficient evidence
Mongo has valid data

Expected:
source = MongoDB


TEST 13:
per-field fallback

highest_education_level:
    Chroma found

degree_name:
    Chroma missing
    Mongo found

Expected:

highest_education_level.source = chroma
degree_name.source = mongodb


TEST 14:
Chroma result without relevant evidence

Chroma returns chunks
but chunks do not contain requested field

Expected:
NOT considered found
fallback MongoDB


TEST 15:
template has more blocks than records

Expected:
fill existing records
leave remaining template blocks untouched

Do not clone rows


TEST 16:
records > template blocks

Expected:
InjectionError


==================================================
36. DEBUG / AUDIT MODE
==================================================

เพิ่ม diagnostic logging โดยไม่ log sensitive information unnecessarily

สำหรับแต่ละ person และ field ให้เห็น:

personId
field
Chroma status
Chroma evidence found?
Mongo fallback?
final source
final value
source reference


ตัวอย่าง:

personId=123
field=highest_education_level

Chroma:
  searched=true
  evidence_sufficient=false

Mongo:
  queried=true
  found=true

Final:
  value="ปริญญาเอก"
  source="mongodb"


อีกตัวอย่าง:

personId=456
field=highest_education_level

Chroma:
  searched=true
  evidence_sufficient=true

Mongo:
  not_called

Final:
  value="ปริญญาโท"
  source="chroma"


เพื่อยืนยันว่า retrieval order ทำงานจริง


==================================================
37. IMPORTANT — อย่าแก้ด้วยการ Hardcode
==================================================

ห้ามแก้ปัญหาด้วย:

if personName == "...":
    value = "..."

ห้าม hardcode:

ชื่อ
ตำแหน่ง
วุฒิ
ปี
จำนวนผลงาน
checkbox

ข้อมูลทั้งหมดต้องมาจาก retrieval/source data


==================================================
38. IMPORTANT — อย่าแก้ด้วย Prompt อย่างเดียว
==================================================

ปัญหาเหล่านี้เป็น deterministic mapping/data aggregation problems

ห้ามแก้โดยเพิ่ม instruction ให้ LLM เพียงอย่างเดียว

ต้องแก้ที่ code/business logic สำหรับ:

- person aggregation
- role merging
- sorting
- field mapping
- education mapping
- year normalization
- work aggregation
- count calculation
- checkbox mapping
- source fallback


==================================================
39. FILES TO INSPECT BEFORE CODING
==================================================

ตรวจสอบ code จริงก่อนแก้:

master_agent/
criterion_agents/
retrieval/
common/
template/
verification/
reference/
injection/

โดยเฉพาะ:

- Retrieval Manager
- MCP tools
- Chroma search
- Mongo retrieval
- PS Agent
- template parser
- template injector
- table group injection
- Result JSON schema
- Slot marking
- traceability


อย่าเขียน implementation ใหม่ทั้งระบบ

ให้แก้เฉพาะส่วนที่เกี่ยวข้องกับปัญหาจริง


==================================================
40. BEFORE MODIFYING CODE — PERFORM DATA AUDIT
==================================================

ก่อนแก้ mapping ให้ตรวจข้อมูลจริงอย่างน้อย 3 คน

สำหรับแต่ละคนให้เปรียบเทียบ:

1. Mongo persons
2. Mongo appointments
3. Mongo educations
4. Mongo academic_works
5. Raw Chroma search results
6. PS Agent Data Request
7. PS Agent Result JSON
8. Final injected DOCX


ต้องตอบให้ได้ว่าแต่ละปัญหาเกิดที่ layer ไหน:

Retrieval
หรือ
Agent mapping
หรือ
Aggregation
หรือ
Injection


ห้ามเดาว่า Chroma ผิดหรือ Mongo ผิดโดยยังไม่ได้ตรวจ


==================================================
41. ACCEPTANCE CRITERIA
==================================================

หลังแก้เสร็จต้องได้ทั้งหมด:

[ ] Readiness ใช้ Monitor generatedReady เท่านั้น

[ ] Generate ไม่คำนวณ readiness เอง

[ ] Chroma ถูกเรียกก่อน Mongo

[ ] Mongo ถูกเรียกเมื่อ Chroma ไม่มี evidence เพียงพอ

[ ] Fallback ทำราย Field

[ ] Source reference ถูกต้อง

[ ] personId เป็น identity key

[ ] duplicate person ถูก merge

[ ] Responsible + Staff เป็น person เดียว

[ ] multi-role people มาก่อน staff-only

[ ] Table 1.1 และ 1.2 ใช้ canonical person ordering เดียวกัน

[ ] academicPosition มาจาก academicPosition

[ ] name มาจาก firstName + lastName

[ ] ไม่มี academic title ซ้ำ

[ ] highest_education_level หมายถึงระดับการศึกษา

[ ] highest_education_level ไม่ใช่ degree name

[ ] degree_name แยกจาก highest_education_level

[ ] education all levels ไม่ blank ถ้ามี source

[ ] graduationYear ไม่ถูกใช้แทน publicationYear

[ ] work count เป็น integer

[ ] academic count ถูกต้อง

[ ] creative count ถูกต้อง

[ ] publication year ถูก normalize อย่าง deterministic

[ ] พ.ศ. แสดงถูกต้อง

[ ] checkbox สะท้อน merged roles

[ ] ไม่มีการ clone template row

[ ] records > template blocks ทำให้ injection fail

[ ] records < template blocks ไม่สร้าง row ใหม่

[ ] Source DB ไม่ถูกแก้

[ ] User Edit ไม่ถูกใช้เป็น Source Data

[ ] Generate ใหม่อ่าน Source Data ใหม่

[ ] Real Chroma collection = document_chunks

[ ] Chroma embedding = BGE-M3 1024

[ ] ไม่มี Gemini 3072 embedding สำหรับ collection นี้

[ ] Unit tests ผ่าน

[ ] Integration tests ผ่าน

[ ] Real E2E ผ่าน


==================================================
42. FINAL REAL E2E
==================================================

หลัง tests ผ่านแล้วค่อยรัน Real E2E

ห้าม hardcode template version

ทุก Generate ต้อง query:

template_ps

ด้วย:

find_one({}, sort=[("version", -1)])

แล้ว download latest version ผ่าน Template Service


ห้าม cache template version/content


Real E2E ต้องตรวจ:

1. Monitor readiness
2. latest template version
3. template download
4. template parsing
5. slot marking
6. Chroma retrieval
7. Mongo fallback
8. person aggregation
9. PS Agent
10. Verification
11. Reference Mapping
12. Table 1.1 injection
13. Table 1.2 injection
14. Traceability
15. DOCX save
16. generated_documents
17. HTML preview


==================================================
43. FINAL REPORT
==================================================

หลังทำงานเสร็จ ให้รายงาน:

A. Root Cause
ระบุปัญหาแต่ละข้อว่าเกิดจาก layer ไหน

B. Files Changed
รายชื่อไฟล์ที่แก้

C. Logic Changed
อธิบาย logic ใหม่

D. Retrieval Audit
แสดงตัวอย่างว่า:

Chroma → ใช้
Chroma → insufficient → Mongo fallback

E. Person Aggregation
แสดงจำนวน:

unique persons
multi-role persons
staff-only persons

F. Table 1.1
ตรวจ:

academic position
name
highest education
degree + field
numbering

G. Table 1.2
ตรวจ:

checkbox
education all levels
year range
academic count
creative count

H. Tests
แสดงจำนวน PASS/FAIL

I. Real E2E
แสดงผลแต่ละ stage

J. Generated Document
ยืนยันว่า generated_documents ถูกบันทึกหลัง DOCX save สำเร็จเท่านั้น


ห้ามบอกว่า "ผ่าน" หากยังไม่ได้รัน test จริง
ห้ามสมมติผลลัพธ์
ห้ามซ่อน failure