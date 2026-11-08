# Generator Service Backend — AUN-QA SAR Generation

The Generator Service's Python backend: Master Agent orchestration, six
Criterion Agents (PS/P1/P2/P3/P4/P8), Retrieval Manager, MCP tool boundary,
Verification, Reference Mapping, Template Injection, and the HTTP API the
`frontend/` React app talks to.

## Architecture

```
React Frontend (../frontend)
      │  HTTP
      ▼
api_server.py (FastAPI)
      │
      ▼
Monitor Readiness (monitor/client.py)
      │
      ▼
master_agent/master.py  (Master Agent)
      │
      ├── criterion_agents/  (PS/P1/P2/P3/P4/P8 - each owns its own prompt/schema/logic)
      │
      ├── retrieval/manager.py  (Retrieval Manager)
      │       ↓
      │   mcp_server/server.py  (MCP tool boundary - the ONLY path to data)
      │       ↓
      │   ChromaDB (BGE-M3, 1024-dim) / MongoDB / Document-OCR (stub)
      │
      ├── common/verification.py       (3 anti-hallucination gates)
      ├── master_agent/traceability.py (Reference Mapping / Traceability Matrix)
      └── master_agent/template_injector.py (Template Injection)
                │
                ▼
          Generated DOCX (output/)
                │
        ┌───────┴────────┐
        ▼                ▼
   document/docx_to_html.py   generated_documents (MongoDB, version history)
   (HTML Preview)                       │
                                        ▼
                              api/routes.py: /api/history, /api/reference
```

Criterion Agents never touch MongoDB/ChromaDB/the filesystem directly -
every real data access goes through Master → Retrieval Manager → MCP →
MCP Tools → ChromaDB/MongoDB/Document-OCR.

## Folder Structure

| Path | Purpose |
|---|---|
| `api_server.py` | FastAPI app: existing generate/status/download endpoints |
| `api/` | New Web workspace endpoints (preview, draft, history, reference) mounted into `api_server.py` |
| `common/` | Config, MongoDB/Chroma clients, schemas, verification, logging |
| `criterion_agents/` | PS/P1/P2/P3/P4/P8, each with its own `agent.py`, `prompt/`, `schema/` |
| `document/` | DOCX → HTML conversion for the Web preview/editor |
| `master_agent/` | Master orchestrator, Slot Marking, Template Structure, Template Injection, Traceability |
| `mcp_server/` | MCP tool server (the only path to ChromaDB/MongoDB/OCR) |
| `monitor/` | Monitor Readiness client (`GET /monitor/{curriculumId}/readiness`) |
| `reference/` | Reference/Traceability API query logic (reads `generation_criteria_log`) |
| `retrieval/` | Retrieval Manager + MongoDB Data-Request mapping |
| `scripts/` | Regression test scripts (run directly, not via pytest) + real-data test entrypoints |
| `test_fixtures/` | Real-template-shaped `.docx` fixtures used by the regression tests |
| `output/` | Generated `.docx` files land here (gitignored except `.gitkeep`) |

## Environment Variables

Copy `.env.example` to `.env` and fill in real values. Never commit `.env`
or `.env.realdata` (already gitignored). Key variables:

- `MONGODB_URI`, `MONGODB_DB_NAME` — the real `aunqa_ps` MongoDB
- `CHROMA_HOST`, `CHROMA_PORT`, `CHROMA_COLLECTION` — real ChromaDB (`document_chunks`)
- `BGE_M3_MODEL` — query-embedding model, must match the Import Service's embedding model (BGE-M3, 1024-dim)
- `GEMINI_API_KEY`, `GEMINI_CRITERIA_MODEL` — Gemini, used only for Criterion Agents' narrative generation
- `TEMPLATE_SERVICE_URL` — real Template Download API (`GET /api/templates/{version}/download`)
- `MONITOR_SERVICE_URL` — real Monitor Readiness API; unset means every `/api/generate` call correctly reports `MONITOR_UNAVAILABLE` and refuses to generate (never a fabricated `READY`)
- `CORS_ORIGINS` — must include the frontend's dev origin (e.g. `http://localhost:5173`)

## Running the Backend

All commands assume the working directory is `backend/` (relative paths -
`.env`, `master_config.json`, `output/`, `test_fixtures/` - resolve from
here):

```bash
cd backend
source ../.venv/bin/activate   # or your own venv with requirements.txt installed
uvicorn api_server:app --port 8010
```

CLI/manual generation (development/test tool only - **not** the production
Web generation path, which always goes through the Monitor-gated
`POST /api/generate`):

```bash
cd backend
python -m master_agent.master
```

## Running Tests

Regression tests are hand-rolled scripts (no pytest), run directly and
checked by their own PASS/FAIL summary + exit code:

```bash
cd backend
python scripts/test_ps_person_aggregation.py
python scripts/test_table_group_injection.py
python scripts/test_traceability_no_heading1.py
python scripts/test_generator_gate.py
python scripts/test_monitor_integration.py
python scripts/test_mongodb_retrieval.py
python scripts/test_slot_marking.py
python scripts/test_slot_map.py          # injection -> slot_map -> HTML ids (offline)
python scripts/test_table_formats.py     # Table 1.1/1.2 first-column formats (numbering, full titles, no duplicated titles)
python scripts/test_education_display.py # Table 1.2 education list: no year, numbering, merge rule, Reference records
python scripts/test_role_ordering.py     # Table 1.1 sections / dual-role first / checkboxes from active appointments (+ live read-only)
python scripts/test_migration.py         # generated_documents migration + per-Version repository (temp DBs only)
python scripts/test_dev_generate_route.py   # dev/prod route wiring + gate (real generation: browser_e2e.py)
python scripts/test_table_1_2_counts.py  # Table 1.2 years/counts, live 13x5 cross-check (read-only)
python scripts/test_lifecycle.py         # Generate/Save/Download lifecycle - uses a TEMPORARY MongoDB
                                         # database aunqa_ps_test_<uuid> (dropped at the end); the
                                         # production DB is only read, never written
```

Real end-to-end generation against real MongoDB/ChromaDB/Gemini/Template
Service: `python -m master_agent.master` (reads `.env` directly) or
`python scripts/test_real_data_generation.py` (development-only, does not
wait for Monitor).

## Document Lifecycle (locked)

```
Generate → Current Generated Artifact      output/SAR_{job}.docx        (NO Version)
Save     → Current Draft                   generation_drafts + output/drafts/   (NO Version)
Download → immutable Version Snapshot      generated_documents.generatedFiles[] + output/versions/
History / old-version Preview / Reference read those snapshots only
```

- **Generate never creates a Version** (`master_agent/master.py` no longer writes `generated_documents`; running the CLI `python -m master_agent.master` therefore creates no History entry either). Generating N times leaves History unchanged.
- **Save** (`PUT /draft`) applies the edited HTML onto a *copy of the generated DOCX* (`document/docx_edit.py`) — the generated file is the structural base; only elements whose text actually changed are rewritten (via the same `set_paragraph_text`/`set_cell_lines` primitives Template Injection uses), so tables, merged cells, vMerge blocks, checkboxes, styles and layout are untouched. An edit that can't be mapped back safely (new/deleted/duplicated paragraph, row or table — e.g. Enter inside a paragraph) → **HTTP 422 `unsupported_edit`**, nothing is saved, the previous draft is unchanged. Formatting-only changes (bold/italic added in the browser) are not persisted.
- **Download** (`api/versioning.py`) snapshots the latest saved draft DOCX (or the generated DOCX if none) into a new unique file and appends **one** element to `generatedFiles[]`. **Every explicit Download creates a new Version** (even with no change in between). The backend assigns the number (`X-Document-Version`, exposed to browsers via CORS `expose_headers`); the frontend never computes it.
- `generated_documents` is History only and holds **one MongoDB document per Version** (never an array): `{_id, curriculumId, fileName, fileType, version, path, timestamp, runId, source:"download", userEdits[]}`. Download only INSERTS a new document; nothing ever updates or deletes a Version document. The next number is read from the database (max `version` for the curriculum + 1, no in-memory counter) and a unique partial index `(curriculumId, version)` makes a duplicate number impossible (a racing Download recomputes). Migrated pre-existing Versions have no `runId`/`source`/`userEdits`; their run id still comes from the `SAR_{run_id}.docx` file name.
- **Migration (explicit, never at startup):** `python scripts/migrate_generated_documents.py [--dry-run] [--keep-legacy]` converts the old single array-based document into N Version documents. It writes a JSON backup first, only inserts, verifies every Version field-by-field (and file hashes) and only then removes the old document; running it again reports "already migrated". Until it has been run the API answers **503 `migration_required`** instead of showing an empty History.
- A generation job (`job_id`/`run_id`) is **not** a Version: Version is assigned only when Download creates the snapshot.

### PS Table 1.1 / 1.2 first-column format (presentation only)
- **Table 1.1 sections come from the real `appointments`** (current curriculum, `status == "active"` only - inactive/ended/other-curriculum appointments never decide a role): "อาจารย์ผู้รับผิดชอบหลักสูตร" lists everyone with `programmeResponsible`; "อาจารย์ประจำหลักสูตร" lists everyone with `programmeStaff`, and the people who ALSO hold `programmeResponsible` come first (so a dual-role person appears in both sections). No head-count or names are hardcoded (`table_1_1_members`). Inside each block the order is the system's existing canonical order (personId ascending): `appointmentOrder`/`effectiveDate` are free text and identical for every appointment of one appointment order, so they cannot rank people. Table 1.2 checkboxes use the same active roles. `python scripts/audit_roles.py [--raw ...]` prints the role audit.
- Table 1.1 "ตำแหน่งทางวิชาการ": `N. <full title>` - N restarts at 1 in each section; full title from an explicit map (`รศ.`→รองศาสตราจารย์, `ผศ.`→ผู้ช่วยศาสตราจารย์, `อ.`→อาจารย์, `ศ.`→ศาสตราจารย์); any other source value is shown as-is (never invented). The name / education / degree / field columns are unchanged.
- Table 1.2 "ตำแหน่งทางวิชาการ ชื่อ-สกุล": `N. <position abbr><ดร.><name>` (e.g. `1. รศ.ดร.พีรวิชญ์ เควด`), N = record order; titles already written in the source name are removed first so nothing is duplicated. Yearly counts are untouched.
- Table 1.2 "วุฒิการศึกษา (ทุกระดับ)": one numbered line per retained education item, `N. <degree> <field>` exactly as stored - **no graduation year** (it stays in the source record/Reference), meaningful parentheses such as `ปรัชญาดุษฎีบัณฑิต (วิทยาศาสตร์เชิงคำนวณ)` kept, plain `1.` `2.` numbering (never `2\.`). Records without a recognizable degree (OCR junk) are not education and are not shown. Code: `criterion_agents/ps_agent/education_display.py`.
- **Duplicates (within ONE person only):** records are one logical education only when they have the same degree abbreviation, graduation year and institution *name* (before any "/" country suffix) AND either the same field after normalization (NFKC, no whitespace/dots) OR one field is the other's written out as `<full degree name> (<field>)` with a degree-name level equal to the degree's level (e.g. `ปร.ด. | X` + `ปร.ด. | ปรัชญาดุษฎีบัณฑิต (X)`; OCR-tolerant on the parenthesized field). The plain representation is shown. The earliest record's text is shown once and **every** underlying record stays cited (Reference lists them all). Anything not proven by those fields (faculty suffix, a one-letter degree variant such as `วท.บ.`/`วบ.บ.`, different year/institution) is NOT merged. Records of different persons are never compared or merged. Nothing is deleted or modified in MongoDB. `python scripts/audit_education.py [--raw output/audit/raw_<run>.json]` is the read-only global audit (Level A within person, Level B across persons, classification C/D/N/A/B/E, source-vs-generator trace).
- The generated DOCX contains SAR content only: **no Traceability Matrix table** (traceability lives in `generation_criteria_log`, `slot_map`, the Reference API and the Web Reference page).
- Numbers exist only in the generated document; nothing is written to MongoDB. Code: `criterion_agents/ps_agent/academic_position.py`, `_build_table_1_1/_build_table_1_2`.

### Stable element identity & User Edit traceability
- Preview HTML carries positional ids (`data-block`, `data-table-id`, `data-row`, `data-col`) — the DOCX-body position the element came from. When the run's `slot_map` exists (written at export into `generation_slot_marking_log.slot_map`, additive) mapped elements also get `data-slot-id`/`data-section`, and `data-reference-id` only where a real Reference item exists. Nothing is invented; no DB ids/secrets are emitted. Attribution on the server uses its own slot_map, never client-supplied attributes.
- On Download the changed elements (vs. the generated DOCX) are frozen into that Version's `userEdits`. Reference for Version N = `generation_criteria_log(runId)` + `userEdits(N)`:
  - real source mapping → `sourceType`/`sourceReference` stay the **original** source (mongodb/chroma), plus `originalValue`, `currentValue`, `userEdited: true` (the source is never presented as having produced the edit);
  - no real mapping → `sourceType: "user_edit"`, `userEdited: true`, **no** `sourceReference`; listed under the "User Edits (unattributed)" node.
- User edits never write to Source Data (curricula, persons, educations, appointments, academic_works, documents, ps_requirements, data_usages).

## API Endpoints

- `GET /api/health`
- `POST /api/generate` — Monitor-gated; body `{curriculum_id}`; creates a generation job only
- `GET /api/generate/{job_id}/status`
- `GET /api/generate/{job_id}/preview` — `{html, fromDraft}`: Current Draft HTML if saved, otherwise the generated document's HTML
- `PUT /api/generate/{job_id}/draft` — body `{html}`; saves the Current Draft (edited DOCX). 422 `unsupported_edit` if it can't be converted back
- `GET /api/generate/{job_id}/download` — **creates a Version Snapshot** and returns it; version number in `X-Document-Version`
- `GET /api/history`, `GET /api/history/{version}/preview`, `GET /api/history/{version}/download` — Download-created snapshots (plus pre-existing versions)
- `GET /api/reference?version=N`, `GET /api/reference/item/{item_id}?version=N` — version-aware Reference (incl. that version's user edits)
- `GET /api/curriculum`, `GET /api/template/latest`

### Known Limitations
- `_jobs` (job → output path) is in-memory: after an `api_server.py` restart a completed job can no longer be previewed/saved/downloaded (unchanged from before). Versions and drafts already stored are unaffected.
- Not supported by Save (→ 422): adding/removing paragraphs, rows, cells or tables. Text edits of existing paragraphs/headings/list items/cells and checkbox state are supported.
- Document/OCR source type is still a stub (no live citations).
- The real Generate → Monitor path can't run end-to-end until `MONITOR_SERVICE_URL` is configured (intentional gate).

## Development/Test real generation from the Web (Monitor not connected yet)

Two entry gates, ONE Generator core (`api_server._new_job -> _start_job -> _execute -> master_agent.master.run`):

| Route | Gate | When it exists |
|---|---|---|
| `POST /api/generate` | Monitor READY (`generatedReady`) -> 412 otherwise | always (production) |
| `POST /api/dev/generate` | none (Development/Test) | only if the process is started with `GENERATOR_DEV_MODE=true` |

`/api/dev/generate` runs the real Master, Criterion Agents, Retrieval Manager, MCP, ChromaDB, MongoDB, Verification, Reference Mapping and Template Injection - the same result production will produce; only the Monitor gate is skipped. It is **not** registered by default, the process **refuses to start** if `GENERATOR_DEV_MODE=true` is combined with `MONITOR_SERVICE_URL`, and the production route is untouched (still 412 without a Monitor). Status/preview/draft/download/history/reference are the shared routes, so Generate -> Save -> Download -> Version -> History -> Reference behave identically.

```bash
# backend (real DBs from .env)
cd backend && GENERATOR_DEV_MODE=true uvicorn api_server:app --port 8010
# frontend: real API + explicit dev generate
cd frontend && VITE_USE_MOCK_API=false VITE_DEV_GENERATE=true npm run dev
```

The Generate page then shows "Mode: Development/Test - real Generator via /api/dev/generate". Without `VITE_DEV_GENERATE=true` the button calls the production route (412 until a Monitor is READY); without `VITE_USE_MOCK_API=false` it uses the mock adapters (banner "MOCK API"). There is no automatic fallback between the three.

**Side effects when run against the real `.env` database:** Generate writes `generation_*` logs, Save writes `generation_drafts`, and every Download appends a Version to the real `generated_documents`. Source collections are only read. For a throw-away run use `scripts/browser_e2e.py` (temporary DB) instead.

## Monitor Readiness

`POST /api/generate` is gated behind a real `GET /monitor/{curriculumId}/readiness` call (`monitor/client.py`). With `MONITOR_SERVICE_URL` unset, every call correctly reports `MONITOR_UNAVAILABLE` and refuses to generate — this is intentional, honest behavior, not a bug, and this gate was **not** weakened or bypassed for this reorganization (see `scripts/test_generator_gate.py`'s 11 regression checks). The frontend's mock adapter (`frontend/src/services/mock/`) is what currently exercises the Generate flow end-to-end in standalone Development Mode.
