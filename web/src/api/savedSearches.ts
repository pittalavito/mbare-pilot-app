import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "./client";
import type { components } from "./schema";

/** Saved searches in the code (plan 34, «regex parlanti»): the defaults of the
 * definitions (``origin: app``) and the project's own (``progetto``), plus «✨ Regex». */

export type SavedSearch = components["schemas"]["SavedSearchView"];
export type SavedSearchBody = components["schemas"]["SavedSearchBody"];
export type RegexProposal = components["schemas"]["RegexProposal"];

const key = (project: string) => ["projects", project, "saved-searches"] as const;

export function useSavedSearches(project: string) {
  return useQuery({
    queryKey: key(project),
    queryFn: () => unwrap(api.GET("/projects/{project}/code-search/saved", { params: { path: { project } } })),
  });
}

/** The search in the project, by name (``replacing`` = the name it had); the list after. */
export function useSaveSavedSearch(project: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: SavedSearchBody) => unwrap(api.PUT("/projects/{project}/code-search/saved", { params: { path: { project } }, body })),
    onSuccess: (list) => queryClient.setQueryData(key(project), list),
  });
}

/** The project's search removed (a default it replaced comes back). */
export function useDeleteSavedSearch(project: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => unwrap(api.DELETE("/projects/{project}/code-search/saved/{name}", { params: { path: { project, name } } })),
    onSuccess: (list) => queryClient.setQueryData(key(project), list),
  });
}

/** «✨ Regex»: the agent ``regex`` proposes a regex, its explanation and an example. */
export function useProposeRegex(project: string) {
  return useMutation({
    mutationFn: (description: string) => unwrap(api.POST("/projects/{project}/code-search/regex", { params: { path: { project } }, body: { description } })),
  });
}
