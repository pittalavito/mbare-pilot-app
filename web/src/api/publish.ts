import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "./client";
import { dataKeys } from "./projectData";
import type { components } from "./schema";

/** «Pubblica su Confluence/Jira» of a task's draft (blocco 10): what it would
 * do, the pages and issue types to choose from, the publication. */

export type PublishPreview = components["schemas"]["PublishPreview"];
export type PublishResult = components["schemas"]["PublishResult"];
export type PublishRequest = components["schemas"]["PublishRequest"];

/** Is ``note`` a draft to publish (``bozza-confluence-<task>.md`` / ``bozza-jira-<task>.md``, saved from Copilot's answer)? */
export const isDraft = (note: string) => note.startsWith("bozza-confluence-") || note.startsWith("bozza-jira-");

/** The draft's kind, from its name (plan 32): a badge in the notes list. */
export const draftKind = (note: string): "confluence" | "jira" | null =>
  note.startsWith("bozza-confluence-") ? "confluence" : note.startsWith("bozza-jira-") ? "jira" : null;

export type ConfluenceNode = components["schemas"]["ConfluenceNode"];

/** Where a new page can go (plan 32): the space's top pages, or the pages and folders under ``parent``. */
export function usePlaces(project: string, space: string, parent: ConfluenceNode | null, enabled: boolean) {
  return useQuery({
    queryKey: ["projects", project, "atlassian", "places", space, parent?.id ?? ""],
    queryFn: () => unwrap(api.GET("/projects/{project}/atlassian/confluence/places", {
      params: { path: { project }, query: { space, parent: parent?.id ?? "", kind: parent?.kind ?? "page" } },
    })),
    enabled: enabled && !!space.trim(),
  });
}

/** Pages and folders by title, or the one a pasted link points to. */
export function useSearchPlaces(project: string) {
  return useMutation({
    mutationFn: ({ q, space }: { q: string; space: string }) =>
      unwrap(api.GET("/projects/{project}/atlassian/confluence/places/search", { params: { path: { project }, query: { q, space } } })),
  });
}

export function usePublishPreview(project: string, task: string, enabled: boolean) {
  return useQuery({
    queryKey: ["projects", project, "publish", task],
    queryFn: () => unwrap(api.GET("/projects/{project}/agent-tasks/{note}/publish", { params: { path: { project, note: task } } })),
    enabled,
    staleTime: 0,
    gcTime: 0,
  });
}

export function usePublish(project: string, task: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: PublishRequest) =>
      unwrap(api.POST("/projects/{project}/agent-tasks/{note}/publish", { params: { path: { project, note: task } }, body })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: dataKeys.typed(project) }),
  });
}

/** The pages of a Confluence space (to pick the new page's parent). */
export function useSpacePages(project: string, space: string, enabled: boolean) {
  return useQuery({
    queryKey: ["projects", project, "atlassian", "pages", space],
    queryFn: () => unwrap(api.GET("/projects/{project}/atlassian/confluence/pages", { params: { path: { project }, query: { space } } })),
    enabled: enabled && !!space.trim(),
  });
}

export function useIssueTypes(project: string, projectKey: string, enabled: boolean) {
  return useQuery({
    queryKey: ["projects", project, "atlassian", "issue-types", projectKey],
    queryFn: () => unwrap(api.GET("/projects/{project}/atlassian/jira/issue-types", {
      params: { path: { project }, query: { project_key: projectKey || undefined } },
    })),
    enabled,
  });
}
