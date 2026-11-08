import "./UnsavedChangesDialog.css";

interface Props {
  open: boolean;
  onStay: () => void;
  onLeave: () => void;
}

/** create.md sec.13 - only ever rendered/opened when there really are
 * unsaved changes; callers must not open this when draftStatus is
 * "saved". */
export function UnsavedChangesDialog({ open, onStay, onLeave }: Props) {
  if (!open) return null;
  return (
    <div className="unsaved-dialog__backdrop" role="presentation">
      <div className="unsaved-dialog surface" role="alertdialog" aria-modal="true" aria-label="Unsaved changes">
        <p>You have unsaved changes. Leave without saving?</p>
        <div className="unsaved-dialog__actions">
          <button className="btn" onClick={onStay}>
            Stay
          </button>
          <button className="btn btn-primary" onClick={onLeave}>
            Leave without saving
          </button>
        </div>
      </div>
    </div>
  );
}
