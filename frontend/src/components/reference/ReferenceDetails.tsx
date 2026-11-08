import type { ReferenceItem } from "../../types/reference";
import { SourceBadge } from "./SourceBadge";
import "./ReferenceDetails.css";

export function ReferenceDetails({ item }: { item: ReferenceItem | null }) {
  if (!item) {
    return <p className="text-muted reference-details__empty">เลือก field ทางซ้ายเพื่อดูรายละเอียด</p>;
  }

  const ref = item.sourceReference;
  const originalDocuments = [ref, ...(item.sourceReferences ?? [])]
    .flatMap((source) => source?.originalDocuments ?? [])
    .filter((document, index, all) => all.findIndex((candidate) => candidate.documentId === document.documentId) === index);
  // Real backend: an edited field keeps its ORIGINAL source (badge/reference
  // below) and reports originalValue + currentValue; an edit with no real
  // source mapping has source "user_edit" and no reference at all.
  const edited = item.userEdited === true && item.originalValue !== undefined;

  return (
    <div className="reference-details">
      <div className="reference-details__row">
        <span className="reference-details__label">Field</span>
        <span className="reference-details__value">{item.field}</span>
      </div>

      {edited ? (
        <>
          <div className="reference-details__row">
            <span className="reference-details__label">
              {item.source === "user_edit" ? "Generated Value" : "Original Source"}
            </span>
            <span className="reference-details__value">{item.originalValue}</span>
          </div>
          <div className="reference-details__row">
            <span className="reference-details__label">User Edit</span>
            <span className="reference-details__value">{item.currentValue ?? item.value}</span>
          </div>
        </>
      ) : item.source === "user_edit" && item.originalSourceValue !== undefined ? (
        <>
          <div className="reference-details__row">
            <span className="reference-details__label">Original Source</span>
            <span className="reference-details__value">{item.originalSourceValue}</span>
          </div>
          <div className="reference-details__row">
            <span className="reference-details__label">User Edit</span>
            <span className="reference-details__value">{item.value}</span>
          </div>
        </>
      ) : (
        <div className="reference-details__row">
          <span className="reference-details__label">Value</span>
          <span className="reference-details__value">{item.value}</span>
        </div>
      )}

      <div className="reference-details__row">
        <span className="reference-details__label">Source</span>
        <SourceBadge source={item.source} />
      </div>

      {ref?.documentId && (
        <div className="reference-details__row">
          <span className="reference-details__label">Document</span>
          <span className="reference-details__value">{ref.documentId}</span>
        </div>
      )}
      {ref?.page !== undefined && (
        <div className="reference-details__row">
          <span className="reference-details__label">Page</span>
          <span className="reference-details__value">{ref.page}</span>
        </div>
      )}
      {ref?.chunkIndex !== undefined && (
        <div className="reference-details__row">
          <span className="reference-details__label">Chunk</span>
          <span className="reference-details__value">{ref.chunkIndex}</span>
        </div>
      )}
      {ref?.collection && (
        <div className="reference-details__row">
          <span className="reference-details__label">Collection</span>
          <span className="reference-details__value">{ref.collection}</span>
        </div>
      )}
      {ref?.recordId && !ref?.personId && (
        <div className="reference-details__row">
          <span className="reference-details__label">Record ID</span>
          <span className="reference-details__value">{ref.recordId}</span>
        </div>
      )}
      {item.sourceReferences && item.sourceReferences.length > 1 && (
        <div className="reference-details__row reference-details__row--list">
          <span className="reference-details__label">Source records ({item.sourceReferences.length})</span>
          <ul className="reference-details__records">
            {item.sourceReferences.map((r, index) => (
              <li key={`${r.collection ?? r.documentId}-${r.recordId ?? r.chunkIndex}-${index}`} className="reference-details__value">
                {[r.collection, r.recordId ?? r.documentId, r.chunkIndex !== undefined && !r.recordId ? `chunk ${r.chunkIndex}` : null]
                  .filter(Boolean)
                  .join(" · ")}
              </li>
            ))}
          </ul>
        </div>
      )}
      {ref?.personId && (
        <div className="reference-details__row">
          <span className="reference-details__label">Person ID</span>
          <span className="reference-details__value">{ref.personId}</span>
        </div>
      )}
      {originalDocuments.length > 0 && (
        <div className="reference-details__row">
          <span className="reference-details__label">เอกสารต้นฉบับ</span>
          <div className="reference-details__documents">
            {originalDocuments.map((document) => (
              <a
                key={document.documentId}
                className="reference-details__document-link"
                href={`/api/import/documents/${encodeURIComponent(document.documentId)}/file`}
                target="_blank"
                rel="noreferrer"
              >
                ดูไฟล์ต้นฉบับ: {document.fileName}
                {document.pageNumbers?.length ? ` (หน้า ${document.pageNumbers.join(", ")})` : ""} ↗
              </a>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
