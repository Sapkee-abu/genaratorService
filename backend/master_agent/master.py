"""Master Agent (mainpromt.md): the MCP client that drives the full
Initialization -> Slot Marking -> Criteria Processing Loop -> Export workflow.

Run as: python -m master_agent.master   (from the generator/ directory, with
mcp_server/ and master_config.json alongside it, and chroma/mongo/gemini
reachable per .env).
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import sys
import uuid
from pathlib import Path

import docx
from mcp import ClientSession, StdioServerParameters
# เป็น สะพานเชื่อม เพื่อให้ mcp client ต่อกับ mcp server
from mcp.client.stdio import stdio_client    

from common.config import get_settings
from common.logging_repo import log_criterion, log_slot_map, log_slot_marking
from common.schemas import EvidenceChunkContext, TargetSlot

# Windows defaults stdout to the system codepage (cp1252) whenever it isn't
# attached to a UTF-8-aware terminal (e.g. under uvicorn/api_server.py, or a
# plain `python -m master_agent.master` without PYTHONIOENCODING set) - any
# print() with Thai text then crashes the whole run with UnicodeEncodeError.
# This was masked in manual CLI testing by setting PYTHONIOENCODING=utf-8
# explicitly each time; forcing it here makes every entrypoint safe by default.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
from common.verification import verify
from criterion_agents._shared import AgentOutputError
from criterion_agents.ps_agent.person_aggregation import aggregate_curriculum_people
from criterion_agents.registry import get_agent
from master_agent import context as context_module
from master_agent.docx_utils import force_field_update
from master_agent.slot_marking_agent import SlotMarkingError, apply_marks, run_slot_marking_agent
from master_agent.slot_map import build_slot_map
from master_agent.template_injector import InjectionError, Placement, inject_section
from master_agent.template_structure import describe_document
from retrieval.manager import RetrievalManager


def mcp_server_parameters(generator_root: Path) -> StdioServerParameters:
    """Start MCP with the same runtime configuration as the Generator.

    The MCP SDK otherwise inherits only a small safe list such as HOME and
    PATH. In Docker, application settings are supplied to the parent process
    by Compose and there is deliberately no /app/.env containing secrets, so
    omitting ``env`` makes every MCP tool lose MongoDB, ChromaDB, Template and
    Gemini configuration.
    """
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_server.server"],
        cwd=str(generator_root),
        env=dict(os.environ),
    )


async def _call_tool_single(session: ClientSession, name: str, arguments: dict | None = None) -> dict:
    """For tools that return one JSON object (get_sar_template, get_example,
    get_master_config)."""
    result = await session.call_tool(name, arguments or {})
    if result.isError:
        raise RuntimeError(f"MCP tool '{name}' failed: {result.content}")
    return json.loads(result.content[0].text)

# ตัวหลัก session mcp client ส่งข้อมูลไป และ ได้ข้อมูลจาก mcp server result
async def _call_tool_list(session: ClientSession, name: str, arguments: dict | None = None) -> list[dict]:
    """For tools that return list[dict] (search_evidence). FastMCP serializes
    a list return as one TextContent block per item, not a single JSON array
    - so each content block is parsed and collected here."""
    # คือข้อมูลที่ได้จาก mcp server
    result = await session.call_tool(name, arguments or {})
    if result.isError:
                                                        # คือข้อมูลที่ได้จาก mcp server
        raise RuntimeError(f"MCP tool '{name}' failed: {result.content}")
            # แปลงกลับเป็น Python dictionary
    return [json.loads(block.text) for block in result.content if hasattr(block, "text")]


def _criterion_trace(attempts_trace: list[dict], ps_structured_context: dict | None, criterion_code: str) -> dict:
    trace: dict = {"attempts": attempts_trace}
    if criterion_code == "PS" and ps_structured_context is not None:
        # PS also gets structured (deterministic) Mongo context outside the
        # per-item ladder - record what it contained
        trace["psStructuredContext"] = {
            "people": len(ps_structured_context["people"]),
            "mongoCitationChunks": len(ps_structured_context["mongo_citation_chunks"]),
            "educationChromaHitsPerPerson": {
                person_id: len(hits) for person_id, hits in ps_structured_context["education_chroma_hits"].items()
            },
        }
    return trace


async def run(run_id: str | None = None) -> Path:
    """`run_id` lets a caller (e.g. api_server.py) supply its own id up front,
    so it can correlate this run with the generation_criteria_log /
    generation_slot_marking_log entries written to Mongo while it's still in
    progress - the CLI entrypoint below doesn't need this and just lets one
    be generated."""
    settings = get_settings()
    run_id = run_id or str(uuid.uuid4())
    generator_root = Path(__file__).resolve().parent.parent
    output_dir = Path(settings.output_dir)

    server_params = mcp_server_parameters(generator_root)
# เป็น สะพานเชื่อม เพื่อให้ mcp client ต่อกับ mcp server
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # ---------- INITIALIZATION (mainpromt.md sec.4-9, changefeature.md sec.22) ----------
            # Template/Example are opened straight from the bytes MCP handed
            # back - no temp file ever touches disk before the final export,
            # per addfeature.md's in-memory-only rule. Guideline is NOT
            # fetched here anymore - per changefeature.md, each criterion's
            # guideline lives directly in master_config.json.
            template_payload = await _call_tool_single(session, "get_sar_template")
            if not template_payload.get("found"):
                raise RuntimeError(template_payload.get("error", "SAR Template not available"))
            template_bytes = base64.b64decode(template_payload["content_base64"])
            document = docx.Document(io.BytesIO(template_bytes))

            example_payload = await _call_tool_single(session, "get_example")
            example_text = ""
            example_document = None
            if example_payload.get("found"):
                example_bytes = base64.b64decode(example_payload["content_base64"])
                example_text = context_module.extract_text(example_bytes, example_payload["file_format"])
                if example_payload["file_format"] == "docx":
                    example_document = docx.Document(io.BytesIO(example_bytes))

            master_config = await _call_tool_single(session, "get_master_config")
            criterion_order: list[str] = master_config["criterion_order"]
            criteria_meta: dict = master_config["criteria"]
            current_academic_year: int | None = master_config.get("current_academic_year")

            # ---------- SLOT MARKING AGENT (addfeature.md) ----------
            # Scans the whole template's Document Structure once and resolves
            # each slot directly to a Paragraph/Table object in memory, so
            # nobody has to hand-mark the real SAR template. Runs once,
            # before the loop.
            structure = describe_document(document)
            example_structure = describe_document(example_document) if example_document is not None else None
            try:
                # google-genai exposes a synchronous generate_content call in
                # the current agent helpers. Keep that network wait away from
                # FastAPI's event loop so health/status requests remain
                # responsive while a production generation is running.
                marking_result = await asyncio.to_thread(
                    run_slot_marking_agent,
                    structure,
                    criteria_meta,
                    example_structure,
                )
                resolved_slots = apply_marks(document, structure, marking_result.marked_slots)
                print(f"Slot Marking Agent: resolved {len(resolved_slots)}/{len(marking_result.marked_slots)} slots")
                await log_slot_marking(
                    run_id,
                    "success",
                    [
                        {"criterion": s.criterion, "slot_id": s.slot_id, "type": s.type, "headers": s.headers}
                        for s in resolved_slots.values()
                    ],
                )
            except SlotMarkingError as exc:
                print(f"Slot Marking Agent failed: {exc}")
                await log_slot_marking(run_id, "failed", [])
                raise

            # ---------- STEP 2.1: target slots, straight from the resolved marks ----------
            all_slots = [
                TargetSlot(
                    slot_id=s.slot_id,
                    type=s.type,
                    criterion=s.criterion,
                    headers=s.headers,
                    # checkbox_options (only ever set for a block-shaped table,
                    # rows_per_record > 1) takes priority: a block table's own
                    # position-based "group" (from analyze_table_groups) is
                    # really just a single divider label spanning every block
                    # (e.g. "อาจารย์ประจำหลักสูตร/อาจารย์ผู้รับผิดชอบหลักสูตร" - one
                    # non-empty label, not the two real per-record categories),
                    # so preferring it here would silently discard the correct
                    # per-record checkbox categories - see slot_marking_agent's
                    # `checkbox_options` and template_injector's use of it.
                    groups=s.checkbox_options
                    or (([g.label for g in s.layout.groups if g.label] or None) if s.layout else None),
                    rows_per_record=s.rows_per_record,
                )
                for s in resolved_slots.values()
            ]

            placements: list[Placement] = []
            injected_slot_ids: set[str] = set()

            # MCP ARCHITECTURE BOUNDARY (change.md "MCP ARCHITECTURE - MUST
            # FIX"): all three retrieval tiers go through MCP tools over this
            # same session - Master/Retrieval Manager never touch ChromaDB,
            # MongoDB, or a filesystem/OCR pipeline directly.
            async def _search_chroma(query: str, top_k: int, exclude_chunk_ids: list[str]) -> list[dict]:
                # เอา data ใส่ภายใน ฟังชั้นมีการเรียกใช้ อ้างถึง mcp client
                return await _call_tool_list(
                    session,
                    "search_evidence",
                    {"query": query, "top_k": top_k, "exclude_chunk_ids": exclude_chunk_ids},
                )

            async def _search_mongo(item) -> list[dict]:
                # เอา data ใส่ภายใน ฟังชั้นมีการเรียกใช้ อ้างถึง mcp client
                return await _call_tool_list(
                    session,
                    "query_structured_data",
                    {"data_type": item.data_type, "role": item.role},
                )

            async def _search_document_ocr(item) -> list[dict]:
                # ภายใน ฟังชั้นมีการเรียกใช้ mcp client
                return await _call_tool_list(session, "retrieve_document", {"data_type": item.data_type})

            # ---------- PS STRUCTURED CONTEXT (change.md "canonical person
            # aggregation" / "Retrieval Manager ให้รองรับ semantic field
            # request") - fetched once, before the loop, not per retry
            # attempt: the canonical aggregation is deterministic, so
            # there's nothing to gain from recomputing it on a verification
            # retry (only PS's LLM-driven narrative slots benefit from
            # retrying). Kept as a plain dict Master hands to PS's own
            # run() - other agents never receive or need this. ----------
            ps_structured_context: dict | None = None
            if "PS" in criterion_order:
                raw = await _call_tool_single(session, "get_curriculum_people_raw")
                # roles come ONLY from ACTIVE appointments of the current curriculum (single-curriculum system,
                # resolved through the same MCP boundary as every other MongoDB read)
                curriculum_hits = await _call_tool_list(session, "query_structured_data", {"data_type": "curriculum"})
                current_curriculum_id = curriculum_hits[0]["document_id"] if curriculum_hits else None
                if current_curriculum_id is None:
                    print("WARNING: no curriculum found in MongoDB - appointments are filtered by status only")
                people = aggregate_curriculum_people(
                    raw["appointments"], raw["persons"], raw["educations"], raw["academic_works"],
                    curriculum_id=current_curriculum_id,
                )

                # Unconditional Mongo-tier citation chunks (change.md sec.3/4:
                # a per-field decision is made separately below - these exist
                # so a citation built from the structured/deterministic data
                # is always resolvable by Verification's Gate 1, regardless
                # of what search_evidence separately found for narrative
                # slots via the ordinary per-item ladder).
                # limit=500 to match fetch_curriculum_people_raw's own
                # default (query_structured_data's own default is 50 -
                # silently truncating academic_works to the first 50 of a
                # real 112 caused several real citations to be missing from
                # evidence_context, failing Gate 1 for records past #50).
                mongo_citation_hits: list[dict] = []
                for data_type in ("person", "education", "academic_work"):
                    mongo_citation_hits += await _call_tool_list(
                        session, "query_structured_data", {"data_type": data_type, "limit": 500}
                    )
                for role in ("programmeResponsible", "programmeStaff", "specialInstructor"):
                    mongo_citation_hits += await _call_tool_list(
                        session, "query_structured_data", {"data_type": "appointment", "role": role}
                    )

                # Real per-person Chroma-first attempt for highest_education_level
                # (change.md sec.4/9/28) - a dedicated search per person, not
                # the broad per-criterion query used for narrative evidence.
                education_chroma_hits: dict[str, list[dict]] = {}
                for person in people:
                    education_chroma_hits[person.person_id] = await _call_tool_list(
                        session,
                        "search_evidence",
                        {"query": f"วุฒิการศึกษาสูงสุด {person.last_name} {person.first_name}", "top_k": 5},
                    )

                # The per-person Chroma hits above are also real citation
                # candidates whenever education_evidence.py judges one
                # sufficient - they must exist in evidence_context too, same
                # reason as mongo_citation_chunks (Gate 1's existence check).
                education_citation_chunks = [
                    EvidenceChunkContext(**hit) for hits in education_chroma_hits.values() for hit in hits
                ]

                ps_structured_context = {
                    "people": people,
                    "mongo_citation_chunks": [EvidenceChunkContext(**hit) for hit in mongo_citation_hits]
                    + education_citation_chunks,
                    "education_chroma_hits": education_chroma_hits,
                }

            # ---------- CRITERIA PROCESSING LOOP ----------
            # Master's role here is orchestration only: dispatch to the criterion's
            # own Agent (criterion_agents/registry.py - never a shared/generic
            # agent), forward that Agent's own Data Request to the Retrieval
            # Manager, hand the Retrieved Data back to the SAME Agent, send its
            # Result JSON to Verification, and branch on PASS/FAIL - Master never
            # writes PS/P1/P2/P3/P4/P8 content itself.
            for criterion_code in criterion_order:
                meta = criteria_meta[criterion_code]
                target_slots = [s for s in all_slots if s.criterion == criterion_code]

                if not target_slots:
                    print(f"[{criterion_code}] no target slots in template - skipping")
                    await log_criterion(run_id, criterion_code, "skipped_no_slots", [])
                    continue

                example_section = example_text
                agent = get_agent(criterion_code)  # same Agent module used for every retry below

                # Per-criterion override (master_config.json) takes priority over
                # the global default - some criteria (e.g. PS, which must describe
                # *every* instructor) need far more evidence chunks than others.
                # See README.md "Guideline lives in master_config.json" / forfuture.md.
                top_k = meta.get("evidence_top_k", settings.evidence_top_k)






                # สร้าง retrival_manager ส่งเครื่องมือ ฟังชั้น ที่ master สร้างขึ้นมาเอง
                retrieval_manager = RetrievalManager(
                    search_chroma=_search_chroma,
                    search_mongo=_search_mongo,
                    search_document_ocr=_search_document_ocr,
                    top_k=top_k,
                )

                # The Agent determines its own Data Requirement (change.md sec.7) -
                # Master/Retrieval Manager never decide what a criterion needs.
                data_request = agent.build_data_request(meta, target_slots)

                feedback: str | None = None
                excluded_chunk_ids: list[str] = []
                verified_response = None
                # audit trace (additive, logged with the criterion): per attempt -
                # what retrieval requested/served and the Verification verdict
                attempts_trace: list[dict] = []






                for attempt in range(settings.max_verification_retries + 1):
                    # ส่ง data request เข้า retrival_manger
                    retrieved = await retrieval_manager.retrieve(data_request.requests, excluded_chunk_ids)
                    attempt_record = {
                        "attempt": attempt + 1,
                        "excludedChunkCount": len(excluded_chunk_ids),
                        "retrieval": [f.trace() for f in retrieved.fields],
                    }
                    # รับข้อมูลจาก retrival และดึงข้อมูลมา ที่ retrival จัดข้อมูลให้อยู่ในรูปแบบมาตรฐานของระบบ
                    attempts_trace.append(attempt_record)
                    evidence_context = retrieved.all_chunks
                    if retrieved.missing_data_types:
                        print(f"[{criterion_code}] attempt {attempt + 1}: no evidence found (any tier) for: "
                              f"{retrieved.missing_data_types}")

                    extra_kwargs: dict = {}
                    if criterion_code == "PS" and ps_structured_context is not None:
                        # The structured/deterministic evidence exists in
                        # evidence_context too, so a RowCitation built from
                        # it is resolvable by Verification's Gate 1 - merged
                        # the same de-duplicated-by-chunk_id way
                        # RetrievedData.all_chunks already does.
                        seen_ids = {c.chunk_id for c in evidence_context}
                        evidence_context = evidence_context + [
                            c for c in ps_structured_context["mongo_citation_chunks"] if c.chunk_id not in seen_ids
                        ]
                        extra_kwargs["structured_context"] = ps_structured_context

                    try:
                        response = await asyncio.to_thread(
                            agent.run,
                            meta["name"],
                            meta["guideline"],
                            meta["keywords"],
                            meta["required_evidence"],
                            example_section,
                            evidence_context,
                            target_slots,
                            current_academic_year=current_academic_year,
                            feedback=feedback,
                            **extra_kwargs,
                        )
                    except AgentOutputError as exc:
                        print(f"[{criterion_code}] attempt {attempt + 1}: agent output error: {exc}")
                        attempt_record["agentError"] = str(exc)
                        feedback = str(exc)
                        continue

                    result = verify(response, evidence_context)
                    attempt_record["verification"] = {"passed": result.passed, "issues": [str(i) for i in result.issues]}
                    if result.passed:
                        verified_response = response
                        break

                    print(f"[{criterion_code}] attempt {attempt + 1}: verification failed: {result.issues}")
                    feedback = result.feedback_text()
                    excluded_chunk_ids = excluded_chunk_ids + [c.chunk_id for c in evidence_context]
                    # FAIL -> retry the SAME Agent (change.md sec.11) - the loop
                    # above re-enters with the same `agent`/`criterion_code`, never
                    # switching to a different Criterion Agent.

                if verified_response is None:
                    print(f"[{criterion_code}] FAILED verification after {settings.max_verification_retries + 1} attempts")
                    await log_criterion(
                        run_id, criterion_code, "failed_verification", [], trace=_criterion_trace(attempts_trace, ps_structured_context, criterion_code)
                    )
                    continue

                try:
                    for section in verified_response.sections:
                        inject_section(resolved_slots, section, placements)
                        injected_slot_ids.add(section.slot_id)
                except InjectionError as exc:
                    print(f"[{criterion_code}] injection failed: {exc}")
                    await log_criterion(
                        run_id, criterion_code, "failed_injection", [], trace=_criterion_trace(attempts_trace, ps_structured_context, criterion_code)
                    )
                    continue

                await log_criterion(
                    run_id,
                    criterion_code,
                    "completed",
                    [c.model_dump() for c in verified_response.citations],
                    sections=[s.model_dump() for s in verified_response.sections],
                    trace=_criterion_trace(attempts_trace, ps_structured_context, criterion_code),
                )
                print(f"[{criterion_code}] completed")

    # ---------- EXPORT (once, after every criterion) ----------
    # NO "Traceability Matrix" table is added to the DOCX: the generated SAR contains SAR content only.
    # Traceability is unchanged elsewhere - generation_criteria_log (sections + citations + trace),
    # generation_slot_marking_log.slot_map, reference/traceability_api.py, GET /api/reference*, the Web
    # Reference page and user-edit traceability all keep working from those records.
    # Forces Word to recompute every field (PAGE, NUMPAGES, TOC, ...) on open
    # instead of showing the template's stale cached values (e.g. a footer
    # PAGE field baked in as "8" on every page) - see docx_utils.force_field_update.
    force_field_update(document)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"SAR_{run_id}.docx"
    document.save(str(output_path))

    # Persist which block/row holds which slot (fix.md sec.11) - additive
    # $set on this run's existing generation_slot_marking_log document.
    await log_slot_map(run_id, build_slot_map(document, resolved_slots, injected_slot_ids, placements))

    # ---------- NO VERSION HERE (fix.md sec.1/5) ----------
    # Generate only produces the Current Generated Artifact above. It must
    # NOT append to generated_documents.generatedFiles[] - a Version
    # Snapshot is created only by an explicit Download
    # (api_server.py::download -> save_version_snapshot).
    print(f"Generated (no version created): {output_path}")

    return output_path


if __name__ == "__main__":
    result_path = asyncio.run(run())
    print(f"SAR generated: {result_path}")
