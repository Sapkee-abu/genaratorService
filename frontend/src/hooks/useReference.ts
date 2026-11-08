import { useCallback, useEffect, useState } from "react";
import { referenceApi } from "../services/referenceApi";
import type { AsyncState } from "../types/api";
import type { ReferenceItem, ReferenceTree } from "../types/reference";

export function useReference(version?: number) {
  const [treeState, setTreeState] = useState<AsyncState<ReferenceTree>>({ status: "idle" });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [itemState, setItemState] = useState<AsyncState<ReferenceItem> | null>(null);

  useEffect(() => {
    let cancelled = false;
    setTreeState({ status: "loading" });
    referenceApi
      .getReferenceTree(version)
      .then((data) => {
        if (!cancelled) setTreeState({ status: "success", data });
      })
      .catch((err: unknown) => {
        if (!cancelled)
          setTreeState({
            status: "error",
            error: { message: err instanceof Error ? err.message : "โหลด Reference ไม่สำเร็จ" },
          });
      });
    return () => {
      cancelled = true;
    };
  }, [version]);

  const selectItem = useCallback(
    (referenceItemId: string) => {
      setSelectedId(referenceItemId);
      setItemState({ status: "loading" });
      referenceApi
        .getReferenceItem(referenceItemId, version)
        .then((data) => setItemState({ status: "success", data }))
        .catch((err: unknown) =>
          setItemState({
            status: "error",
            error: { message: err instanceof Error ? err.message : "โหลดรายละเอียด Reference ไม่สำเร็จ" },
          })
        );
    },
    [version]
  );

  return { treeState, itemState, selectedId, selectItem };
}
