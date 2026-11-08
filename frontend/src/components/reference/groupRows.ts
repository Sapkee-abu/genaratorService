import type { ReferenceTreeNode } from "../../types/reference";

/** UI-only grouping of a table's per-cell Reference leaves by ROW.
 *
 * The backend already encodes the row in each leaf's id (`<slot>.row<N>.col<M>`, N = 0-based row
 * index; its label is "<header> (row N+1)"). This reads that existing information to build
 * Table -> Row -> Field for display. It never changes the data: every leaf keeps its own
 * `id` and `referenceItemId` (so selecting a field still loads exactly the same Reference
 * item / sourceReference), no item is added, removed or recomputed - only the leaf's DISPLAY
 * label drops the now-redundant " (row N)" suffix, and a display-only "Row N" wrapper is
 * inserted. Children that don't look like row cells (narratives, mock data, future shapes)
 * are returned untouched and in place. Generic - not tied to any table name. */
const ROW_LEAF_ID = /\.row(\d+)\.col\d+$/;
const ROW_LABEL_SUFFIX = /\s*\(row \d+\)\s*$/;

export interface GroupedChildren {
  nodes: ReferenceTreeNode[];
  /** Number of Row groups created (0 = nothing was row-based, children returned as-is). */
  rowCount: number;
}

/** Marks the display-only "Row N" wrapper nodes created below. Their children are already the fields of
 * one row, so they must never be grouped again (that would nest Row N inside Row N). */
const ROW_GROUP_ID = /::row\d+$/;

export function groupRowChildren(parentId: string, children: ReferenceTreeNode[]): GroupedChildren {
  if (ROW_GROUP_ID.test(parentId)) return { nodes: children, rowCount: 0 };

  const groups = new Map<string, ReferenceTreeNode>();
  const nodes: ReferenceTreeNode[] = [];

  for (const child of children) {
    const match = child.referenceItemId && !child.children ? ROW_LEAF_ID.exec(child.id) : null;
    if (!match) {
      nodes.push(child);
      continue;
    }

    const rowIndex = match[1];
    let group = groups.get(rowIndex);
    if (!group) {
      group = { id: `${parentId}::row${rowIndex}`, label: `Row ${Number(rowIndex) + 1}`, children: [] };
      groups.set(rowIndex, group);
      nodes.push(group); // the group takes the place of its first cell, so document order is preserved
    }
    group.children!.push({ ...child, label: child.label.replace(ROW_LABEL_SUFFIX, "") });
  }

  return { nodes, rowCount: groups.size };
}
