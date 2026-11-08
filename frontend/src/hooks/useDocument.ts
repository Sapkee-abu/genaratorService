import { useCallback, useState } from "react";
import { generatorApi } from "../services/generatorApi";
import type { DraftStatus, GeneratedDocument } from "../types/document";

/** create.md sec.11/29/30 - single source of truth for the document being
 * edited (`documentDraft`). Save = "Current Draft" only, never a Version;
 * Download is the only thing that creates a Version (useDocument doesn't
 * do that itself - see DocumentWorkspace, which also calls historyApi to
 * refresh after a download). */
export function useDocument(initial: GeneratedDocument) {
  const [draftHtml, setDraftHtml] = useState(initial.html);
  const [status, setStatus] = useState<DraftStatus>(initial.status);
  const [lastSavedAt, setLastSavedAt] = useState<string | undefined>(initial.lastSavedAt);
  const [isEditing, setIsEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const updateDraft = useCallback((html: string) => {
    setDraftHtml(html);
    setStatus("unsaved");
  }, []);

  const save = useCallback(async () => {
    setSaving(true);
    setSaveError(null);
    try {
      const { savedAt } = await generatorApi.saveDraft(initial.id, draftHtml);
      setStatus("saved");
      setLastSavedAt(savedAt);
      setIsEditing(false);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "บันทึกไม่สำเร็จ");
    } finally {
      setSaving(false);
    }
  }, [draftHtml, initial.id]);

  const cancelEdit = useCallback(() => {
    setDraftHtml(initial.html);
    setIsEditing(false);
  }, [initial.html]);

  const download = useCallback(async () => {
    setDownloading(true);
    setDownloadError(null);
    try {
      const { version, blob } = await generatorApi.download(initial.id);
      const url = URL.createObjectURL(blob);
      const link = window.document.createElement("a");
      link.href = url;
      link.download = initial.fileName;
      link.click();
      URL.revokeObjectURL(url);
      return version;
    } catch (err) {
      setDownloadError(err instanceof Error ? err.message : "ดาวน์โหลดไม่สำเร็จ");
      return null;
    } finally {
      setDownloading(false);
    }
  }, [initial.id, initial.fileName]);

  return {
    draftHtml,
    status,
    lastSavedAt,
    isEditing,
    setIsEditing,
    saving,
    saveError,
    downloading,
    downloadError,
    updateDraft,
    save,
    cancelEdit,
    download,
  };
}
