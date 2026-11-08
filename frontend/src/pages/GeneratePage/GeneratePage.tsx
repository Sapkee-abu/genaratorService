import { useEffect, useState } from "react";
import { generatorApi } from "../../services/generatorApi";
import { useGenerate } from "../../hooks/useGenerate";
import { GenerateForm } from "../../components/generate/GenerateForm";
import { GenerateProgress } from "../../components/generate/GenerateProgress";
import { DocumentWorkspace } from "../../components/generate/DocumentWorkspace";
import type { CurriculumSummary, TemplateSummary } from "../../types/document";
import "./GeneratePage.css";

export function GeneratePage() {
  const { status, steps, document, error, start, retry } = useGenerate();
  const [curriculum, setCurriculum] = useState<CurriculumSummary | null>(null);
  const [template, setTemplate] = useState<TemplateSummary | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([generatorApi.getCurriculum(), generatorApi.getLatestTemplate()])
      .then(([curriculumResult, templateResult]) => {
        if (cancelled) return;
        setCurriculum(curriculumResult);
        setTemplate(templateResult);
      })
      .catch((err: unknown) => {
        if (!cancelled) setLoadError(err instanceof Error ? err.message : "โหลดข้อมูลเริ่มต้นไม่สำเร็จ");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (status === "success" && document) {
    return (
      <div className="generate-page">
        <DocumentWorkspace document={document} />
      </div>
    );
  }

  if (status === "generating") {
    return (
      <div className="generate-page">
        <GenerateProgress steps={steps} />
      </div>
    );
  }

  if (status === "error") {
    return (
      <div className="generate-page">
        <div className="generate-page__error surface">
          <p className="generate-page__error-title">Generation Failed</p>
          <p>ไม่สามารถสร้างเอกสารได้</p>
          <p>กรุณาลองใหม่อีกครั้ง</p>
          {error && <p className="text-muted">{error}</p>}
          <button className="btn btn-primary" onClick={() => curriculum && retry(curriculum.id)}>
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="generate-page">
      {loadError && <p className="generate-page__load-error">{loadError}</p>}
      <GenerateForm
        curriculum={curriculum}
        template={template}
        onGenerate={() => curriculum && start(curriculum.id)}
        disabled={!curriculum || !template || !template.fileName.toLowerCase().endsWith(".docx")}
      />
    </div>
  );
}
