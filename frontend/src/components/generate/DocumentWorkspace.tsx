import { useState } from "react";
import type { GeneratedDocument } from "../../types/document";
import { useDocument } from "../../hooks/useDocument";
import { useUnsavedChangesGuard } from "../../hooks/useUnsavedChangesGuard";
import { DocumentToolbar } from "./DocumentToolbar";
import { DocumentViewer } from "./DocumentViewer";
import { DocumentEditor } from "./DocumentEditor";
import { UnsavedChangesDialog } from "./UnsavedChangesDialog";
import "./DocumentWorkspace.css";

export function DocumentWorkspace({
  document: initialDocument,
  onDownloaded,
}: {
  document: GeneratedDocument;
  onDownloaded?: () => void;
}) {
  const doc = useDocument(initialDocument);
  const blocker = useUnsavedChangesGuard(doc.status === "unsaved");
  const [downloadNotice, setDownloadNotice] = useState<number | null>(null);

  const handleDownload = async () => {
    const version = await doc.download();
    if (version !== null) {
      setDownloadNotice(version);
      onDownloaded?.();
    }
  };

  return (
    <section className="document-workspace">
      <DocumentToolbar
        fileName={initialDocument.fileName}
        draftStatus={doc.status}
        lastSavedAt={doc.lastSavedAt}
        isEditing={doc.isEditing}
        saving={doc.saving}
        downloading={doc.downloading}
        onEdit={() => doc.setIsEditing(true)}
        onSave={() => void doc.save()}
        onCancel={doc.cancelEdit}
        onDownload={() => void handleDownload()}
      />

      {doc.saveError && <p className="document-workspace__error">{doc.saveError}</p>}
      {doc.downloadError && <p className="document-workspace__error">{doc.downloadError}</p>}
      {downloadNotice !== null && (
        <p className="document-workspace__notice">Downloaded as Version {downloadNotice}.</p>
      )}

      <div className="document-workspace__content surface">
        {doc.isEditing ? (
          <DocumentEditor html={doc.draftHtml} onChange={doc.updateDraft} />
        ) : (
          <DocumentViewer html={doc.draftHtml} />
        )}
      </div>

      <UnsavedChangesDialog
        open={blocker.state === "blocked"}
        onStay={() => blocker.state === "blocked" && blocker.reset()}
        onLeave={() => blocker.state === "blocked" && blocker.proceed()}
      />
    </section>
  );
}
