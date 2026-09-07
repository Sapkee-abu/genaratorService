# Guideline Backup

Real guideline text removed from `master_config.json` for testing (Evidence
for PS is incomplete — no official instructor-count / appointment-order
document yet, only individual CVs). Paste back into `criteria.PS.guideline`
in `master_config.json` once that Evidence is available (e.g. after the
มคอ.2 upload succeeds, or a standalone คำสั่งแต่งตั้ง document is uploaded).

## PS — Programme Specification

```json
"guideline": [
  "หลักสูตรระดับปริญญาตรี ต้องมีอาจารย์ผู้รับผิดชอบหลักสูตรไม่น้อยกว่า 5 คน",
  "ต้องเป็นอาจารย์ประจำหลักสูตรที่มีคุณวุฒิตรงหรือสัมพันธ์กับสาขาวิชาที่เปิดสอน",
  "เป็นอาจารย์ผู้รับผิดชอบหลักสูตรเกินกว่า 1 หลักสูตรในเวลาเดียวกันไม่ได้ (ยกเว้นหลักสูตรพหุวิทยาการ)",
  "ต้องได้รับการแต่งตั้งอย่างเป็นทางการตามคำสั่งของสถาบันอุดมศึกษา"
],
"required_evidence": [
  "มคอ.2 หมวดอาจารย์ผู้รับผิดชอบหลักสูตร",
  "คำสั่งแต่งตั้งอาจารย์ผู้รับผิดชอบหลักสูตร"
]
```
