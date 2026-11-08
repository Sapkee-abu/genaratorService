import type { CurriculumSummary, GeneratedDocument, GenerationStep, TemplateSummary } from "../types/document";
import type { DocumentHistory } from "../types/history";
import type { ReferenceItem, ReferenceTree } from "../types/reference";

/** create.md sec.26 - the ONE contract every component/hook talks to;
 * services/api and services/mock each provide one implementation, chosen
 * by services/generatorApi.ts (etc) - components never know which. */
export interface GeneratorApi {
  getCurriculum(): Promise<CurriculumSummary>;
  getLatestTemplate(): Promise<TemplateSummary>;
  generate(curriculumId: string): Promise<{ jobId: string }>;
  getGenerationStatus(jobId: string): Promise<GenerationStatusResult>;
  saveDraft(documentId: string, html: string): Promise<{ savedAt: string }>;
  download(documentId: string): Promise<{ version: number; blob: Blob }>;
}

export interface GenerationStatusResult {
  status: "running" | "completed" | "failed";
  steps: GenerationStep[];
  error?: string;
  document?: GeneratedDocument;
}

export interface HistoryApi {
  getHistory(): Promise<DocumentHistory>;
  previewVersion(version: number): Promise<GeneratedDocument>;
  downloadVersion(version: number): Promise<Blob>;
}

export interface ReferenceApi {
  getReferenceTree(version?: number): Promise<ReferenceTree>;
  getReferenceItem(id: string, version?: number): Promise<ReferenceItem>;
}
