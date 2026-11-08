import { useParams } from "react-router-dom";
import { useReference } from "../../hooks/useReference";
import { ReferencePanel } from "../../components/reference/ReferencePanel";
import "./ReferencePage.css";

export function ReferencePage() {
  const { version: versionParam } = useParams();
  const version = versionParam ? Number(versionParam) : undefined;
  const { treeState, itemState, selectedId, selectItem } = useReference(version);

  return (
    <div className="reference-page">
      <h1 className="reference-page__title">
        Reference{version !== undefined ? ` — Version ${version}` : ""}
      </h1>

      {treeState.status === "loading" && <p className="text-muted">กำลังโหลด...</p>}
      {treeState.status === "error" && <p className="reference-page__error">ไม่สามารถโหลด Reference ได้</p>}
      {treeState.status === "success" && treeState.data.nodes.length === 0 && (
        <p className="text-muted">ยังไม่มี Reference สำหรับเอกสารนี้</p>
      )}
      {treeState.status === "success" && treeState.data.nodes.length > 0 && (
        <ReferencePanel
          tree={treeState.data}
          selectedId={selectedId}
          selectedItem={itemState?.status === "success" ? itemState.data : null}
          onSelect={selectItem}
        />
      )}
    </div>
  );
}
