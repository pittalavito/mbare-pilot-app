import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "./client";

/** The worker that executes the queues (automations, Copilot): started and
 * stopped by the API, followed every 5 seconds wherever it is shown. */


export const workerKey = ["admin", "worker"] as const;

export function useWorkerState() {
  return useQuery({ queryKey: workerKey, queryFn: () => unwrap(api.GET("/admin/worker")), refetchInterval: 5_000 });
}

/** «Avvia il worker» (also from the step «Lavora» of an activity, whose round it moves). */
export function useStartWorker() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/admin/worker/start")),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: workerKey }),
  });
}
