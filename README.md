# Generator Service — AUN-QA SAR Generation (Master Agent)
เรื่องการ เปิด/ปิด service gnarator 
ปิด: แค่ไม่ต้องรัน uvicorn api_server:app — หน้าเว็บจะเช็คแล้วโชว์ "ไม่พร้อมใช้งาน" เองอัตโนมัติ ไม่ต้องแก้โค้ดอะไรเลย
เปิดกลับ: รัน uvicorn api_server:app --port 8010 ใหม่อีกครั้งเท่านั้น

Implements `../../mainpromt.md` (as refined by `../../changefeature.md`):
reads the SAR Template and Example the Import Service (`../import`) has
already collected, reads each criterion's Guideline directly from
`master_config.json`, and produces a completed SAR `.docx` with citations
and a traceability matrix. Built only after the Import Service was complete
and tested, per `../../PROJECT.md`.

## ⚠️ Verification is currently bypassed in `master_agent/master.py`

`master.py` around line 173 currently **injects whatever the Criteria Agent
returns regardless of whether verification passes**, for testing purposes
while real Evidence for PS (an official instructor-count/appointment-order
document) is still missing. Any `.docx` generated right now may contain
**unverified, potentially miscited content** - do not treat it as compliant
output. To restore normal behavior (only inject verified content, retry on
failure), remove the 3-line bypass and restore the original:

```python
result = verify(response, evidence_context)
if result.passed:
    verified_response = response
    break
```

(the original retry logic just below is still intact and unreachable while
the bypass's `break` sits above it - removing the bypass makes it live
again, no other change needed).

## Architecture

```text
generator/
├── common/            shared by master_agent, mcp_server, and api_server
│   ├── config.py        .env-driven settings
│   ├── mongo.py          reads templates/examples + GridFS (same DB the Import Service writes to)
│   ├── chroma.py         queries the same ChromaDB collection the Import Service embeds into
│   ├── gemini.py         Gemini calls (embedding for queries, JSON generation for both agents)
│   ├── schemas.py        pydantic models: SlotMark/SlotMarkingResult, and the Criteria Agent's required JSON schema
│   ├── verification.py   the 3 verification gates
│   └── logging_repo.py   writes generation_slot_marking_log + generation_criteria_log to MongoDB
├── mcp_server/
│   └── server.py         MCP server (stdio) - the "MCP Server" mainpromt.md describes.
│                          Tools: get_sar_template, get_example, get_master_config, search_evidence
│                          (no get_guideline - guideline lives in master_config.json, not a file)
├── master_agent/
│   ├── master.py             Master Agent = MCP client; runs the full workflow
│   ├── docx_utils.py          python-docx helpers (block iteration, formatting-preserving text replace)
│   ├── template_structure.py  serializes the Document into the Slot Marking Agent's input JSON
│   ├── slot_marking_agent.py  addfeature.md: auto-detects + injects slots (see below)
│   ├── context.py             Example extraction (pymupdf/python-docx) - Guideline is NOT extracted from a file
│   ├── criteria_agent.py      builds the prompt, calls Gemini, validates the JSON response
│   ├── template_injector.py   writes a verified section into its resolved slot
│   └── traceability.py        builds + appends the Traceability Matrix
├── api_server.py         HTTP API wrapping master.run() for the Import Service frontend (see below)
├── master_config.json    criterion order + per-criterion guideline/keywords/required_evidence
├── default.md            backup of PS's real guideline/required_evidence, cleared for testing - restore from here
├── output/               generated .docx files land here
└── test_fixtures/        synthetic template/example/evidence used by scripts/e2e_test.py
```

Master spawns the MCP server as a subprocess over stdio (`python -m
mcp_server.server`) and talks to it via the official `mcp` SDK - a real
client/server split, matching mainpromt.md's "Master ทำหน้าที่เป็น MCP
Client" framing.

Template/Example are opened directly from the bytes MCP hands back
(`docx.Document(io.BytesIO(...))`) - nothing touches disk until the final
`.docx` is exported.

**On ChromaDB**: `mainpromt.md` names ChromaDB as the evidence vector store,
and a later prompt (`changefeature.md` §12) said to move to MongoDB Vector
Search instead - deliberately **not done**; confirmed with the project owner
to keep ChromaDB, since it was already built and tested. See
`../import/README.md`.

**On stdout encoding**: `master.py` forces `sys.stdout.reconfigure(encoding="utf-8")`
at import time. Without it, any `print()` containing Thai text crashes with
`UnicodeEncodeError` on Windows whenever stdout isn't already UTF-8 (e.g. run
via `api_server.py`/uvicorn, or a plain terminal without `PYTHONIOENCODING`
set) - this was hit and fixed while wiring up `api_server.py`.

## Slot Marking Agent (addfeature.md)

Slots used to require hand-editing the template with `{{slot_id}}` markers.
Per addfeature.md, that's now automatic: before the Criteria Processing Loop,
Master serializes the whole template into a Document Structure JSON and asks
a Gemini call (`master_agent/slot_marking_agent.py`) to decide where each
criterion's slots belong - no template editing needed.

1. `template_structure.py:describe_document()` walks the in-memory Document
   and produces:
   ```json
   {
     "paragraphs": [{"p_index": 0, "text": "...", "is_heading": bool, "is_empty": bool}, ...],
     "tables": [{"table_index": 0, "preceding_p_index": 3, "headers": [...], "sample_row": [...]}, ...]
   }
   ```
   (`p_index` matches `document.paragraphs` order, `table_index` matches
   `document.tables` order - not a single interleaved index.)
2. The agent returns `marked_slots`, each with `criterion`, `slot_id`,
   `type` (`narrative`/`table`), `target_type` (`paragraph`/`table`) and
   `target_index` referencing the arrays above. It's told never to mark a
   static/checklist/scoring table - only tables that look like they need
   real per-course data filled in.
3. `slot_marking_agent.py:apply_marks()` snapshots `document.paragraphs` /
   `document.tables` **before** making any edits (so inserting a paragraph
   for one slot can't shift the index another slot still needs), then
   resolves each mark straight to the real Paragraph/Table object -
   returning `dict[slot_id, ResolvedSlot]`. A `{{slot_id}}` /
   `{{table:slot_id}}` tag is also written into the document as a visual
   aid, but the actual downstream linking uses the resolved object
   reference directly, not a text re-scan.
4. The rest of the pipeline (Criteria Agent, verification, injection,
   traceability) consumes `ResolvedSlot` objects unchanged - normally only
   run for verified content (see the bypass warning above for the current
   exception).

A criterion with zero resolved slots is skipped entirely (logged as
`skipped_no_slots`), since a real template will likely only have some
criteria's sections written yet.

## Guideline lives in `master_config.json` (changefeature.md)

Each criterion has `name`, `guideline` (list of rule strings), `keywords`,
`required_evidence` - all data, no code changes needed to tune them:

```json
"PS": {
  "name": "Programme Specification (...)",
  "guideline": ["หลักสูตรระดับปริญญาตรี ต้องมีอาจารย์ผู้รับผิดชอบหลักสูตรไม่น้อยกว่า 5 คน", "..."],
  "keywords": ["อาจารย์ผู้รับผิดชอบหลักสูตร", "..."],
  "required_evidence": ["มคอ.2 หมวดอาจารย์ผู้รับผิดชอบหลักสูตร", "..."]
}
```

- `guideline` - sent to the Criteria Agent as the rules to check Evidence
  against. **Never fabricate AUN-QA guideline text without a real source** -
  leave `[]` if none is available yet (true for P2/P3/P4/P8 currently).
- `keywords` - joined into the `search_evidence` query, and given to the Slot
  Marking Agent as context.
- `required_evidence` - also read by the Criteria Agent (not just
  `guideline`) to judge whether Evidence is sufficient. **Clearing
  `guideline` alone does not relax what the Agent expects** - confirmed live:
  PS still reported `gap_analysis: missing` citing มคอ.2/appointment-order by
  name from `required_evidence` alone, with `guideline` already emptied.
- PS's real `guideline` + `required_evidence` are currently cleared to `[]`
  for testing (Evidence is 14 individual CVs only - no document states an
  aggregate instructor count or appointment order) - the real values are
  backed up in `default.md`. Restore them once that Evidence exists.

## Setup

```bash
cd generator
python -m venv .venv
.venv/Scripts/activate
pip install -r requirements.txt
cp .env.example .env
# MONGODB_URI / CHROMA_HOST / CHROMA_PORT must point at the same Mongo +
# Chroma the Import Service uses. GEMINI_EMBEDDING_MODEL must be identical
# to the Import Service's, or query vectors won't compare meaningfully
# against stored ones.
```

Requires the Import Service's MongoDB (with a real Template/Example already
uploaded through it) and its ChromaDB server (`chroma run --path
../import/backend/chroma_data --port 8001`) to already be running.

## Running - CLI

```bash
python -m master_agent.master
```

Prints Slot Marking Agent progress, then per-criterion progress
(`completed` / `skipped_no_slots` / `FAILED verification`), and on success
the output path under `output/`.

## Running - Web UI (Generate SAR button)

`api_server.py` is a small FastAPI app wrapping `master_agent.master.run()`
so the Import Service frontend's **Generate SAR** page (currently disabled
placeholder) has something to call:

```bash
uvicorn api_server:app --port 8010
```

| Endpoint | Purpose |
| --- | --- |
| `POST /api/generate` | Starts a run in the background, returns `{job_id, status}`. `409` if one is already running (single-run-at-a-time). |
| `GET /api/generate/{job_id}/status` | `{status, error, slot_marking, criteria_progress}` - the latter two read live from `generation_slot_marking_log`/`generation_criteria_log` in Mongo, keyed by `job_id` (passed through as `master.run(run_id=job_id)`). |
| `GET /api/generate/{job_id}/download` | Streams the completed `.docx` once `status: completed`. |

The frontend ([`GenerateSar.jsx`](../import/frontend/src/pages/GenerateSar.jsx))
talks to this via a separate client
([`generatorClient.js`](../import/frontend/src/api/generatorClient.js)),
base URL from `VITE_GENERATOR_API_URL` (`.env`, default
`http://localhost:8010`). It checks `/api/health` on load and shows
"Generator Service is not reachable" instead of crashing if this process
isn't running.

### Turning the Web UI integration off

This integration is a separate process (`api_server.py`) and a separate
frontend module (`generatorClient.js`) - nothing else depends on either.

- **Simplest**: just don't run `uvicorn api_server:app`. The frontend page
  detects this via the health check and disables the button with an
  explanatory message - no code change needed, this is the normal "off"
  state.
- **To remove the button/feature from the UI entirely**: in
  `GenerateSar.jsx`, the button and progress UI are gated by
  `serviceAvailable`/`job` state - reverting to the old static
  "Not Available" placeholder means restoring the original file (the
  Slot Marking Agent, Criteria Agent, verification, etc. are all
  untouched either way; only this one page and `generatorClient.js` are
  Web-UI-specific).

### Turning it back on after disabling

Just start `uvicorn api_server:app --port 8010` again (and make sure
`VITE_API_BASE_URL`'s companion `VITE_GENERATOR_API_URL` in the frontend's
`.env` still points at it) - no code changes needed either way, since
nothing was removed, only not run.

## Testing

- `scripts/test_slot_marking.py` - standalone Slot Marking Agent test against
  `test_fixtures/template_unmarked.docx` (no MCP/Import Service needed, just
  Gemini). Checks a real data table gets a slot and a static checklist table
  does not.
- `scripts/e2e_test.py` - uploads the same unmarked fixtures through a
  running Import Service, runs the full Master Agent (Slot Marking through
  Export), checks the output for injected content, cross-checks that the
  Example's deliberately-wrong fact (a fake instructor count) did **not**
  leak into the output, then deletes the fixtures it uploaded.

```bash
pip install -r requirements-dev.txt
python scripts/test_slot_marking.py
python scripts/e2e_test.py
```

Both have been run against real MongoDB Atlas, real ChromaDB, and real
Gemini and pass (against a synthetic fixture with sufficient Evidence):
automatic slot detection (including correctly skipping a static checklist
table), MCP tool round-trip, Criteria Agent JSON generation, all three
verification gates, narrative + table injection with existing table style
preserved, traceability matrix, MongoDB logging, and Example-fact-leakage
prevention. `api_server.py`'s full HTTP flow (start → poll → download,
including the 409 concurrent-run guard) has also been exercised end-to-end.

## Known gaps / not yet exercised

- **Verification is currently bypassed** - see the warning at the top of
  this file.
- Real run against the real (partial) `template2.docx` + 14 real instructor
  CVs uploaded through the Import Service: Slot Marking correctly finds
  slots in the real document, but PS consistently fails verification even
  with `guideline`/`required_evidence` both cleared - individual CVs don't
  contain the *aggregate* fact PS's narrative needs (e.g. "5 instructors
  total"), so no single Evidence chunk supports a citation for that claim,
  and Gate 1/Gate 2 correctly flag the mismatch. A document that states the
  aggregate directly (มคอ.2, or a standalone appointment-order document) is
  needed - not just more individual CVs.
- The real มคอ.2 file failed to embed during Import (627 chunks): hit a
  Gemini free-tier **per-request token-volume limit** (batches of 35 chunks
  succeeded, 40+ failed deterministically) and, separately, a **sustained
  throughput/per-minute limit** that persisted even at a paced 20-chunk/8-10s
  rate. `../import/backend/app/services/embedding_service.py` was tuned
  against this (batch size 20, wider pacing, more patient retry) but the
  large real file itself hasn't yet succeeded - a paid Gemini tier would
  remove this constrained entirely. See `../import/README.md`.
- Only tested against a template with slots for a single criterion (PS).
  Multi-criterion runs are mechanically identical but haven't run against
  real content for P1-P4/P8 (their `guideline` is still `[]`).
- The Slot Marking Agent has only been tested on a small synthetic template
  and the real partial `template2.docx`. A full-length real SAR template
  would produce a much larger Document Structure JSON - mechanically the
  same call, but unverified at that scale.
- **Table injection only supports "simple" table shapes**: single-row
  header, optional subheader rows dividing groups (e.g. table 1.1's
  "อาจารย์ผู้รับผิดชอบหลักสูตร" / "อาจารย์ประจำหลักสูตร"), one physical row per
  record, with existing numbered/checkbox placeholder rows to fill in place
  (`master_agent/docx_utils.analyze_table_groups`). Table 1.2 in the real
  `template2.docx` does **not** fit this shape - it has a 2-row header (a
  supra-header row plus a real-label row) and each instructor occupies a
  5-physical-row block (one row per year, via a single "พ.ศ." column, not
  separate year columns) - so `slot_marking_agent.apply_marks` deterministically
  skips it (logs `"... skipped - no placeholder rows detected ..."`) rather
  than injecting mis-shapen data into it. Supporting it needs a follow-up
  design pass (multi-row headers + multi-row-per-record blocks), not
  attempted yet.
