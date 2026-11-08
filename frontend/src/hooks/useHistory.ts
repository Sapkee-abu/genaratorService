import { useCallback, useEffect, useState } from "react";
import { historyApi } from "../services/historyApi";
import type { AsyncState } from "../types/api";
import type { DocumentHistory } from "../types/history";

export function useHistory() {
  const [state, setState] = useState<AsyncState<DocumentHistory>>({ status: "idle" });

  const load = useCallback(async () => {
    setState({ status: "loading" });
    try {
      const data = await historyApi.getHistory();
      setState({ status: "success", data });
    } catch (err) {
      setState({ status: "error", error: { message: err instanceof Error ? err.message : "โหลดประวัติล้มเหลว" } });
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return { state, reload: load };
}
