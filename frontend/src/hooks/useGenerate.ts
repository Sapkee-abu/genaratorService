import { useCallback, useEffect, useRef, useState } from "react";
import { generatorApi } from "../services/generatorApi";
import type { GeneratedDocument, GenerationStatus, GenerationStep } from "../types/document";

const POLL_INTERVAL_MS = 400;

export function useGenerate() {
  const [status, setStatus] = useState<GenerationStatus>("idle");
  const [steps, setSteps] = useState<GenerationStep[]>([]);
  const [document, setDocument] = useState<GeneratedDocument | null>(null);
  const [error, setError] = useState<string | null>(null);
  const mountedRef = useRef(true);
  const timeoutRef = useRef<number | undefined>(undefined);

  useEffect(() => {
    // Must be re-armed on (re)mount: React StrictMode (dev) runs mount -> cleanup -> mount,
    // and without this the cleanup's `false` sticks, so every state update after an `await`
    // (error 412, progress, completion) is silently dropped and the UI hangs on "Generating...".
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (timeoutRef.current) window.clearTimeout(timeoutRef.current);
    };
  }, []);

  const poll = useCallback(async (jobId: string) => {
    try {
      const result = await generatorApi.getGenerationStatus(jobId);
      if (!mountedRef.current) return;
      setSteps(result.steps);

      if (result.status === "completed") {
        if (result.document) setDocument(result.document);
        setStatus("success");
        return;
      }
      if (result.status === "failed") {
        setStatus("error");
        setError(result.error ?? "การสร้างเอกสารล้มเหลว");
        return;
      }
      timeoutRef.current = window.setTimeout(() => poll(jobId), POLL_INTERVAL_MS);
    } catch (err) {
      if (!mountedRef.current) return;
      setStatus("error");
      setError(err instanceof Error ? err.message : "เกิดข้อผิดพลาดที่ไม่ทราบสาเหตุ");
    }
  }, []);

  const start = useCallback(
    async (curriculumId: string) => {
      setStatus("generating");
      setError(null);
      setDocument(null);
      setSteps([]);
      try {
        const { jobId } = await generatorApi.generate(curriculumId);
        await poll(jobId);
      } catch (err) {
        if (!mountedRef.current) return;
        setStatus("error");
        setError(err instanceof Error ? err.message : "ไม่สามารถเริ่ม Generate ได้");
      }
    },
    [poll]
  );

  const retry = useCallback(
    (curriculumId: string) => {
      void start(curriculumId);
    },
    [start]
  );

  return { status, steps, document, error, start, retry, setDocument };
}
