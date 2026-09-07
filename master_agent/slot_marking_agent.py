"""SAR Template Slot Marking Agent (addfeature.md).

Automates what used to be a manual step: analyzes the whole SAR Template's
Document Structure JSON (paragraphs + tables, see template_structure.py),
decides where each criterion's narrative/table slots belong, and returns
target_type/target_index references the code below resolves directly to the
real Paragraph/Table objects in memory - no {{slot_id}} text round-trip
needed. Runs once, before the Criteria Processing Loop, per mainpromt.md's
Initialization step.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from docx.document import Document as DocumentObject
from docx.table import Table
from docx.text.paragraph import Paragraph
from pydantic import ValidationError

from common.gemini import generate_json
from common.schemas import SlotMark, SlotMarkingResult
from master_agent.docx_utils import (
    TableLayout,
    analyze_table_groups,
    extract_checkbox_options,
    find_header_row_index,
    group_into_records,
    logical_header_texts,
)

SYSTEM_PROMPT = """\
คุณคือ "SAR Template Slot Marking Agent" ผู้เชี่ยวชาญด้านการวิเคราะห์โครงสร้างเอกสาร Word \
รายงานประเมินตนเอง (SAR) ตามเกณฑ์ AUN-QA

หน้าที่: วิเคราะห์โครงสร้างเอกสาร SAR Template จาก Document Structure JSON ที่แปลงมาจาก python-docx \
และระบุตำแหน่งเป้าหมายที่ต้องเติมข้อมูล โดยระบุ target_index เพื่อให้โค้ด Python นำไปฉีดแท็ก \
{{slot_id}} หรือผูก Table Object ใน RAM ได้อย่างแม่นยำ สำหรับทุกเกณฑ์ที่ระบุใน [CRITERIA_CONFIG] \
ก่อนเริ่ม Criteria Processing Loop

[CRITERIA_CONFIG] แต่ละเกณฑ์มี guideline (กฎ/ข้อกำหนดของเกณฑ์นั้น), keywords, และ required_evidence - \
ใช้ข้อมูลเหล่านี้เพื่อทำความเข้าใจว่าเกณฑ์นั้นต้องการข้อมูลประเภทใด แต่ **Document Structure จาก \
Template จริงเท่านั้นที่เป็น Source of Truth สำหรับตำแหน่ง p_index/table_index** - guideline ไม่มีสิทธิ์ \
กำหนดตำแหน่งเอง ถ้าไม่พบตำแหน่งที่เหมาะสมในเอกสารจริง ให้ไม่ต้องสร้าง slot สำหรับเกณฑ์นั้น

อินพุตที่ได้รับ (ดูใน [DOCUMENT_STRUCTURE]):
- paragraphs: [{"p_index": 0, "text": "...", "is_heading": true/false, "is_empty": true/false}, ...]
- tables: [{"table_index": 0, "preceding_p_index": 3, "headers": [...], "sample_row": [...]}, ...]

กฎการระบุตำแหน่ง Slot:
1. Narrative slot: ค้นหา p_index ที่เป็นย่อหน้าว่าง (is_empty: true) ที่อยู่ใต้ heading ของเกณฑ์นั้น \
(ใช้ preceding context จากลำดับ p_index ก่อนหน้าเพื่อดูว่าอยู่ในหัวข้อไหน) กำหนด slot_id \
(เช่น intro_ps, desc_p1, eval_p3) และ target_type: "paragraph", target_index: ค่า p_index นั้น
2. Table slot: ตรวจ headers และ sample_row ของแต่ละ table_index หากเป็น "ตารางข้อมูลจริง" ที่ต้องกรอก \
(เช่น ตารางรายชื่อ, ตารางคุณวุฒิ, ตาราง ELO Mapping, ตารางผลงานวิชาการ) กำหนด slot_id \
(เช่น table_ps_1_1, table_p1_elo) และ target_type: "table", target_index: ค่า table_index นั้น
3. ห้ามระบุ table slot สำหรับตารางที่เป็นเกณฑ์ประเมินคงที่ (checklist), ตาราง checkbox มาตรฐาน, หรือ \
ตารางสรุปคะแนนคงที่ - สังเกตจาก headers/sample_row ที่เป็นข้อความเกณฑ์/checkbox ซ้ำ ๆ แทนที่จะเป็น \
ช่องว่างรอกรอกข้อมูลจริง
4. แต่ละเกณฑ์ควรมีอย่างน้อย 1 slot หากพบตำแหน่งที่เกี่ยวข้องในเอกสาร แต่ถ้าเอกสารไม่มีส่วนของเกณฑ์นั้นเลย \
ก็ไม่ต้องสร้าง slot ให้เกณฑ์นั้น (ห้ามสร้าง slot ที่ไม่มีอยู่จริงในเอกสาร)
5. slot_id ต้องไม่ซ้ำกันภายในเอกสาร

ตอบกลับเป็น JSON ตาม schema นี้เท่านั้น ห้ามมีข้อความอื่นนอก JSON:
{
  "status": "success",
  "total_slots_marked": 0,
  "marked_slots": [
    {
      "criterion": "PS",
      "slot_id": "intro_ps",
      "type": "narrative",
      "target_type": "paragraph",
      "target_index": 5,
      "location_heading": "2.1 PS การบริหารหลักสูตรตามเกณฑ์มาตรฐาน..."
    },
    {
      "criterion": "PS",
      "slot_id": "table_ps_1_1",
      "type": "table",
      "target_type": "table",
      "target_index": 0,
      "location_heading": "1.1 ข้อมูลอาจารย์ผู้รับผิดชอบหลักสูตร...",
      "table_headers": ["ตำแหน่งทางวิชาการ", "ชื่อ-นามสกุล", "วุฒิการศึกษาสูงสุด", "ชื่อปริญญา (สาขาวิชา)"]
    }
  ]
}
"""


def build_prompt(structure: dict, criteria_meta: dict, example_structure: dict | None) -> str:
    criteria_config = [
        {
            "criterion": code,
            "name": meta["name"],
            "guideline": meta["guideline"],
            "keywords": meta["keywords"],
            "required_evidence": meta["required_evidence"],
        }
        for code, meta in criteria_meta.items()
    ]

    prompt = f"""[CRITERIA_CONFIG]
{json.dumps(criteria_config, ensure_ascii=False, indent=2)}

[DOCUMENT_STRUCTURE]
{json.dumps(structure, ensure_ascii=False, indent=2)}
"""

    if example_structure:
        prompt += f"""
[EXAMPLE_STRUCTURE]
(โครงสร้างรายงานปีก่อนหน้า ใช้ดูตำแหน่งของเนื้อหาบรรยายและตารางข้อมูลจริงเท่านั้น ห้ามใช้เป็นข้อเท็จจริง)
{json.dumps(example_structure, ensure_ascii=False, indent=2)}
"""

    return prompt


class SlotMarkingError(Exception):
    pass


def run_slot_marking_agent(
    structure: dict,
    criteria_meta: dict,
    example_structure: dict | None = None,
) -> SlotMarkingResult:
    prompt = build_prompt(structure, criteria_meta, example_structure)
    raw = generate_json(f"{SYSTEM_PROMPT}\n\n{prompt}")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SlotMarkingError(f"Slot Marking Agent did not return valid JSON: {exc}") from exc

    try:
        return SlotMarkingResult.model_validate(data)
    except ValidationError as exc:
        raise SlotMarkingError(f"Slot Marking Agent JSON did not match the required schema: {exc}") from exc


@dataclass
class ResolvedSlot:
    criterion: str
    slot_id: str
    type: str  # "narrative" | "table"
    headers: list[str] | None = None
    paragraph: Paragraph | None = None  # narrative: the paragraph to write content into
    table: Table | None = None  # table: the table to add rows to
    marker_paragraph: Paragraph | None = None  # table: cleared after injection
    layout: TableLayout | None = None  # table: groups/placeholder rows, see docx_utils.analyze_table_groups
    rows_per_record: int | None = None  # table: >1 when each logical record spans several physical rows
    checkbox_options: list[str] | None = None  # table: category options embedded in a block's own placeholder label


def _insert_paragraph_after(document: DocumentObject, after_paragraph: Paragraph) -> Paragraph:
    new_paragraph = document.add_paragraph()
    after_paragraph._p.addnext(new_paragraph._p)
    return new_paragraph


def _insert_paragraph_before_table(document: DocumentObject, table: Table) -> Paragraph:
    new_paragraph = document.add_paragraph()
    table._tbl.addprevious(new_paragraph._p)
    return new_paragraph


def apply_marks(document: DocumentObject, structure: dict, marks: list[SlotMark]) -> dict[str, ResolvedSlot]:
    """Resolves each mark's target_type/target_index against a snapshot of
    document.paragraphs/document.tables taken *before* any insertion, so that
    inserting a paragraph for one mark can't shift the indices another mark
    is still relying on. Returns slot_id -> ResolvedSlot for direct use by
    the Criteria Processing Loop and template_injector.py - no {{slot_id}}
    text re-scan required.
    """
    paragraphs = document.paragraphs
    tables = document.tables

    resolved: dict[str, ResolvedSlot] = {}
    for mark in marks:
        if mark.slot_id in resolved:
            continue

        if mark.target_type == "paragraph":
            if not (0 <= mark.target_index < len(paragraphs)):
                continue
            anchor = paragraphs[mark.target_index]
            target_paragraph = anchor if anchor.text.strip() == "" else _insert_paragraph_after(document, anchor)
            target_paragraph.text = "{{" + mark.slot_id + "}}"
            resolved[mark.slot_id] = ResolvedSlot(
                criterion=mark.criterion, slot_id=mark.slot_id, type="narrative", paragraph=target_paragraph
            )
        else:
            if not (0 <= mark.target_index < len(tables)):
                continue
            table = tables[mark.target_index]

            # Deterministic (Python-side, not LLM-side) structural guard: a
            # table only gets targeted for structured injection if at least
            # one row's column layout actually matches its own header's -
            # i.e. it has real placeholder rows to fill. Tables that don't
            # fit this shape (e.g. a multi-row header, or one record spanning
            # several physical rows) are skipped here regardless of what the
            # Slot Marking Agent's prompt-only judgment proposed, so an
            # unsupported table shape can never be silently corrupted by
            # template_injector.py - see docx_utils.analyze_table_groups.
            layout = analyze_table_groups(table)
            if not layout.has_placeholders:
                print(
                    f"table slot '{mark.slot_id}' skipped - no placeholder rows detected "
                    f"in table_index={mark.target_index} (unsupported table shape)"
                )
                continue

            # Merge-deduplicated headers (see docx_utils.logical_columns) -
            # a raw row.cells read would double-count a horizontally-merged
            # header and mislead the Criteria Agent about the real column
            # count. Uses find_header_row_index rather than assuming row 0,
            # since some tables have a decorative supra-header row above the
            # real one (see docx_utils.find_header_row_index).
            header_row = table.rows[find_header_row_index(table)] if table.rows else None
            headers = logical_header_texts(header_row) if header_row is not None else []

            # rows_per_record > 1 when this table needs several physical rows
            # per logical record (e.g. one row per academic year for the same
            # instructor) rather than one row per record. Only set when every
            # group's records agree on the same size - an ambiguous/mixed
            # shape falls back to today's one-row-per-record behavior (None)
            # rather than guessing at a block size that might be wrong.
            all_records = [r for g in layout.groups for r in group_into_records(g.rows)]
            record_sizes = {len(r.rows) for r in all_records}
            rows_per_record = record_sizes.pop() if len(record_sizes) == 1 else None
            if rows_per_record is not None and rows_per_record <= 1:
                rows_per_record = None

            # A block-shaped record's own raw placeholder label may embed a
            # checkbox-style category choice (e.g. "14.\n[ ] อาจารย์ประจำหลักสูตร\n
            # [ ] อาจารย์ผู้รับผิดชอบหลักสูตร") rather than a position-based
            # subheader divider like Table 1.1's groups - extracted once here
            # so the Criteria Agent can be told the valid options (via
            # TargetSlot.groups, in master.py) and template_injector.py can
            # render the right checkbox mark per record.
            checkbox_options = None
            if rows_per_record and all_records:
                checkbox_options = extract_checkbox_options(all_records[0].label) or None

            marker_paragraph = _insert_paragraph_before_table(document, table)
            marker_paragraph.text = "{{table:" + mark.slot_id + "}}"
            resolved[mark.slot_id] = ResolvedSlot(
                criterion=mark.criterion,
                slot_id=mark.slot_id,
                type="table",
                headers=headers,
                table=table,
                marker_paragraph=marker_paragraph,
                layout=layout,
                rows_per_record=rows_per_record,
                checkbox_options=checkbox_options,
            )

    return resolved
