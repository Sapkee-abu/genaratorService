import { useEffect } from "react";
import { useBlocker } from "react-router-dom";

/** create.md sec.13 - warns before leaving with unsaved changes, both for
 * in-app navigation (Navigation links / back-forward, via react-router's
 * data-router useBlocker) and for closing/refreshing the tab (native
 * beforeunload). Never triggers when there are no unsaved changes. */
export function useUnsavedChangesGuard(hasUnsavedChanges: boolean) {
  const blocker = useBlocker(hasUnsavedChanges);

  useEffect(() => {
    if (!hasUnsavedChanges) return;
    const handler = (event: BeforeUnloadEvent) => {
      event.preventDefault();
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [hasUnsavedChanges]);

  return blocker;
}
