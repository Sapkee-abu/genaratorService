import type { ReferenceSourceType } from "../../types/reference";
import "./SourceBadge.css";

const LABELS: Record<ReferenceSourceType, string> = {
  chroma: "ChromaDB",
  mongodb: "MongoDB",
  document_ocr: "Document/OCR",
  user_edit: "User Edit",
};

export function SourceBadge({ source }: { source: ReferenceSourceType }) {
  return (
    <span className={`source-badge source-badge--${source}`}>
      <span className="source-badge__dot" aria-hidden="true" />
      {LABELS[source]}
    </span>
  );
}
