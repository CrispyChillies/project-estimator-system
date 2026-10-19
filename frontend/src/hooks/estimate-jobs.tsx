"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { errorToast, useInvalidateEstimate, useJob } from "@/hooks/queries";
import { api } from "@/lib/api";
import type { Job } from "@/lib/types";

interface Entry {
  jobId: string;
  estimateId: string;
  taskIds: string[];
}

interface Ctx {
  start: (estimateId: string, taskIds: string[]) => Promise<void>;
  isEstimating: (estimateId: string, taskId?: string) => boolean;
}

const EstimateJobsContext = createContext<Ctx>({ start: async () => {}, isEstimating: () => false });

export const useEstimateJobs = () => useContext(EstimateJobsContext);

function Watcher({ entry, onDone }: { entry: Entry; onDone: (e: Entry) => void }) {
  const { data } = useJob(entry.jobId);
  const invalidate = useInvalidateEstimate();
  const fired = useRef(false);
  useEffect(() => {
    if (!data || fired.current || !["done", "failed"].includes(data.status)) return;
    fired.current = true;
    invalidate(entry.estimateId);
    if (data.status === "done") toast.success(`AI estimated ${entry.taskIds.length} task(s)`);
    else toast.error(data.error ?? "AI estimate failed");
    onDone(entry);
  }, [data, entry, invalidate, onDone]);
  return null;
}

/** Lives above the router so background estimates keep running (and finish) while the user changes tabs/pages. */
export function EstimateJobsProvider({ children }: { children: React.ReactNode }) {
  const [entries, setEntries] = useState<Entry[]>([]);
  const start = useCallback(async (estimateId: string, taskIds: string[]) => {
    try {
      const job = await api<Job>(`/estimates/${estimateId}/tasks/estimate`, { method: "POST", json: { task_ids: taskIds } });
      setEntries((e) => [...e, { jobId: job.id, estimateId, taskIds }]);
      toast.info(`AI is estimating ${taskIds.length} task(s) in the background`);
    } catch (err) {
      errorToast(err);
    }
  }, []);
  const isEstimating = useCallback(
    (estimateId: string, taskId?: string) =>
      entries.some((e) => e.estimateId === estimateId && (!taskId || e.taskIds.includes(taskId))),
    [entries],
  );
  const done = useCallback((e: Entry) => setEntries((all) => all.filter((x) => x.jobId !== e.jobId)), []);
  return (
    <EstimateJobsContext.Provider value={{ start, isEstimating }}>
      {children}
      {entries.map((e) => (
        <Watcher key={e.jobId} entry={e} onDone={done} />
      ))}
    </EstimateJobsContext.Provider>
  );
}
