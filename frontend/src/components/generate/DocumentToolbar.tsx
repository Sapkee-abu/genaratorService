import type { DraftStatus } from "../../types/document";
import "./DocumentToolbar.css";

interface Props {
  fileName: string;
  draftStatus: DraftStatus;
  lastSavedAt?: string;
  isEditing: boolean;
  saving: boolean;
  downloading: boolean;
  onEdit: () => void;
  onSave: () => void;
  onCancel: () => void;
  onDownload: () => void;
}

function formatTimestamp(value?: string): string {
  if (!value) return "—";
  try {
    return new Intl.DateTimeFormat("en-GB", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(value));
  } catch {
    return value;
  }
}

export function DocumentToolbar({
  fileName,
  draftStatus,
  lastSavedAt,
  isEditing,
  saving,
  downloading,
  onEdit,
  onSave,
  onCancel,
  onDownload,
}: Props) {
  return (
    <div className="document-toolbar surface">
      <div className="document-toolbar__info">
        <span className="document-toolbar__filename">{fileName}</span>
        <span className="document-toolbar__meta">
          Status: Current Draft &nbsp;·&nbsp; Last saved: {formatTimestamp(lastSavedAt)}
        </span>
        <span
          className={
            "document-toolbar__draft-state " +
            (draftStatus === "unsaved" ? "document-toolbar__draft-state--unsaved" : "")
          }
        >
          {draftStatus === "unsaved" ? "● Unsaved changes" : "✓ Saved"}
        </span>
      </div>

      <div className="document-toolbar__actions">
        {isEditing ? (
          <>
            <button className="btn btn-primary" onClick={onSave} disabled={saving}>
              {saving ? "Saving..." : "Save"}
            </button>
            <button className="btn" onClick={onCancel} disabled={saving}>
              Cancel
            </button>
          </>
        ) : (
          <>
            <button className="btn" onClick={onEdit}>
              Edit
            </button>
            <button className="btn btn-primary" onClick={onDownload} disabled={downloading}>
              {downloading ? "Downloading..." : "Download"}
            </button>
          </>
        )}
      </div>
    </div>
  );
}
