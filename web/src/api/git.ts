import { useMutation, useQuery } from "@tanstack/react-query";

import { api, unwrap } from "./client";
import type { components } from "./schema";

export type Repository = components["schemas"]["RepositoryResponse"];
export type Commit = components["schemas"]["CommitResponse"];
export type GitStatus = components["schemas"]["StatusResponse"];
export type Change = components["schemas"]["ChangeResponse"];
export type LogFilters = { limit: number; author: string; message: string; commit: string };

export function useRepositories(project: string) {
  return useQuery({
    queryKey: ["projects", project, "git", "repositories"],
    queryFn: () => unwrap(api.GET("/projects/{project}/git/repositories", { params: { path: { project } } })),
  });
}

/** Git runs only on demand (a button), hence mutations: the last result stays on screen. */
export function useGitLog(project: string) {
  return useMutation({
    mutationFn: ({ path, filters }: { path: string; filters: LogFilters }) =>
      unwrap(api.GET("/projects/{project}/git/log", { params: { path: { project }, query: { path, ...filters } } })),
  });
}

export function useGitStatus(project: string) {
  return useMutation({
    mutationFn: (path: string) => unwrap(api.GET("/projects/{project}/git/status", { params: { path: { project }, query: { path } } })),
  });
}
