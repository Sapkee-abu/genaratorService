import type { DocumentHistory } from "../../types/history";
import { HistoryItem } from "./HistoryItem";
import "./HistoryList.css";

interface Props {
  history: DocumentHistory;
  onPreview: (version: number) => void;
  onDownload: (version: number) => void;
}

export function HistoryList({ history, onPreview, onDownload }: Props) {
  if (history.versions.length === 0) {
    return <p className="text-muted">ยังไม่มีเอกสารที่ Download</p>;
  }

  return (
    <div className="history-list">
      <h2 className="history-list__filename">{history.fileName}</h2>
      {history.versions.map((version) => (
        <HistoryItem key={version.version} version={version} onPreview={onPreview} onDownload={onDownload} />
      ))}
    </div>
  );
}
