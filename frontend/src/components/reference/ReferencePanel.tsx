import type { ReferenceItem, ReferenceTree as TreeData } from "../../types/reference";
import { ReferenceTree } from "./ReferenceTree";
import { ReferenceDetails } from "./ReferenceDetails";
import "./ReferencePanel.css";

interface Props {
  tree: TreeData;
  selectedId: string | null;
  selectedItem: ReferenceItem | null;
  onSelect: (referenceItemId: string) => void;
}

export function ReferencePanel({ tree, selectedId, selectedItem, onSelect }: Props) {
  return (
    <div className="reference-panel">
      <div className="reference-panel__tree surface">
        <ReferenceTree tree={tree} selectedId={selectedId} onSelect={onSelect} />
      </div>
      <div className="reference-panel__details surface">
        <ReferenceDetails item={selectedItem} />
      </div>
    </div>
  );
}
