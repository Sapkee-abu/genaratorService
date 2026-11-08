"""Real-infrastructure retrieval + verification-flow tests (fix.md Phase A).

Uses the REAL MCP server (spawned over stdio exactly like master.py does), the
REAL ChromaDB, the REAL MongoDB and the real Retrieval Manager / PS field
resolution. READ-ONLY end to end: no MongoDB write, no Chroma write (only
query/get), so no temp DB is needed. The MCP subprocess reads the production
source collections (allowed: source data is read-only for this whole task).

CASE 1  Chroma evidence is sufficient for a person's highest education
          -> the value is taken from Chroma, with a REAL Chroma document reference
CASE 2  Chroma returned hits for the person but they do NOT support the field
          -> Chroma non-empty != complete: falls through to MongoDB, real `educations` reference
CASE 3  Chroma yields nothing AND MongoDB has nothing for the item
          -> Document/OCR tier is consulted; it is a stub today (no OCR pipeline, and
             documents.extractedText paths live on the Import Service's filesystem), so the item
             is reported `missing` with a full trace - never a fabricated hit.
Also: Agents never touch MongoDB/Chroma/filesystem/OCR directly (static import scan);
Verification PASS/FAIL semantics and that Injection is only reachable after PASS (static + unit).
"""

from __future__ import annotations

import ast
import asyncio
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

from common.config import get_settings  # noqa: E402
from common.schemas import CitationEntry, DataRequestItem, EvidenceChunkContext  # noqa: E402
from criterion_agents.ps_agent.agent import _resolve_highest_education_level  # noqa: E402
from criterion_agents.ps_agent.person_aggregation import aggregate_curriculum_people  # noqa: E402
from retrieval.manager import RetrievalManager  # noqa: E402

passed = 0


def ok(name: str) -> None:
    global passed
    passed += 1
    print(f"TEST {name}: OK", flush=True)


async def call_single(session, name, args=None) -> dict:
    result = await session.call_tool(name, args or {})
    assert not result.isError, result.content
    return json.loads(result.content[0].text)


async def call_list(session, name, args=None) -> list[dict]:
    result = await session.call_tool(name, args or {})
    assert not result.isError, result.content
    return [json.loads(b.text) for b in result.content if hasattr(b, "text")]


def test_agents_never_touch_data_stores_directly() -> None:
    """Static scan: no Criterion Agent module imports a DB/Chroma/OCR client or opens arbitrary files."""
    forbidden = ("motor", "pymongo", "chromadb", "common.mongo", "common.chroma", "retrieval.mongodb",
                 "retrieval.document_ocr", "common.bge_embedding", "fitz", "pymupdf", "pytesseract")
    offenders = []
    for path in (BACKEND / "criterion_agents").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            for n in names:
                if any(n == f or n.startswith(f + ".") for f in forbidden):
                    offenders.append(f"{path.name}: import {n}")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open":
                offenders.append(f"{path.name}: open()")
    assert not offenders, offenders
    ok("0a Criterion Agents import no MongoDB/Chroma/OCR client and call no open() (retrieval only via Master/MCP)")


def test_injection_only_after_verification_pass() -> None:
    """Static scan of master.py's loop: `verified_response` is only ever assigned inside `if result.passed`,
    and inject_section is only reached under `verified_response is None -> continue` first."""
    src = (BACKEND / "master_agent" / "master.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    assigns = []
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and "result.passed" in ast.unparse(node.test):
            for sub in ast.walk(node):
                if isinstance(sub, ast.Assign) and any(getattr(t, "id", "") == "verified_response" for t in sub.targets):
                    assigns.append(sub)
    all_assigns = [n for n in ast.walk(tree) if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "verified_response" for t in n.targets)]
    non_none = [a for a in all_assigns if not (isinstance(a.value, ast.Constant) and a.value.value is None)]
    assert len(non_none) == 1 and non_none[0] in assigns, "verified_response is set outside `if result.passed`"
    body = src.index("if verified_response is None:")
    assert body < src.index("inject_section(resolved_slots, section, placements)"), "injection reachable before the PASS guard"
    guard = src[body : src.index("inject_section(resolved_slots, section, placements)")]
    assert "continue" in guard, "FAIL path must `continue` past injection"
    # the SAME agent object serves every retry: it is resolved once, outside the attempt loop
    assert src.index("agent = get_agent(criterion_code)") < src.index("for attempt in range(")
    ok("0b Master: verified_response only set on Verification PASS; FAIL `continue`s past Injection; same Agent object retried")


def test_verification_pass_and_fail_units() -> None:
    from common.schemas import AgentResponse, GapAnalysis, NarrativeSection
    from common.verification import verify

    text = "หลักสูตรมีการแต่งตั้งอาจารย์ผู้รับผิดชอบหลักสูตรตามคำสั่งมหาวิทยาลัยที่ 350/2568 ลงวันที่ 4 กุมภาพันธ์ พ.ศ. 2568"
    chunk = EvidenceChunkContext(chunk_id="c1", document_id="d1", chunk_index=0, source_filename="d1", text=text)

    def response(span: str, source: str = "d1", idx: int = 0):
        return AgentResponse(
            gap_analysis=GapAnalysis(status="complete"),
            sections=[NarrativeSection(type="narrative", slot_id="s", content="หลักสูตรมีการแต่งตั้งอาจารย์ผู้รับผิดชอบหลักสูตรตามคำสั่งมหาวิทยาลัยที่ 350/2568 ลงวันที่ 4 กุมภาพันธ์ พ.ศ. 2568 [1]")],
            citations=[CitationEntry(citation_id="[1]", text_span=span, source_filename=source, chunk_index=idx)],
        )

    assert verify(response(text), [chunk]).passed is True
    bad_span = verify(response("ข้อความที่ไม่มีอยู่ในหลักฐานเลยแม้แต่น้อย xyz"), [chunk])
    assert bad_span.passed is False and bad_span.issues and bad_span.feedback_text()
    outside = verify(response(text, source="not-in-evidence"), [chunk])
    assert outside.passed is False and any("ไม่อยู่ใน Evidence" in i for i in outside.issues)
    ok("0c Verification: real evidence-matching citation PASSes; wrong text_span and out-of-evidence citation FAIL with feedback")


async def main() -> None:
    test_agents_never_touch_data_stores_directly()
    test_injection_only_after_verification_pass()
    test_verification_pass_and_fail_units()

    settings = get_settings()
    params = StdioServerParameters(command=sys.executable, args=["-m", "mcp_server.server"], cwd=str(BACKEND))
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            raw = await call_single(session, "get_curriculum_people_raw")
            people = aggregate_curriculum_people(raw["appointments"], raw["persons"], raw["educations"], raw["academic_works"])
            assert people, "no people aggregated from real MongoDB"

            # exactly what master.py does per person (Chroma-first, dedicated per-person query)
            chroma: dict[str, list[dict]] = {}
            for person in people:
                chroma[person.person_id] = await call_list(
                    session, "search_evidence",
                    {"query": f"วุฒิการศึกษาสูงสุด {person.last_name} {person.first_name}", "top_k": 5},
                )

            case1, case2 = [], []
            for person in people:
                hits = chroma[person.person_id]
                level, citation = _resolve_highest_education_level(person, hits)
                assert hits, "real Chroma returned no hits at all"  # top-k nearest neighbours are always non-empty
                source = None if citation is None else ("mongodb" if citation.source_filename.startswith("mongodb:") else "chroma")
                (case1 if source == "chroma" else case2 if source == "mongodb" else []).append((person, hits, level, citation))
            print(f"   real persons: {len(people)}; resolved from Chroma: {len(case1)}; Chroma non-empty but insufficient -> MongoDB: {len(case2)}")

            # ---------------- CASE 1 ----------------
            if case1:
                person, hits, level, citation = case1[0]
                assert citation.source_filename in {h["source_filename"] for h in hits}, "Chroma citation not among real hits"
                mongo_levels = {e.get("degree") for e in person.educations}
                print(f"   CASE 1 sample: {person.display_name}: level={level!r} from Chroma doc {citation.source_filename} chunk {citation.chunk_index}; "
                      f"Mongo degrees={sorted(d for d in mongo_levels if d)}")
                ok("1  CASE 1 - Chroma evidence sufficient -> value + real Chroma reference used")
            else:
                print("TEST 1  CASE 1 NOT OBSERVABLE with this dataset: no person's Chroma evidence is sufficient for highest education")

            # ---------------- CASE 2 ----------------
            assert case2, "expected at least one person whose Chroma hits are non-empty but insufficient"
            for person, hits, level, citation in case2:
                assert hits, "CASE 2 requires Chroma to have returned hits"
                assert citation.source_filename.startswith("mongodb:educations:"), citation
            person, hits, level, citation = case2[0]
            print(f"   CASE 2 sample: {person.display_name}: Chroma returned {len(hits)} hit(s) (non-empty) yet level came from "
                  f"{citation.source_filename} -> {level!r}")
            ok(f"2  CASE 2 - Chroma non-empty but insufficient -> MongoDB fallback for {len(case2)}/{len(people)} people (never 'non-empty == complete')")

            # ---------------- CASE 3 ----------------
            # Make Chroma legitimately yield nothing by excluding every chunk id it has (read-only get), and
            # ask for a data_type MongoDB cannot resolve ("evidence") -> all three tiers are consulted.
            import chromadb

            col = chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port).get_collection(settings.chroma_collection)
            all_ids = col.get(include=[])["ids"]

            async def _search_chroma(q, k, exclude):
                return await call_list(session, "search_evidence", {"query": q, "top_k": k, "exclude_chunk_ids": exclude})

            async def _search_mongo(item):
                return await call_list(session, "query_structured_data", {"data_type": item.data_type, "role": item.role})

            async def _search_ocr(item):
                return await call_list(session, "retrieve_document", {"data_type": item.data_type})

            manager = RetrievalManager(_search_chroma, _search_mongo, _search_ocr, top_k=5)
            retrieved = await manager.retrieve(
                [DataRequestItem(data_type="evidence", purpose="ข้อมูลที่ไม่มีในทุกแหล่ง")], exclude_chunk_ids=all_ids
            )
            trace = retrieved.fields[0].trace()
            print("   CASE 3 trace:", json.dumps(trace, ensure_ascii=False))
            assert trace["tiersTried"] == ["chromadb", "mongodb", "document_ocr"], trace
            assert trace["missing"] is True and trace["fallbackUsed"] is True and trace["chunkCount"] == 0 and trace["sources"] == []
            ok("3  CASE 3 - Chroma empty + MongoDB empty -> Document/OCR consulted -> `missing` with full trace, no fabricated sourceReference")
            print("   NOTE: real Document/OCR retrieval is BLOCKED - retrieval/document_ocr.py is a stub (no OCR pipeline) and "
                  "documents.extractedText paths point at the Import Service's filesystem, not readable here.")

            # manager-level semantics, recorded honestly: for a Mongo-resolvable type the per-item ladder stops at Chroma
            retrieved = await manager.retrieve([DataRequestItem(data_type="appointment", role="programmeResponsible", purpose="PS instructor list")])
            t = retrieved.fields[0].trace()
            print("   manager-level ladder for a Mongo-resolvable item:", json.dumps({k: t[k] for k in ("tiersTried", "resolvedTier", "chunkCount")}))
            assert t["resolvedTier"] == "chromadb" and t["tiersTried"] == ["chromadb"]
            ok("3b Manager-level ladder is first-non-empty (finding: completeness for PS is guaranteed by per-field resolve_field + the "
               "structured Mongo context, not by this ladder)")

    print(f"\nALL {passed} retrieval/verification checks passed (read-only; no DB writes)")


if __name__ == "__main__":
    asyncio.run(main())
