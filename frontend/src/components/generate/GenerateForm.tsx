import type { CurriculumSummary, TemplateSummary } from "../../types/document";
import { GENERATE_PATH, USE_DEV_GENERATE, USE_MOCK_API } from "../../services/config";
import "./GenerateForm.css";

interface Props {
  curriculum: CurriculumSummary | null;
  template: TemplateSummary | null;
  onGenerate: () => void;
  disabled?: boolean;
}

export function GenerateForm({ curriculum, template, onGenerate, disabled }: Props) {
  return (
    <section className="generate-form surface">
      <h1 className="generate-form__title">Generate SAR</h1>

      {USE_MOCK_API ? (
        <p className="generate-form__mode text-muted">Mode: MOCK API (no real generation)</p>
      ) : USE_DEV_GENERATE ? (
        <p className="generate-form__mode text-muted" data-generate-path={GENERATE_PATH}>
          Mode: Development/Test - real Generator via {GENERATE_PATH} (Monitor gate bypassed)
        </p>
      ) : null}

      <div className="generate-form__field">
        <span className="generate-form__label">ชื่อหลักสูตร</span>
        <span className="generate-form__value">{curriculum?.name ?? "—"}</span>
      </div>

      <div className="generate-form__field">
        <span className="generate-form__label">รหัสหลักสูตร</span>
        <span className="generate-form__value">{curriculum?.code || "—"}</span>
      </div>

      <div className="generate-form__field">
        <span className="generate-form__label">Template</span>
        <span className="generate-form__value">
          {template ? `Latest Template (v${template.version})` : "—"}
        </span>
      </div>

      <button className="btn btn-primary generate-form__button" onClick={onGenerate} disabled={disabled}>
        Generate
      </button>
    </section>
  );
}
