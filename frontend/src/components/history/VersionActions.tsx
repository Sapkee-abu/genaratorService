import { Link } from "react-router-dom";
import "./VersionActions.css";

interface Props {
  onPreview: () => void;
  onDownload: () => void;
  version: number;
}

export function VersionActions({ onPreview, onDownload, version }: Props) {
  return (
    <div className="version-actions">
      <button className="btn" onClick={onPreview}>
        Preview
      </button>
      <button className="btn" onClick={onDownload}>
        Download
      </button>
      <Link className="btn" to={`${import.meta.env.VITE_PORTAL === "true" ? "/generator" : ""}/reference/${version}`}>
        Reference
      </Link>
    </div>
  );
}
