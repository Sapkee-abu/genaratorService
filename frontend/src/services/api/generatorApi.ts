import type { GeneratorApi, GenerationStatusResult } from "../contracts";
import { GENERATE_PATH } from "../config";
import { getBlob, getJson, postJson, putJson } from "../httpClient";
import type { GenerationStep, GenerationStepKey } from "../../types/document";

/** Real backend (backend/api_server.py + backend/api/routes.py). All 5
 * contract methods are now backed by real endpoints:
 * - getCurriculum -> GET /api/curriculum
 * - getLatestTemplate -> GET /api/template/latest
 * - generate -> POST /api/generate (Monitor-gated - see backend/README.md;
 *   will return HTTP 412 without a real Monitor configured, which is the
 *   honest, expected state, not a bug in this adapter). With the explicit
 *   Development/Test switch VITE_DEV_GENERATE=true it posts to
 *   /api/dev/generate instead (same real Generator, no Monitor gate) - see
 *   services/config.ts. Errors from either route are shown as-is.
 * - getGenerationStatus -> GET /api/generate/{job_id}/status +
 *   GET /api/generate/{job_id}/preview (once completed)
 * - saveDraft -> PUT /api/generate/{job_id}/draft
 * - download -> GET /api/generate/{job_id}/download. Download IS the
 *   Version Snapshot action (fix.md): the backend creates the immutable
 *   Version from the latest saved draft (or the generated document) and
 *   returns its number in the X-Document-Version header - never invented or
 *   counted client-side.
 * - saveDraft errors: HTTP 422 (unsupported_edit) carries a readable
 *   `detail.message`, surfaced by httpClient as the thrown Error's message.
 */

const STEP_DEFINITIONS: { key: GenerationStepKey; label: string }[] = [
  { key: "load_template", label: "Load Template" },
  { key: "parse_template", label: "Parse Template" },
  { key: "build_structure", label: "Build Template Structure" },
  { key: "generate_criterion", label: "Generate Criterion" },
  { key: "verification", label: "Verification" },
  { key: "reference_mapping", label: "Reference Mapping" },
  { key: "template_injection", label: "Template Injection" },
  { key: "prepare_preview", label: "Prepare Preview" },
];

interface RealStatusResponse {
  job_id: string;
  status: "running" | "completed" | "failed";
  error: string | null;
  slot_marking: unknown | null;
  criteria_progress: unknown[];
}

function stepsFromRealStatus(body: RealStatusResponse): GenerationStep[] {
  // Best-effort mapping: the real status endpoint only exposes
  // slot_marking presence and criteria_progress length, not per-stage
  // granularity (no verification/reference-mapping/injection sub-status
  // exists in that response yet).
  const hasSlotMarking = body.slot_marking != null;
  const criteriaStarted = body.criteria_progress.length > 0;
  const isDone = body.status === "completed";

  return STEP_DEFINITIONS.map((def, index) => {
    if (isDone) return { ...def, status: "done" as const };
    if (index === 0 || index === 1 || index === 2) {
      return { ...def, status: hasSlotMarking ? ("done" as const) : index === 0 ? ("active" as const) : ("pending" as const) };
    }
    if (index === 3) return { ...def, status: criteriaStarted ? ("active" as const) : ("pending" as const) };
    return { ...def, status: "pending" as const };
  });
}

export const realGeneratorApi: GeneratorApi = {
  async getCurriculum() {
    return getJson("/api/curriculum");
  },

  async getLatestTemplate() {
    return getJson("/api/template/latest");
  },

  async generate(curriculumId: string) {
    const response = await postJson<{ job_id: string; status: string }>(GENERATE_PATH, {
      curriculum_id: curriculumId,
    });
    return { jobId: response.job_id };
  },

  async getGenerationStatus(jobId: string): Promise<GenerationStatusResult> {
    const body = await getJson<RealStatusResponse>(`/api/generate/${jobId}/status`);

    let document: GenerationStatusResult["document"];
    if (body.status === "completed") {
      const preview = await getJson<{ html: string; fromDraft: boolean }>(`/api/generate/${jobId}/preview`);
      document = {
        id: jobId,
        fileName: `SAR_${jobId}.docx`,
        html: preview.html,
        status: preview.fromDraft ? "saved" : "unsaved",
      };
    }

    return {
      status: body.status,
      steps: stepsFromRealStatus(body),
      error: body.error ?? undefined,
      document,
    };
  },

  async saveDraft(documentId: string, html: string) {
    const response = await putJson<{ savedAt: string }>(`/api/generate/${documentId}/draft`, { html });
    return { savedAt: response.savedAt };
  },

  async download(documentId: string) {
    const { blob, headers } = await getBlob(`/api/generate/${documentId}/download`);
    const versionHeader = headers.get("X-Document-Version");
    const version = versionHeader ? Number(versionHeader) : null;
    if (version === null) {
      throw new Error(
        "ดาวน์โหลดไฟล์ได้ แต่ Backend ไม่ได้ส่งเลข Version กลับมาใน header X-Document-Version " +
          "(ตรวจสอบว่า Backend เปิด CORS expose_headers สำหรับ header นี้)"
      );
    }
    return { version, blob };
  },
};
