import { useQuery } from "@tanstack/react-query";

import { api, unwrap } from "./client";
import type { components } from "./schema";

/** The worker that executes the queues (automations, Copilot): started and
 * stopped by the API, followed every 5 seconds wherever it is shown. */

export type WorkerState = components["schemas"]["WorkerStateResponse"];

export const workerKey = ["admin", "worker"] as const;

export function useWorkerState() {
  return useQuery({ queryKey: workerKey, queryFn: () => unwrap(api.GET("/admin/worker")), refetchInterval: 5_000 });
}
