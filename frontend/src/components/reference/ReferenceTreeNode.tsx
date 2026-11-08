import { useMemo, useState } from "react";
import type { ReferenceTreeNode as TreeNode } from "../../types/reference";
import { groupRowChildren } from "./groupRows";
import "./ReferenceTreeNode.css";

interface Props {
  node: TreeNode;
  selectedId: string | null;
  onSelect: (referenceItemId: string) => void;
  depth?: number;
}

export function ReferenceTreeNode({ node, selectedId, onSelect, depth = 0 }: Props) {
  const [expanded, setExpanded] = useState(depth < 1);
  // Table -> Row -> Field (display only; see groupRows.ts). Non-row children pass through unchanged.
  const { nodes: displayChildren, rowCount } = useMemo(
    () => (node.children ? groupRowChildren(node.id, node.children) : { nodes: [], rowCount: 0 }),
    [node.id, node.children]
  );
  const hasChildren = displayChildren.length > 0;
  const isLeaf = !hasChildren && !!node.referenceItemId;

  const handleActivate = () => {
    if (isLeaf && node.referenceItemId) {
      onSelect(node.referenceItemId);
    } else if (hasChildren) {
      setExpanded((value) => !value);
    }
  };

  return (
    <li>
      <div
        role="treeitem"
        tabIndex={0}
        aria-expanded={hasChildren ? expanded : undefined}
        aria-selected={isLeaf && node.referenceItemId === selectedId}
        className={
          "reference-tree-node" +
          (isLeaf && node.referenceItemId === selectedId ? " reference-tree-node--selected" : "")
        }
        style={{ paddingLeft: `${depth * 16}px` }}
        onClick={handleActivate}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            handleActivate();
          }
        }}
      >
        {hasChildren && <span className="reference-tree-node__toggle">{expanded ? "▼" : "▶"}</span>}
        {node.label}
        {rowCount > 0 && (
          <span className="reference-tree-node__count text-muted">
            {rowCount} {rowCount === 1 ? "row" : "rows"}
          </span>
        )}
      </div>
      {hasChildren && expanded && (
        <ul className="reference-tree-node__children">
          {displayChildren.map((child) => (
            <ReferenceTreeNode key={child.id} node={child} selectedId={selectedId} onSelect={onSelect} depth={depth + 1} />
          ))}
        </ul>
      )}
    </li>
  );
}
