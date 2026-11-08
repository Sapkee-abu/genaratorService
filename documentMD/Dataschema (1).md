

# Data Schema — PS System

## 1. `curricula`

**เก็บข้อมูลหลักสูตร**

```javascript
{
  "_id": ObjectId(),
  "curriculumCode": "25500231104894",
  "curriculumName": "วิทยาศาสตรบัณฑิต สาขาเทคโนโลยีสารสนเทศอัจฉริยะ",
  "curriculumYear": 2567,
  "version": 1,
  "status": "latest",

  "timestamp": ISODate("2026-09-16T08:00:00Z")
}
```

`timestamp` = เวลาที่ข้อมูลหลักสูตร Record นี้ถูกบันทึกหรืออัปเดตล่าสุด

---

## 2. `persons`

**เก็บข้อมูลอาจารย์/บุคคล**

```javascript
{
  "_id": ObjectId(),
  "title": "ผศ.ดร.",
  "firstName": "สุภาภรณ์",
  "lastName": "ใจรังษี",
  "fullName": "ผศ.ดร.สุภาภรณ์ ใจรังษี",
  "academicPosition": "ผู้ช่วยศาสตราจารย์",

  "timestamp": ISODate("2026-09-16T08:00:00Z")
}
```

**หน้าที่:** เก็บข้อมูลตัวบุคคล

> `role` ยังคงไม่อยู่ใน `persons` เพราะบทบาทของอาจารย์อยู่ใน `appointments` ตามโครงสร้างเดิม

---

## 3. `educations`

**เก็บข้อมูลคุณวุฒิของอาจารย์**

```javascript
{
  "_id": ObjectId(),
  "personId": ObjectId(),
  "degree": "Ph.D.",
  "field": "Informatics",
  "institution": "King's College London",
  "graduationYear": 2555,

  "timestamp": ISODate("2026-09-16T08:00:00Z")
}
```

ความสัมพันธ์:

```text
persons 1 ───────── * educations
                     ↑
                  personId
```

ดังนั้นอาจารย์ 1 คนมีหลายวุฒิได้ และ **แต่ละวุฒิมี `timestamp` ของ Record ตัวเอง**

---

## 4. `appointments`

**เก็บข้อมูลการแต่งตั้งและบทบาทของอาจารย์ในหลักสูตร**

### อาจารย์ผู้รับผิดชอบหลักสูตร

```javascript
{
  "_id": ObjectId(),

  "curriculumId": ObjectId(),
  "personId": ObjectId(),

  "role": "programmeResponsible",
  "roleName": "อาจารย์ผู้รับผิดชอบหลักสูตร",

  "effectiveDate": "2567-11-13",

  "appointmentOrder": {
    "orderNumber": "350/2568",
    "orderDate": "2568-02-04"
  },

  "status": "active",

  "timestamp": ISODate("2026-09-16T08:00:00Z")
}
```

### อาจารย์ประจำหลักสูตร

```javascript
{
  "_id": ObjectId(),

  "curriculumId": ObjectId(),
  "personId": ObjectId(),

  "role": "programmeStaff",
  "roleName": "อาจารย์ประจำหลักสูตร",

  "effectiveDate": "2567-11-13",

  "appointmentOrder": {
    "orderNumber": "350/2568",
    "orderDate": "2568-02-04"
  },

  "status": "active",

  "timestamp": ISODate("2026-09-16T08:00:00Z")
}
```

ความสัมพันธ์:

```text
curricula 1 ───── * appointments * ───── 1 persons
```

`timestamp` ของแต่ละ Appointment เปลี่ยนเมื่อข้อมูลการแต่งตั้ง Record นั้นถูกอัปเดต

---

## 5. `academic_works`

**เก็บผลงานทางวิชาการ**

```javascript
{
  "_id": ObjectId(),

  "personId": ObjectId(),

  "workType": "journalArticle",
  "title": "A sequential deep learning framework for proactive fault detection in Multi-Unit HVAC systems",

  "publicationYear": 2569,

  "database": "Scopus",
  "quartile": "Q1",

  "timestamp": ISODate("2026-09-16T08:00:00Z")
}
```

ความสัมพันธ์:

```text
persons 1 ───────── * academic_works
                     ↑
                  personId
```

ถ้าอาจารย์หนึ่งคนมี 5 ผลงาน จะมี 5 Records และ **แต่ละผลงานมี `timestamp` ของตัวเอง**

```text
Person A
│
├── Work 1 → timestamp
├── Work 2 → timestamp
├── Work 3 → timestamp
├── Work 4 → timestamp
└── Work 5 → timestamp
```

---

# 6. `documents`

**เก็บข้อมูลเอกสาร Import + ไฟล์แปลง/Extract**

ยังคงใช้ **Local Storage บน Server**

```javascript
{
  "_id": ObjectId(),

  "documentType": "curriculum",
  "fileType": "pdf",
  "fileName": "มคอ2-IIT70.pdf",

  "curriculumId": ObjectId(),

  "originalFile": {
    "storage": "local",
    "path": "project-data/documents/original/curriculum/มคอ2-IIT70.pdf"
  },

  "convertedFile": {
    "storage": "local",
    "path": "project-data/documents/converted/curriculum/มคอ2-IIT70.docx"
  },

  "extractedText": {
    "storage": "local",
    "path": "project-data/documents/extracted/curriculum/มคอ2-IIT70.txt"
  },

  "status": "processed",

  "timestamp": ISODate("2026-09-16T08:00:00Z")
}
```

`timestamp` = เวลาที่ข้อมูลเอกสาร Record นี้ถูกบันทึกหรืออัปเดตล่าสุด

Local Storage:

```text
project-data/
└── documents/
    ├── original/
    │   ├── curriculum/
    │   ├── cv/
    │   └── appointment/
    │
    ├── converted/
    ├── extracted/
    │
    └── generated/       ← เพิ่มใหม่
```

ยังคงใช้ **Relative Path** ตาม Requirement เดิม

---

## 7. `ps_requirements`

**เก็บเกณฑ์ PS-01 ถึง PS-09 + Configuration**

```javascript
{
  "generationReadiness": {
    "requiredPS": [
      "PS-01",
      "PS-02",
      "PS-03",
      "PS-04",
      "PS-05",
      "PS-06",
      "PS-07",
      "PS-08",
      "PS-09"
    ],
    "readyWhen": {
      "allowedStatus": [
        "PASS",
        "N/A"
      ],
      "blockedStatus": [
        "FAIL",
        "REVIEW"
      ]
    },
    "requiredAll": true
  },
  "psConfigurations": [
    {
      "psCode": "PS-01",
      "requirement": "หลักสูตรต้องมีอาจารย์ผู้รับผิดชอบหลักสูตรอย่างน้อย 5 คน",
      "config": {
        "targetCollection": "appointments",
        "filter": {
          "role": "programmeResponsible"
        },
        "count": {
          "field": "personId",
          "distinct": true
        },
        "condition": {
          "operator": ">=",
          "value": 5
        },
        "result": {
          "pass": "PASS",
          "fail": "FAIL",
          "review": "REVIEW",
          "na": "N/A"
        },
        "reviewCondition": [
          "จำนวนข้อมูลไม่ชัดเจน"
        ],
        "naEnabled": false
      },
      "active": true
    },
    {
      "psCode": "PS-02",
      "requirement": "อาจารย์ผู้รับผิดชอบหลักสูตรต้องมีสถานะอาจารย์ประจำ",
      "config": {
        "targetCollection": "appointments",
        "responsibleRole": "programmeResponsible",
        "permanentRole": "programmeStaff",
        "matching": {
          "sameCurriculum": true,
          "samePerson": true
        },
        "condition": {
          "operator": "EXISTS",
          "field": "programmeStaff"
        },
        "result": {
          "pass": "PASS",
          "fail": "FAIL",
          "review": "REVIEW",
          "na": "N/A"
        },
        "reviewCondition": [
          "ไม่สามารถตรวจสอบสถานะอาจารย์ประจำได้"
        ],
        "naEnabled": false
      },
      "active": true
    },
    {
      "psCode": "PS-03",
      "requirement": "อาจารย์ผู้รับผิดชอบหลักสูตรต้องไม่รับผิดชอบเกิน 1 หลักสูตร",
      "config": {
        "targetCollection": "appointments",
        "targetRole": "programmeResponsible",
        "review": {
          "required": true,
          "reviewByUser": true,
          "allowManualResult": [
            "PASS",
            "FAIL",
            "REVIEW"
          ]
        },
        "result": {
          "pass": "PASS",
          "fail": "FAIL",
          "review": "REVIEW",
          "na": "N/A"
        },
        "naEnabled": false
      },
      "active": true
    },
    {
      "psCode": "PS-04",
      "requirement": "หลักสูตรต้องมีคำสั่งแต่งตั้งและระบุบทบาทการบริหารหลักสูตรอย่างชัดเจน",
      "config": {
        "targetCollection": "appointments",
        "requiredFields": [
          "personId",
          "role",
          "roleName",
          "appointmentOrder"
        ],
        "appointmentOrder": {
          "required": true,
          "requiredFields": [
            "orderNumber",
            "orderDate"
          ]
        },
        "role": {
          "required": true,
          "roleNameRequired": true
        },
        "result": {
          "pass": "PASS",
          "fail": "FAIL",
          "review": "REVIEW",
          "na": "N/A"
        },
        "conditions": {
          "pass": "ข้อมูลการแต่งตั้งครบและระบุบทบาทชัดเจน",
          "fail": "ไม่มีคำสั่งแต่งตั้งหรือข้อมูลไม่ครบ",
          "review": "มีข้อมูลแต่ไม่สามารถระบุความครบถ้วนหรือความชัดเจนได้"
        },
        "naEnabled": false
      },
      "active": true
    },
    {
      "psCode": "PS-05",
      "requirement": "อาจารย์ผู้รับผิดชอบหลักสูตรต้องมีคุณวุฒิสูงสุดอย่างน้อยระดับปริญญาโท",
      "config": {
        "targetCollection": "educations",
        "appointment": {
          "role": "programmeResponsible"
        },
        "join": {
          "from": "appointments.personId",
          "to": "educations.personId"
        },
        "degree": {
          "field": "degree",
          "minimum": "master",
          "ordering": [
            "bachelor",
            "master",
            "Ph.D."
          ]
        },
        "result": {
          "pass": "PASS",
          "fail": "FAIL",
          "review": "REVIEW",
          "na": "N/A"
        },
        "reviewCondition": [
          "ไม่สามารถระบุระดับคุณวุฒิได้"
        ],
        "naEnabled": false
      },
      "active": true
    },
    {
      "psCode": "PS-06",
      "requirement": "คุณวุฒิของอาจารย์สัมพันธ์กับสาขาของหลักสูตร",
      "config": {
        "targetCollection": "educations",
        "appointment": {
          "role": "programmeResponsible"
        },
        "join": {
          "appointmentPersonId": "appointments.personId",
          "educationPersonId": "educations.personId",
          "curriculumId": "appointments.curriculumId"
        },
        "programmeField": {
          "source": "curricula.curriculumName",
          "method": "extract"
        },
        "qualificationField": {
          "source": "educations.field"
        },
        "normalization": {
          "enabled": true,
          "remove": [
            "สาขาวิชา",
            "สาขา",
            "หลักสูตร",
            "วิชา",
            " ",
            "-"
          ],
          "caseInsensitive": true
        },
        "comparison": {
          "method": "mapping",
          "allowExactMatch": true,
          "allowRelatedMatch": true
        },
        "fieldMappings": [
          {
            "programmeField": "วิทยาการคอมพิวเตอร์",
            "aliases": [
              "วิทยาการคอมพิวเตอร์",
              "Computer Science",
              "Computing Science",
              "Computer Sciences",
              "Computing"
            ],
            "relatedFields": [
              "เทคโนโลยีสารสนเทศ",
              "สารสนเทศศาสตร์",
              "ระบบสารสนเทศ",
              "วิศวกรรมซอฟต์แวร์",
              "วิศวกรรมคอมพิวเตอร์",
              "เทคโนโลยีคอมพิวเตอร์",
              "เทคโนโลยีสารสนเทศและการสื่อสาร",
              "Information Technology",
              "Information Systems",
              "Information Science",
              "Software Engineering",
              "Computer Engineering",
              "Computer Technology",
              "Information and Communication Technology",
              "ICT"
            ]
          },
          {
            "programmeField": "เทคโนโลยีสารสนเทศ",
            "aliases": [
              "เทคโนโลยีสารสนเทศ",
              "Information Technology",
              "IT"
            ],
            "relatedFields": [
              "วิทยาการคอมพิวเตอร์",
              "วิทยาการสารสนเทศ",
              "สารสนเทศศาสตร์",
              "ระบบสารสนเทศ",
              "เทคโนโลยีสารสนเทศและการสื่อสาร",
              "เทคโนโลยีสารสนเทศและนวัตกรรม",
              "เทคโนโลยีดิจิทัล",
              "วิศวกรรมซอฟต์แวร์",
              "Information Science",
              "Information Systems",
              "Computer Science",
              "Information and Communication Technology",
              "Digital Technology",
              "Software Engineering"
            ]
          },
          {
            "programmeField": "สารสนเทศศาสตร์",
            "aliases": [
              "สารสนเทศศาสตร์",
              "วิทยาการสารสนเทศ",
              "Information Science",
              "Informatics"
            ],
            "relatedFields": [
              "เทคโนโลยีสารสนเทศ",
              "ระบบสารสนเทศ",
              "วิทยาการคอมพิวเตอร์",
              "เทคโนโลยีสารสนเทศและการสื่อสาร",
              "Information Technology",
              "Information Systems",
              "Computer Science",
              "Informatics",
              "Information and Communication Technology"
            ]
          },
          {
            "programmeField": "ระบบสารสนเทศ",
            "aliases": [
              "ระบบสารสนเทศ",
              "Information Systems",
              "Management Information Systems",
              "MIS"
            ],
            "relatedFields": [
              "เทคโนโลยีสารสนเทศ",
              "สารสนเทศศาสตร์",
              "วิทยาการสารสนเทศ",
              "วิทยาการคอมพิวเตอร์",
              "เทคโนโลยีสารสนเทศและการสื่อสาร",
              "Information Technology",
              "Information Science",
              "Informatics",
              "Computer Science",
              "Information and Communication Technology"
            ]
          },
          {
            "programmeField": "วิศวกรรมซอฟต์แวร์",
            "aliases": [
              "วิศวกรรมซอฟต์แวร์",
              "Software Engineering"
            ],
            "relatedFields": [
              "วิทยาการคอมพิวเตอร์",
              "เทคโนโลยีสารสนเทศ",
              "วิศวกรรมคอมพิวเตอร์",
              "เทคโนโลยีคอมพิวเตอร์",
              "Computer Science",
              "Information Technology",
              "Computer Engineering",
              "Computer Technology"
            ]
          },
          {
            "programmeField": "วิศวกรรมคอมพิวเตอร์",
            "aliases": [
              "วิศวกรรมคอมพิวเตอร์",
              "Computer Engineering"
            ],
            "relatedFields": [
              "วิทยาการคอมพิวเตอร์",
              "วิศวกรรมซอฟต์แวร์",
              "เทคโนโลยีสารสนเทศ",
              "เทคโนโลยีคอมพิวเตอร์",
              "Computer Science",
              "Software Engineering",
              "Information Technology",
              "Computer Technology"
            ]
          },
          {
            "programmeField": "เทคโนโลยีดิจิทัล",
            "aliases": [
              "เทคโนโลยีดิจิทัล",
              "Digital Technology",
              "Digital Technologies"
            ],
            "relatedFields": [
              "เทคโนโลยีสารสนเทศ",
              "วิทยาการคอมพิวเตอร์",
              "สารสนเทศศาสตร์",
              "วิทยาการสารสนเทศ",
              "ระบบสารสนเทศ",
              "เทคโนโลยีสารสนเทศและการสื่อสาร",
              "Information Technology",
              "Computer Science",
              "Information Science",
              "Information Systems",
              "Information and Communication Technology"
            ]
          },
          {
            "programmeField": "เทคโนโลยีสารสนเทศและการสื่อสาร",
            "aliases": [
              "เทคโนโลยีสารสนเทศและการสื่อสาร",
              "Information and Communication Technology",
              "Information Communication Technology",
              "ICT"
            ],
            "relatedFields": [
              "เทคโนโลยีสารสนเทศ",
              "วิทยาการคอมพิวเตอร์",
              "สารสนเทศศาสตร์",
              "วิทยาการสารสนเทศ",
              "ระบบสารสนเทศ",
              "เทคโนโลยีดิจิทัล",
              "Information Technology",
              "Computer Science",
              "Information Science",
              "Information Systems",
              "Digital Technology"
            ]
          }
        ],
        "result": {
          "exact": "PASS",
          "related": "PASS",
          "unrelated": "FAIL",
          "unknown": "REVIEW"
        },
        "reviewCondition": [
          "ไม่พบข้อมูล education.field",
          "ไม่สามารถระบุ programme field ได้",
          "ไม่มี Mapping สำหรับ programme field",
          "ไม่สามารถตัดสินความสัมพันธ์ได้"
        ],
        "naEnabled": false
      },
      "active": true
    },
    {
      "psCode": "PS-07",
      "requirement": "อาจารย์ผู้รับผิดชอบหรืออาจารย์ประจำหลักสูตรต้องมีผลงานวิชาการย้อนหลัง 5 ปี",
      "config": {
        "targetCollections": [
          "academic_works",
          "appointments"
        ],
        "targetRoles": [
          "programmeResponsible",
          "programmeStaff"
        ],
        "join": {
          "from": "appointments.personId",
          "to": "academic_works.personId"
        },
        "publicationYear": {
          "field": "publicationYear",
          "period": "previous5Years"
        },
        "minimumCount": 1,
        "result": {
          "pass": "PASS",
          "fail": "FAIL",
          "review": "REVIEW",
          "na": "N/A"
        },
        "reviewCondition": [
          "ไม่สามารถตรวจสอบ publicationYear ได้"
        ],
        "naEnabled": false
      },
      "active": true
    },
    {
      "psCode": "PS-08",
      "requirement": "อาจารย์พิเศษต้องมีคุณวุฒิและประสบการณ์ที่เหมาะสม",
      "config": {
        "targetCollection": "appointments",
        "targetRole": "specialInstructor",
        "join": {
          "appointmentPersonId": "appointments.personId",
          "educationPersonId": "educations.personId"
        },
        "qualification": {
          "source": "educations.degree",
          "required": true,
          "condition": {
            "operator": "EXISTS"
          }
        },
        "experience": {
          "required": true,
          "source": "persons.hasTeachingExperience",
          "condition": {
            "operator": "==",
            "value": true
          }
        },
        "result": {
          "pass": "PASS",
          "fail": "FAIL",
          "review": "REVIEW",
          "na": "N/A"
        },
        "conditions": {
          "noSpecialInstructor": "N/A",
          "qualifiedAndSuitable": "PASS",
          "notQualifiedOrNotSuitable": "FAIL",
          "insufficientInformation": "REVIEW"
        },
        "naEnabled": true
      },
      "active": true
    },
    {
      "psCode": "PS-09",
      "requirement": "หลักสูตรต้องมีการปรับปรุงล่าสุดไม่เกิน 5 ปี",
      "config": {
        "targetCollection": "curricula",
        "year": {
          "field": "curriculumYear"
        },
        "comparison": {
          "operator": "<=",
          "value": 5,
          "reference": "currentYear"
        },
        "calculation": {
          "formula": "currentYear - curriculumYear"
        },
        "result": {
          "pass": "PASS",
          "fail": "FAIL",
          "review": "REVIEW",
          "na": "N/A"
        },
        "reviewCondition": [
          "ไม่สามารถระบุ curriculumYear ได้"
        ],
        "naEnabled": false
      },
      "active": true
    }
  ]
}
```

ประกอบด้วย:

```text
PS-01
PS-02
PS-03
PS-04
PS-05
PS-06
PS-07
PS-08
PS-09
```

`timestamp` มีประโยชน์โดยเฉพาะกรณี Config ถูกแก้ เพราะระบบจะรู้ว่า Requirement/Config Record นั้นถูกอัปเดตล่าสุดเมื่อใด

---

## 8. `data_usages`

**เก็บ Mapping ว่าข้อมูลถูกนำไปใช้ตอบ PS และ Template ส่วนใด**

```javascript
{
  "_id": ObjectId(),

  "dataType": "education",
  "dataId": ObjectId(),

  "curriculumId": ObjectId(),

  "psCodes": [
    "PS-02",
    "PS-05",
    "PS-06"
  ],

  "roles": [
    "programmeResponsible"
  ],

  "templateFields": [
    "education"
  ],

  "timestamp": ISODate("2026-09-16T08:00:00Z")
}
```

`timestamp` = เวลาที่ Mapping Record นี้ถูกบันทึกหรืออัปเดตล่าสุด

---

# 9. `generated_documents` — Collection ใหม่

**เก็บเอกสาร PS ที่ระบบ Generate และเก็บไฟล์ Generate ก่อนหน้าทั้งหมด**

```javascript
{
  "_id": ObjectId(),

  "curriculumId": ObjectId(),

  "fileName": "PS-2569.md",
  "fileType": "md",

  "generatedFiles": [
    {
      "path": "project-data/documents/generated/PS-2569-v1.md",
      "timestamp": ISODate("2026-09-16T08:00:00Z")
    },
    {
      "path": "project-data/documents/generated/PS-2569-v2.md",
      "timestamp": ISODate("2026-09-16T09:30:00Z")
    },
    {
      "path": "project-data/documents/generated/PS-2569-v3.md",
      "timestamp": ISODate("2026-09-17T03:00:00Z")
    }
  ],

  "timestamp": ISODate("2026-09-17T03:00:00Z")
}
```

ตรงนี้มี **Timestamp 2 ระดับ** เพราะมีคนละหน้าที่:

```text
generated_documents
│
├── timestamp
│     └── เวลาที่ Record ของเอกสารนี้
│         ถูกอัปเดตล่าสุด
│
└── generatedFiles[]
      │
      ├── v1
      │    ├── path
      │    └── timestamp ← เวลา Generate v1
      │
      ├── v2
      │    ├── path
      │    └── timestamp ← เวลา Generate v2
      │
      └── v3
           ├── path
           └── timestamp ← เวลา Generate v3
```

ดังนั้นเมื่อ Generate ใหม่ **ไฟล์เก่าไม่ถูกลบหรือเขียนทับ**

```text
generated/
├── PS-2569-v1.md
├── PS-2569-v2.md
└── PS-2569-v3.md
```

---

# Relationship ฉบับล่าสุด

```text
                         curricula
                            │
              ┌─────────────┼────────────────┐
              │             │                │
              ▼             ▼                ▼
        appointments     documents    generated_documents
              │
              │ personId
              ▼
           persons
           │     │
           │     │
           ▼     ▼
     educations  academic_works


ps_requirements
       │
       ▼
   data_usages
       │
       └── dataId → ข้อมูลที่ใช้ตอบ PS
```

การเชื่อม ID:

```text
appointments.curriculumId  → curricula._id
appointments.personId      → persons._id

educations.personId        → persons._id

academic_works.personId    → persons._id

documents.curriculumId     → curricula._id

data_usages.curriculumId   → curricula._id

generated_documents.curriculumId
                            → curricula._id
```

# สรุป 9 Collections — Final Confirm

|  # | Collection            | ข้อมูล               |        `timestamp`        |
| -: | --------------------- | -------------------- | :-----------------------: |
|  1 | `curricula`           | หลักสูตร             |             ✓             |
|  2 | `persons`             | อาจารย์/บุคคล        |             ✓             |
|  3 | `educations`          | คุณวุฒิแต่ละรายการ   |             ✓             |
|  4 | `appointments`        | การแต่งตั้ง/บทบาท    |             ✓             |
|  5 | `academic_works`      | ผลงานแต่ละรายการ     |             ✓             |
|  6 | `documents`           | เอกสาร Import        |             ✓             |
|  7 | `ps_requirements`     | PS-01–PS-09 + Config |             ✓             |
|  8 | `data_usages`         | Mapping Data → PS    |             ✓             |
|  9 | `generated_documents` | เอกสารที่ Generate   | ✓ + Timestamp ต่อ Version |


