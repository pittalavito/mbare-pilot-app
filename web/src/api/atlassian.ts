import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "./client";
import { projectKeys } from "./projects";
import type { components } from "./schema";

/** A project's Atlassian Cloud site: its settings (the saved token never comes
 * back), Jira issues, Confluence pages and the favorites saved in the app.
 * Atlassian is called only on demand (mutations); favorites are app data. */

export type AtlassianSettings = components["schemas"]["AtlassianSettingsResponse"];
export type AtlassianSettingsRequest = components["schemas"]["AtlassianSettingsRequest"];
export type JiraIssue = components["schemas"]["JiraIssueResponse"];
export type ConfluencePage = components["schemas"]["ConfluencePageResponse"];
export type Favorite = components["schemas"]["FavoriteResponse"];
export type FavoriteKind = components["schemas"]["FavoriteKind"];
export type PageLink = { id: string; title: string };

export const isConfigured = (settings: AtlassianSettings | null | undefined) =>
  Boolean(settings && settings.base_url && settings.email && settings.has_token);

export function useAtlassianSettings(project: string) {
  return useQuery({
    queryKey: projectKeys.atlassian(project),
    queryFn: () => unwrap(api.GET("/projects/{project}/atlassian", { params: { path: { project } } })),
  });
}

export function useSaveAtlassian(project: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: AtlassianSettingsRequest) => unwrap(api.PUT("/projects/{project}/atlassian", { params: { path: { project } }, body })),
    onSuccess: (settings) => queryClient.setQueryData(projectKeys.atlassian(project), settings),
  });
}

export function useRemoveAtlassian(project: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.DELETE("/projects/{project}/atlassian", { params: { path: { project } } })),
    onSuccess: () => queryClient.setQueryData(projectKeys.atlassian(project), null),
  });
}

export function useCheckAtlassian(project: string) {
  return useMutation({
    mutationFn: () => unwrap(api.POST("/projects/{project}/atlassian/check", { params: { path: { project } } })),
  });
}

export function useJiraIssue(project: string) {
  return useMutation({
    mutationFn: (issueKey: string) =>
      unwrap(api.GET("/projects/{project}/atlassian/jira/issues/{issue_key}", { params: { path: { project, issue_key: issueKey.trim() } } })),
  });
}

export function useConfluencePage(project: string) {
  return useMutation({
    mutationFn: (pageId: string) =>
      unwrap(api.GET("/projects/{project}/atlassian/confluence/pages/{page_id}", { params: { path: { project, page_id: pageId } } })),
  });
}

/** The pages of the default space, or those matching ``text``: just id and title. */
export function useConfluencePages(project: string) {
  return useMutation({
    mutationFn: async (text?: string): Promise<PageLink[]> =>
      text
        ? unwrap(api.GET("/projects/{project}/atlassian/confluence/search", { params: { path: { project }, query: { q: text } } }))
        : unwrap(api.GET("/projects/{project}/atlassian/confluence/pages", { params: { path: { project } } })),
  });
}

const favoritesKey = (project: string) => ["projects", project, "atlassian", "favorites"] as const;

export function useFavorites(project: string) {
  return useQuery({
    queryKey: favoritesKey(project),
    queryFn: () => unwrap(api.GET("/projects/{project}/atlassian/favorites", { params: { path: { project } } })),
  });
}

export function useAddFavorite(project: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { kind: FavoriteKind; ref: string; title: string; url: string }) =>
      unwrap(api.POST("/projects/{project}/atlassian/favorites", { params: { path: { project } }, body })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: favoritesKey(project) }),
  });
}

export function useRemoveFavorite(project: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      unwrap(api.DELETE("/projects/{project}/atlassian/favorites/{favorite_id}", { params: { path: { project, favorite_id: id } } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: favoritesKey(project) }),
  });
}
