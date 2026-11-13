import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "./client";
import type { components } from "./schema";

/** The checks around a development delegated to Copilot (blocco 09): the
 * tests' settings, whether the project has «Prepara sviluppo» and «Verifica
 * sviluppo», and the branches to pick when preparing a repository. */

export type DevSettings = components["schemas"]["DevSettingsResponse"];
export type PrepareTarget = components["schemas"]["PrepareTarget"];
export type TestScope = DevSettings["test_scope"];

export const SCOPE_LABELS: Record<TestScope, string> = { all: "Tutti i test", touched: "Solo i test toccati" };

const settingsKey = (project: string) => ["projects", project, "dev-settings"] as const;

export function useDevSettings(project: string) {
  return useQuery({
    queryKey: settingsKey(project),
    queryFn: () => unwrap(api.GET("/projects/{project}/dev-settings", { params: { path: { project } } })),
  });
}

export function useSaveDevSettings(project: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: components["schemas"]["DevSettingsRequest"]) =>
      unwrap(api.PUT("/projects/{project}/dev-settings", { params: { path: { project } }, body })),
    onSuccess: (saved) => queryClient.setQueryData(settingsKey(project), saved),
  });
}

/** The current branch and the local and remote ones of a repository (``""`` = the project folder). */
export function useBranches(project: string, path: string | null) {
  return useQuery({
    queryKey: ["projects", project, "git", "branches", path],
    queryFn: () => unwrap(api.GET("/projects/{project}/git/branches", { params: { path: { project }, query: { path: path ?? "" } } })),
    enabled: path !== null,
  });
}

export type CommandRequest = components["schemas"]["CommandRequest"];

/** The commands the Operator asked for (plan 11), waiting for an answer: refreshed while the panel is open. */
export function useCommandRequests(project: string, enabled = true) {
  return useQuery({
    queryKey: ["projects", project, "command-requests"],
    queryFn: () => unwrap(api.GET("/projects/{project}/command-requests", { params: { path: { project } } })),
    enabled,
    refetchInterval: 4000,
  });
}

/** «Sempre» (allow + always), «Solo stavolta» (allow) or «No». */
export function useAnswerCommand(project: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: components["schemas"]["CommandAnswer"]) =>
      unwrap(api.POST("/projects/{project}/command-requests/answer", { params: { path: { project } }, body })),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects", project, "command-requests"] });
      queryClient.invalidateQueries({ queryKey: settingsKey(project) });
    },
  });
}
