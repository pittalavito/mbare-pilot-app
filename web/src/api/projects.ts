import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "./client";
import type { components } from "./schema";

export type Project = components["schemas"]["ProjectResponse"];
export type OpenFolderRequest = components["schemas"]["OpenFolderRequest"];
export type CreateFromScratchRequest = components["schemas"]["CreateFromScratchRequest"];

export const projectKeys = {
  all: ["projects"] as const,
  one: (name: string) => ["projects", name] as const,
  atlassian: (name: string) => ["projects", name, "atlassian"] as const,
};

export function useProjects() {
  return useQuery({ queryKey: projectKeys.all, queryFn: () => unwrap(api.GET("/projects")) });
}

export function useProject(name: string) {
  return useQuery({
    queryKey: projectKeys.one(name),
    queryFn: () => unwrap(api.GET("/projects/{name}", { params: { path: { name } } })),
  });
}

export function useOpenFolder() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: OpenFolderRequest) => unwrap(api.POST("/projects/open-folder", { body })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: projectKeys.all }),
  });
}

export function useCreateFromScratch() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateFromScratchRequest) => unwrap(api.POST("/projects/from-scratch", { body })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: projectKeys.all }),
  });
}

/** The project's Atlassian site; the tab exists only when it is configured. */
export function useAtlassianConfigured(name: string) {
  const settings = useQuery({
    queryKey: projectKeys.atlassian(name),
    queryFn: () => unwrap(api.GET("/projects/{project}/atlassian", { params: { path: { project: name } } })),
  });
  const data = settings.data;
  return Boolean(data && data.base_url && data.email && data.has_token);
}

// ------------------------------------------------------------- folder picker

export function useFolderRoots() {
  return useQuery({
    queryKey: ["folders", "roots"],
    queryFn: () => unwrap(api.GET("/folders/roots")),
    staleTime: Infinity,
  });
}

/** A folder of the PC as the backend sees it ('' = the default one), confined to PROJECT_ROOTS. */
export function useFolder(path: string, showHidden: boolean) {
  return useQuery({
    queryKey: ["folders", path, showHidden],
    queryFn: () => unwrap(api.GET("/folders", { params: { query: { path, show_hidden: showHidden } } })),
    placeholderData: keepPreviousData,
  });
}

export function fetchFolder(path: string) {
  return unwrap(api.GET("/folders", { params: { query: { path } } }));
}

// ------------------------------------------------------------------ settings

export type UpdateProjectRequest = components["schemas"]["UpdateProjectRequest"];

export function useProjectOptions() {
  return useQuery({ queryKey: ["projects", "options"], queryFn: () => unwrap(api.GET("/projects/options")), staleTime: Infinity });
}

export function useUpdateProject(name: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: UpdateProjectRequest) => unwrap(api.PATCH("/projects/{name}", { params: { path: { name } }, body })),
    onSuccess: (project) => {
      queryClient.setQueryData(projectKeys.one(name), project);
      return queryClient.invalidateQueries({ queryKey: projectKeys.all, exact: true });
    },
  });
}

/** Forget the project in the app (its folder on disk is not touched). */
export function useRemoveProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => unwrap(api.DELETE("/projects/{name}", { params: { path: { name } } })),
    onSuccess: (_, name) => {
      queryClient.removeQueries({ queryKey: projectKeys.one(name) });
      return queryClient.invalidateQueries({ queryKey: projectKeys.all, exact: true });
    },
  });
}
