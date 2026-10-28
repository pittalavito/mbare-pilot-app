import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "./client";
import type { components } from "./schema";

/** The values of a project the LLM sees only as aliases, and the definitions synced from files. */

export type MaskEntry = components["schemas"]["MaskEntryResponse"];
export type MaskCategory = components["schemas"]["MaskCategory"];
export type SyncReport = components["schemas"]["SyncReportResponse"];

const maskingKey = (project: string) => ["projects", project, "masking"] as const;

export function useMaskEntries(project: string) {
  return useQuery({
    queryKey: maskingKey(project),
    queryFn: () => unwrap(api.GET("/projects/{project}/masking", { params: { path: { project } } })),
  });
}

export function useAddMask(project: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { category: MaskCategory; value: string }) =>
      unwrap(api.POST("/projects/{project}/masking", { params: { path: { project } }, body })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: maskingKey(project) }),
  });
}

export function useRemoveMask(project: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (alias: string) => unwrap(api.DELETE("/projects/{project}/masking/{alias}", { params: { path: { project, alias } } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: maskingKey(project) }),
  });
}

export type DefinitionEntry = components["schemas"]["DefinitionEntryResponse"];
export type DefinitionKey = components["schemas"]["DefinitionKeyRequest"];

const definitionsKey = (project: string) => ["projects", project, "definitions"] as const;

/** What the YAML files define for the project, nothing applied: each element new, already there or with its error. */
export function useDefinitionsPreview(project: string) {
  return useQuery({
    queryKey: definitionsKey(project),
    queryFn: () => unwrap(api.GET("/projects/{project}/definitions", { params: { path: { project } } })),
  });
}

/** Apply the YAML definitions to the project (the file wins): everything, or ``only`` the elements chosen from the preview. */
export function useSyncDefinitions(project: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (only?: DefinitionKey[]) =>
      unwrap(api.POST("/projects/{project}/definitions/sync", { params: { path: { project } }, body: only ? { only } : undefined })),
    onSuccess: () =>
      Promise.all(
        [["agents"], ["projects", project, "chatbots"], ["projects", project, "pipelines"], definitionsKey(project)].map((queryKey) =>
          queryClient.invalidateQueries({ queryKey }),
        ),
      ),
  });
}
