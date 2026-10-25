import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "./client";
import type { components } from "./schema";

/** The Admin page: app config, observability (agent runs, tool calls, traces), model catalog, DB backups. */

export type RunSummary = components["schemas"]["RunSummaryResponse"];
export type ToolCall = components["schemas"]["ToolCallResponse"];
export type CatalogModel = components["schemas"]["CatalogModelBody"];
export type Backup = components["schemas"]["BackupResponse"];

export function useConfig() {
  return useQuery({ queryKey: ["admin", "config"], queryFn: () => unwrap(api.GET("/admin/config")) });
}

export function useAgentRuns() {
  return useQuery({ queryKey: ["observability", "runs"], queryFn: () => unwrap(api.GET("/observability/runs")) });
}

export function useToolCalls() {
  return useQuery({ queryKey: ["observability", "tool-calls"], queryFn: () => unwrap(api.GET("/observability/tool-calls")) });
}

/** The verbatim trace of a run, kept in Redis (it may have expired). */
export function useTrace(runId: string | undefined) {
  return useQuery({
    queryKey: ["observability", "trace", runId],
    queryFn: () => unwrap(api.GET("/observability/runs/{run_id}/trace", { params: { path: { run_id: runId! } } })),
    enabled: runId !== undefined,
    retry: false,
    staleTime: Infinity,
  });
}

export function useModels() {
  return useQuery({ queryKey: ["models", "catalog"], queryFn: () => unwrap(api.GET("/models")) });
}

/** Replace the whole catalog; a model in use cannot be removed (deactivate it). */
export function useSaveModels() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (models: CatalogModel[]) => unwrap(api.PUT("/models", { body: models })),
    onSuccess: (models) => {
      queryClient.setQueryData(["models", "catalog"], models);
      return queryClient.invalidateQueries({ queryKey: ["models", "choices"] });
    },
  });
}

export function useBackups() {
  return useQuery({ queryKey: ["admin", "backups"], queryFn: () => unwrap(api.GET("/admin/backups")) });
}

export function useExportDb() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/admin/backups")),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin", "backups"] }),
  });
}

export const backupUrl = (name: string) => `${window.location.origin}/api/admin/backups/${encodeURIComponent(name)}`;
