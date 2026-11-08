import type { GeneratorApi, GenerationStatusResult } from "../contracts";
import type { GenerationStep, GenerationStepKey } from "../../types/document";
import { addVersion } from "./mockStore";

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

const MOCK_HTML = `
<h1>2.1 PS การบริหารหลักสูตรตามเกณฑ์มาตรฐานหลักสูตร</h1>
<p>หลักสูตรมีการดำเนินงานตามเกณฑ์มาตรฐาน [1] โดยมีอาจารย์ผู้รับผิดชอบหลักสูตรครบตามที่กำหนด</p>
<table>
  <thead>
    <tr><th>ตำแหน่งทางวิชาการ</th><th>ชื่อ-นามสกุล</th><th>วุฒิการศึกษาสูงสุด</th><th>ชื่อปริญญา (สาขาวิชา)</th></tr>
  </thead>
  <tbody>
    <tr><td>รศ.</td><td>ดร.พีรวิชญ์ เควด</td><td>ปริญญาเอก</td><td>ปร.ด. วิทยาศาสตร์เชิงคำนวณ</td></tr>
    <tr><td>ผศ.</td><td>ดร.สุภาภรณ์ ใจรังษี</td><td>ปริญญาเอก</td><td>Ph.D. Informatics</td></tr>
  </tbody>
</table>
<p>สรุปคะแนนการประเมินตนเองตามเกณฑ์ PS: <input type="checkbox" checked disabled /> ผ่านเกณฑ์ PS</p>
`;

interface MockJobState {
  startedAt: number;
  document: {
    id: string;
    fileName: string;
    html: string;
    status: "saved" | "unsaved";
    lastSavedAt?: string;
  };
}

const jobs = new Map<string, MockJobState>();
const STEP_INTERVAL_MS = 700;

function stepsAtElapsed(elapsedMs: number): GenerationStep[] {
  const doneCount = Math.min(STEP_DEFINITIONS.length, Math.floor(elapsedMs / STEP_INTERVAL_MS));
  return STEP_DEFINITIONS.map((def, index) => ({
    ...def,
    status: index < doneCount ? "done" : index === doneCount ? "active" : "pending",
  }));
}

export const mockGeneratorApi: GeneratorApi = {
  async getCurriculum() {
    return { id: "mock-curriculum-1", code: "25500231104894", name: "วิทยาศาสตรบัณฑิต สาขาเทคโนโลยีสารสนเทศอัจฉริยะ" };
  },

  async getLatestTemplate() {
    return { version: 2, fileName: "template2 (1).docx" };
  },

  async generate() {
    const jobId = `mock-job-${Date.now()}`;
    jobs.set(jobId, {
      startedAt: Date.now(),
      document: {
        id: jobId,
        fileName: "SAR_2569.docx",
        html: MOCK_HTML,
        status: "unsaved",
      },
    });
    return { jobId };
  },

  async getGenerationStatus(jobId: string): Promise<GenerationStatusResult> {
    const job = jobs.get(jobId);
    if (!job) throw new Error("ไม่พบงาน Generate นี้");

    const elapsed = Date.now() - job.startedAt;
    const steps = stepsAtElapsed(elapsed);
    const allDone = steps.every((s) => s.status === "done");

    return {
      status: allDone ? "completed" : "running",
      steps,
      document: allDone
        ? { ...job.document, status: job.document.status, lastSavedAt: job.document.lastSavedAt }
        : undefined,
    };
  },

  async saveDraft(documentId: string, html: string) {
    const job = jobs.get(documentId);
    const savedAt = new Date().toISOString();
    if (job) {
      job.document.html = html;
      job.document.status = "saved";
      job.document.lastSavedAt = savedAt;
    }
    return { savedAt };
  },

  async download(documentId: string) {
    const job = jobs.get(documentId);
    if (!job) throw new Error("ไม่พบเอกสารนี้");
    const record = addVersion(job.document.html);
    const blob = new Blob([job.document.html], { type: "application/octet-stream" });
    return { version: record.version, blob };
  },
};
