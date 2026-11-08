import type { DocumentVersion } from "../../types/history";
import { VersionActions } from "./VersionActions";
import "./HistoryItem.css";

function formatTimestamp(value: string): string {
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

interface Props {
  version: DocumentVersion;
  onPreview: (version: number) => void;
  onDownload: (version: number) => void;
}

export function HistoryItem({ version, onPreview, onDownload }: Props) {
  return (
    <div className="history-item surface">
      <div className="history-item__info">
        <span className="history-item__version">Version {version.version}</span>
        <span className="history-item__timestamp text-muted">{formatTimestamp(version.timestamp)}</span>
      </div>
      <VersionActions
        version={version.version}
        onPreview={() => onPreview(version.version)}
        onDownload={() => onDownload(version.version)}
      />
    </div>
  );
}
