"""Shared infrastructure for the six Criterion Agents (change.md sec.5:
PS/P1/P2/P3/P4/P8 must be separate Agents, each with its own agent.py,
Prompt, Logic and Schema - but the LLM call plumbing, the criterion-agnostic
part of the system prompt, and the Data Request default are identical
mechanics, not "criterion content", so they live here once instead of being
copy-pasted six times.

Moved out of the old master_agent/criteria_agent.py (which used to be the
one generic agent for every criterion - see change.md sec.20 Critical Check
A/B). Each criterion_agents/{code}_agent/agent.py is the one that actually
owns its own Prompt (prompt/system_prompt.txt, appended as `extra_rules`)
and Schema (schema/output_schema.json) - this module never decides
criterion-specific content, only the shared skeleton every agent renders it
into.
"""

from __future__ import annotations

import json

from pydantic import ValidationError

from common.config import get_settings
from common.gemini import generate_json
from common.schemas import AgentResponse, DataRequest, DataRequestItem, EvidenceChunkContext, TargetSlot
from master_agent.context import group_evidence_by_source

EXAMPLE_JSON_STRUCTURE = {
    "gap_analysis": {"status": "complete", "missing_fields": []},
    "sections": [
        {"type": "narrative", "slot_id": "string", "content": "ข้อความบรรยายพร้อมเลขอ้างอิง [1]"},
        {
            "type": "table",
            "slot_id": "string",
            "headers": ["หัวตาราง 1", "หัวตาราง 2"],
            "rows": [
                {
                    "values": ["ค่า 1", "ค่า 2"],
                    "citations": [{"source_filename": "string", "chunk_index": 0}],
                    "group": "string (ใส่เฉพาะเมื่อ Target Slot นี้มี groups - ต้องตรงกับหนึ่งใน groups เป๊ะๆ)",
                    "record_key": "string (ใส่เฉพาะเมื่อ Target Slot นี้มี rows_per_record - ทุกแถวย่อยของ "
                    "record เดียวกันต้องใช้ค่าเดียวกันเป๊ะๆ)",
                }
            ],
        },
    ],
    "citations": [
        {
            "citation_id": "[1]",
            "text_span": "ข้อความที่ใช้อ้างอิง",
            "source_filename": "string",
            "chunk_index": 0,
        }
    ],
}


class AgentOutputError(Exception):
    pass


def _base_system_prompt(
    criterion_code: str, criterion_name: str, source_count: int, current_academic_year: int | None
) -> str:
    """The criterion-agnostic instructions every Criterion Agent shares.
    Criterion-specific rules (e.g. PS's column-splitting/degree-abbreviation
    rules) are NOT here - they're appended separately by each agent module
    from its own prompt/system_prompt.txt (`extra_rules`), so a P1-P8 agent
    never silently inherits PS's business rules the way the old single
    shared prompt did.
    """
    prompt = (
        f"คุณคือ AUN-QA Criteria Agent ประจำเกณฑ์ {criterion_code} ({criterion_name})\n\n"
        "ทำงานตามลำดับนี้เท่านั้น:\n"
        "1. อ่าน [GUIDELINE] ของเกณฑ์นี้ - คือกฎ/ข้อกำหนด/เงื่อนไขที่ต้องตรวจสอบ ไม่ใช่ข้อเท็จจริง\n"
        "2. อ่าน [EVIDENCE_SOURCES] - คือข้อเท็จจริงของหลักสูตรปีปัจจุบัน แหล่งเดียวที่อนุญาตให้ใช้เป็นข้อเท็จจริง "
        "จัดกลุ่มแยกเป็นบล็อกตามไฟล์ต้นทาง (SOURCE 1 ถึง SOURCE N) แต่ละ SOURCE คือหลักฐาน 1 ชิ้น (เช่น CV 1 คน)\n"
        "3. เปรียบเทียบแต่ละข้อของ GUIDELINE กับ EVIDENCE_SOURCES ว่ามีหลักฐานรองรับหรือไม่\n"
        "4. ถ้า Evidence ไม่รองรับข้อกำหนดข้อใด ห้ามแต่งข้อมูลขึ้นเพื่อให้ผ่าน Guideline - ให้ระบุ "
        "gap_analysis.status เป็น missing พร้อมระบุ missing_fields แทน\n"
        "5. สร้างเนื้อหาเฉพาะจากข้อเท็จจริงใน Evidence ที่ตรวจสอบแล้วว่ารองรับ Guideline\n"
        "6. จัดเนื้อหาลง Target Slots ที่กำหนดให้เท่านั้น (ห้ามสร้าง slot ใหม่)\n"
        "7. ทุกข้อความบรรยายที่มีข้อเท็จจริงต้องมี Citation Number เช่น [1] และทุก Row ของตารางต้องมี "
        "Citation ระดับ Row อ้างอิงกลับไปยัง Evidence Chunk จริงเท่านั้น (ห้ามอ้างอิง chunk ที่ไม่ได้อยู่ใน "
        "[EVIDENCE_SOURCES])\n"
        "8. ส่งกลับเป็น JSON ตาม schema ที่กำหนดเท่านั้น ห้ามส่งข้อความอื่นนอก JSON\n\n"
        "กฎเพิ่มเติม:\n"
        "- ห้ามนำข้อมูลจาก [EXAMPLE_TEXT] มาใช้เป็นข้อเท็จจริงเด็ดขาด (ชื่อ/จำนวน/ตัวเลข/ปี/ผลการประเมิน) "
        "ใช้ Example เพื่อศึกษาสำนวนภาษาและโครงสร้างประโยคเท่านั้น เว้นแต่ข้อมูลนั้นมี Evidence ปัจจุบันรองรับโดยตรง\n"
        "- ใช้ [KEYWORDS] และ [REQUIRED_EVIDENCE] เป็นตัวช่วยทำความเข้าใจว่าเกณฑ์นี้ต้องการข้อมูลประเภทใด\n"
        "- citation_id ต้องเป็นเลขอ้างอิงที่คุณกำหนดเรียงลำดับเองภายในคำตอบนี้เท่านั้น รูปแบบ \"[1]\", \"[2]\", \"[3]\" "
        "(ตัวเลขเรียงจาก 1 ห้ามข้าม ห้ามซ้ำ) เริ่มนับใหม่ทุกครั้งที่ตอบ ห้ามใช้ค่าอื่นใดเป็น citation_id เด็ดขาด "
        "โดยเฉพาะห้ามคัดลอกชื่อไฟล์ เลข chunk_index หรือรหัสใดๆ ที่ปรากฏใน [EVIDENCE_SOURCES] มาใส่ใน citation_id - "
        "หน้าที่ของ citation_id คือเป็นเลขอ้างอิงสั้นๆ ให้คนอ่านเทียบกับรายการ citations ท้าย JSON เท่านั้น ส่วนการ "
        "อ้างอิง Evidence Chunk จริงให้ใช้ source_filename และ chunk_index ในรายการ citations แทน\n"
        f"- [EVIDENCE_SOURCES] ถูกจัดกลุ่มแยกตามไฟล์ต้นทางไว้ให้แล้วทั้งหมด {source_count} แหล่งข้อมูล (SOURCE 1 ถึง "
        f"SOURCE {source_count}) - ถ้า Target Slot เป็นตารางที่แต่ละแถวควรตรงกับหนึ่งแหล่งข้อมูลพอดี (เช่น ตารางรายชื่อ "
        f"บุคคลที่ 1 คน = 1 SOURCE/1 ไฟล์ CV) ต้องประมวลผลและสร้างแถวข้อมูลให้ครบทั้ง {source_count} SOURCE ตามลำดับที่ให้มา "
        "ห้ามตกหล่นหรือข้าม SOURCE ใดเด็ดขาด แม้ SOURCE นั้นจะมีเนื้อหาน้อยกว่า SOURCE อื่นก็ตาม ก่อนส่งคำตอบให้ทวนนับจำนวน "
        f"แถวที่สร้างเทียบกับจำนวน SOURCE ({source_count}) อีกครั้งเสมอ - ถ้าไม่ครบให้กลับไปอ่าน SOURCE ที่ยังไม่ได้สร้างแถว "
        "แล้วเพิ่มให้ครบก่อนตอบ\n"
        "- ทุกแถวของตารางที่มาจาก [EVIDENCE_SOURCES] ต้องมี citations ที่ระบุ source_filename ตรงกับ SOURCE ที่แถวนั้น "
        "มาจากเสมอ ห้ามอ้างอิง SOURCE อื่นที่ไม่ใช่แหล่งข้อมูลจริงของแถวนั้น\n"
        "- ถ้า Target Slot (table) มี groups กำกับไว้ ทุก row ในตารางนั้นต้องระบุ field \"group\" ให้ตรงกับหนึ่งใน "
        "รายการ groups ที่กำหนดเป๊ะๆ (ห้ามสร้างชื่อ group ขึ้นเอง ห้ามสะกดต่าง) เพื่อให้ระบบรู้ว่าข้อมูลแถวนี้ควรอยู่ใน "
        "กลุ่มใดของตาราง ถ้า Target Slot ไม่มี groups ไม่ต้องใส่ field นี้\n"
        "- ถ้า Target Slot (table) มี rows_per_record มากกว่า 1 แปลว่าตารางนั้นต้องใช้หลายแถวจริงต่อหนึ่ง record "
        "(เช่น 1 คน มีข้อมูลหลายปีการศึกษา แถวละ 1 ปี) ทุกแถวย่อยของ record เดียวกันต้องระบุ field \"record_key\" "
        "เป็นค่าเดียวกันเป๊ะๆ (เช่น ชื่อเต็มของบุคคลนั้น) และต้องมีจำนวนแถวย่อยไม่เกิน rows_per_record ต่อหนึ่ง record - "
        "คอลัมน์ที่เป็นข้อมูลประจำตัว (เช่น ชื่อ ตำแหน่ง วุฒิ) ให้ใส่ค่าเดียวกันซ้ำทุกแถวย่อยของ record นั้น ส่วนคอลัมน์ที่ควร"
        "ต่างกันในแต่ละแถวย่อยตามความหมายของหัวตาราง (เช่น ปีการศึกษา และจำนวนผลงานของปีนั้น) ให้ใส่ค่าจริงที่ต่างกันตามปี "
        "ห้ามใส่ค่าเดียวกันซ้ำทุกแถวถ้าหัวตารางสื่อว่าควรต่างกัน ถ้าไม่มีข้อมูลของปีใดให้ใส่ 0 หรือ \"\" ตามความเหมาะสม "
        "ห้ามเดาตัวเลข (ต้องมี Evidence รองรับเสมอ)\n"
        "- ถ้าบุคคลเดียวกันปรากฏในมากกว่าหนึ่ง Target Slot (เช่น ตารางรายชื่อกับตารางรายละเอียดผลงานของคนกลุ่มเดียวกัน) "
        "ต้องใช้ค่า \"group\" (หมวดหมู่/ประเภท) เดียวกันสำหรับบุคคลนั้นในทุกตาราง ห้ามขัดแย้งกันเองระหว่างตาราง"
        + (
            f"\n- ปีการศึกษาปัจจุบันคือ {current_academic_year} (ดู [CURRENT_ACADEMIC_YEAR]) ถ้าต้องระบุปีย้อนหลัง "
            "(เช่น 'ย้อนหลัง N ปีการศึกษา') ให้นับถอยหลังจากปีนี้"
            if current_academic_year is not None
            else ""
        )
    )

    if get_settings().test_mode_force_content:
        prompt += (
            "\n\nหมายเหตุ (โหมดทดสอบระบบ - TEST_MODE_FORCE_CONTENT=true ใน .env): "
            "[GUIDELINE] หรือ [REQUIRED_EVIDENCE] ของเกณฑ์นี้อาจว่างเปล่าเพราะยังไม่มีหลักฐานตัวเต็ม "
            "(เช่น ยังไม่มี มคอ.2) ในกรณีนี้ห้ามตีความว่า 'ไม่มี Guideline ให้เช็ค = ข้อมูลไม่ครบ' และห้ามรายงาน "
            "gap_analysis.status เป็น missing เพียงเพราะ GUIDELINE ว่าง - ให้เขียนเนื้อหาที่ตรงกับ Target Slot "
            "จาก Evidence Chunks ที่มีจริงให้ดีที่สุดแทน (ยังคงห้ามแต่งข้อเท็จจริงที่ไม่มีใน Evidence และยังต้องมี "
            "Citation ตามปกติ) วัตถุประสงค์คือทดสอบว่า pipeline ทำงานได้จริงระหว่างที่ยังรอ Evidence ตัวเต็ม"
        )

    return prompt


def _format_slots(slots: list[TargetSlot]) -> str:
    lines = []
    for slot in slots:
        if slot.type == "narrative":
            lines.append(f"- slot_id={slot.slot_id} type=narrative")
            continue
        extras = []
        if slot.groups:
            extras.append(f"groups={slot.groups}")
        if slot.rows_per_record:
            extras.append(f"rows_per_record={slot.rows_per_record}")
        suffix = (" " + " ".join(extras)) if extras else ""
        lines.append(f"- slot_id={slot.slot_id} type=table headers={slot.headers}{suffix}")
    return "\n".join(lines)


def _format_list(items: list[str]) -> str:
    if not items:
        return "(ไม่มีข้อมูล)"
    return "\n".join(f"- {item}" for item in items)


def build_prompt(
    criterion_code: str,
    criterion_name: str,
    guideline: list[str],
    keywords: list[str],
    required_evidence: list[str],
    example_section: str,
    evidence_chunks: list[EvidenceChunkContext],
    target_slots: list[TargetSlot],
    current_academic_year: int | None = None,
    feedback: str | None = None,
    extra_rules: str = "",
) -> tuple[str, str]:
    evidence_block, source_count = group_evidence_by_source(evidence_chunks)
    system_prompt = _base_system_prompt(criterion_code, criterion_name, source_count, current_academic_year)
    if extra_rules.strip():
        system_prompt += "\n\nกฎเฉพาะของเกณฑ์นี้:\n" + extra_rules.strip()

    user_prompt = f"""[CRITERION]
{criterion_code}

[CRITERION_NAME]
{criterion_name}

[GUIDELINE]
{_format_list(guideline)}

[KEYWORDS]
{_format_list(keywords)}

[REQUIRED_EVIDENCE]
{_format_list(required_evidence)}

[EXAMPLE_TEXT]
{example_section}
(หมายเหตุ: Example ใช้เป็นแนวทางด้านภาษาเท่านั้น ห้ามนำข้อเท็จจริงจาก Example มาใช้)

[EXAMPLE_JSON_STRUCTURE]
{json.dumps(EXAMPLE_JSON_STRUCTURE, ensure_ascii=False, indent=2)}

{evidence_block}

[TARGET_SLOTS]
{_format_slots(target_slots)}
"""

    if current_academic_year is not None:
        user_prompt += f"\n[CURRENT_ACADEMIC_YEAR]\n{current_academic_year}\n"

    if feedback:
        user_prompt += f"\n[REVISION_REQUIRED]\n{feedback}\n"

    return system_prompt, user_prompt


def run_agent(
    criterion_code: str,
    criterion_name: str,
    guideline: list[str],
    keywords: list[str],
    required_evidence: list[str],
    example_section: str,
    evidence_chunks: list[EvidenceChunkContext],
    target_slots: list[TargetSlot],
    current_academic_year: int | None = None,
    feedback: str | None = None,
    extra_rules: str = "",
) -> AgentResponse:
    system_prompt, user_prompt = build_prompt(
        criterion_code,
        criterion_name,
        guideline,
        keywords,
        required_evidence,
        example_section,
        evidence_chunks,
        target_slots,
        current_academic_year,
        feedback,
        extra_rules,
    )
    raw = generate_json(f"{system_prompt}\n\n{user_prompt}")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AgentOutputError(f"Agent did not return valid JSON: {exc}") from exc

    try:
        return AgentResponse.model_validate(data)
    except ValidationError as exc:
        raise AgentOutputError(f"Agent JSON did not match the required schema: {exc}") from exc


def default_build_data_request(criterion_code: str, meta: dict) -> DataRequest:
    """Each Criterion Agent owns its Data Requirement (change.md sec.7) - it
    is determined from the Agent's own Prompt/Logic/Template Structure, not
    handed down by Master or the Retrieval Manager. Today an Agent's "Logic"
    for what it needs is still keyword-based (master_config.json's
    per-criterion `keywords`, unchanged from the pre-migration behavior) -
    real per-data-type/role splitting (e.g. PS separately requesting
    "person"/"education"/"appointment") needs the structured MongoDB
    collections from change.md sec.9/sec.12 to be meaningful, which are out
    of scope for this change (DO NOT TOUCH: real MongoDB data population).
    Kept as one shared default (rather than six copy-pasted identical
    bodies) since every agent currently builds its request the same way;
    an agent module is free to override this once it has real data-type
    logic of its own to express (see criterion_agents/ps_agent/agent.py's
    docstring).
    """
    query = " ".join(meta.get("keywords", []))
    return DataRequest(
        criterion=criterion_code,
        requests=[DataRequestItem(data_type="evidence", purpose=query)],
    )
