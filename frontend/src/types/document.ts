export type GenerationStatus = "idle" | "generating" | "success" | "error";

export type DraftStatus = "saved" | "unsaved";

export type GenerationStepKey =
  | "load_template"
  | "parse_template"
  | "build_structure"
  | "generate_criterion"
  | "verification"
  | "reference_mapping"
  | "template_injection"
  | "prepare_preview";

export type GenerationStepState = "done" | "active" | "pending";

export interface GenerationStep {
  key: GenerationStepKey;
  label: string;
  status: GenerationStepState;
}

export interface GeneratedDocument {
  id: string;
  fileName: string;
  html: string;
  status: DraftStatus;
  lastSavedAt?: string;
}

/** change.md/create.md sec.39 - future Monitor gate, unused (ready is
 * always true) until a real Monitor integration is wired in. */
export interface GenerationGate {
  ready: boolean;
  source?: "monitor";
}

export interface CurriculumSummary {
  id: string;
  code: string;
  name: string;
}

export interface TemplateSummary {
  version: number;
  fileName: string;
}
