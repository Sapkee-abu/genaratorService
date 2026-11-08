import { useState } from "react";
import { useHistory } from "../../hooks/useHistory";
import { historyApi } from "../../services/historyApi";
import { HistoryList } from "../../components/history/HistoryList";
import { DocumentViewer } from "../../components/generate/DocumentViewer";
import "./HistoryPage.css";

export function HistoryPage() {
  const { state } = useHistory();
  const [previewHtml, setPreviewHtml] = useState<string | null>(null);
  const [previewVersion, setPreviewVersion] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const handlePreview = async (version: number) => {
    setActionError(null);
    try {
      const doc = await historyApi.previewVersion(version);
      setPreviewHtml(doc.html);
      setPreviewVersion(version);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "ไม่สามารถ Preview ได้");
    }
  };

  const handleDownload = async (version: number) => {
    setActionError(null);
    try {
      const blob = await historyApi.downloadVersion(version);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `SAR_v${version}.docx`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "ดาวน์โหลดไม่สำเร็จ");
    }
  };

  return (
    <div className="history-page">
      <h1 className="history-page__title">Generation History</h1>

      {state.status === "loading" && <p className="text-muted">กำลังโหลด...</p>}
      {state.status === "error" && <p className="history-page__error">ไม่สามารถโหลดประวัติเอกสารได้</p>}
      {actionError && <p className="history-page__error">{actionError}</p>}
      {state.status === "success" && (
        <HistoryList history={state.data} onPreview={handlePreview} onDownload={handleDownload} />
      )}

      {previewHtml !== null && (
        <div className="history-page__preview surface">
          <div className="history-page__preview-header">
            <span>Preview — Version {previewVersion}</span>
            <button className="btn" onClick={() => setPreviewHtml(null)}>
              Close
            </button>
          </div>
          <DocumentViewer html={previewHtml} />
        </div>
      )}
    </div>
  );
}
