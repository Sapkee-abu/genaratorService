import type { ReferenceTree as TreeData } from "../../types/reference";
import { ReferenceTreeNode } from "./ReferenceTreeNode";
import "./ReferenceTree.css";

interface Props {
  tree: TreeData;
  selectedId: string | null;
  onSelect: (referenceItemId: string) => void;
}

export function ReferenceTree({ tree, selectedId, onSelect }: Props) {
  return (
    <ul className="reference-tree" role="tree" aria-label="Document structure">
      {tree.nodes.map((node) => (
        <ReferenceTreeNode key={node.id} node={node} selectedId={selectedId} onSelect={onSelect} />
      ))}
    </ul>
  );
}
