import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "./client";
import type { components } from "./schema";

/** The project's context (RAG): the documents of context/ (saving one indexes
 * it), the state of the index, «Reindicizza tutto», a search to try it. */

export type RagHit = components["schemas"]["RagHit"];

const keys = {
  list: (project: string) => ["projects", project, "context"] as const,
  document: (project: string, name: string) => ["projects", project, "context", name] as const,
  index: (project: string) => ["projects", project, "context-index"] as const,
};

export function useContextDocuments(project: string) {
  return useQuery({ queryKey: keys.list(project), queryFn: () => unwrap(api.GET("/projects/{project}/context", { params: { path: { project } } })) });
}

export function useContextDocument(project: string, name: string) {
  return useQuery({
    queryKey: keys.document(project, name),
    queryFn: () => unwrap(api.GET("/projects/{project}/context/{name}", { params: { path: { project, name } } })),
  });
}

export function useContextIndex(project: string) {
  return useQuery({ queryKey: keys.index(project), queryFn: () => unwrap(api.GET("/projects/{project}/context-index", { params: { path: { project } } })) });
}

/** Create or overwrite a document: it is indexed at once (``index_error`` says why not). */
export function useSaveContext(project: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ name, content }: { name: string; content: string }) =>
      unwrap(api.PUT("/projects/{project}/context/{name}", { params: { path: { project, name } }, body: { content } })),
    onSuccess: (saved, { content }) => {
      queryClient.setQueryData(keys.document(project, saved.name), { name: saved.name, content });
      return Promise.all([
        queryClient.invalidateQueries({ queryKey: keys.list(project), exact: true }),
        queryClient.invalidateQueries({ queryKey: keys.index(project) }),
      ]);
    },
  });
}

export function useDeleteContext(project: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => unwrap(api.DELETE("/projects/{project}/context/{name}", { params: { path: { project, name } } })),
    onSuccess: () => Promise.all([
      queryClient.invalidateQueries({ queryKey: keys.list(project), exact: true }),
      queryClient.invalidateQueries({ queryKey: keys.index(project) }),
    ]),
  });
}

export function useReindexContext(project: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/projects/{project}/context-index/reindex", { params: { path: { project } } })),
    onSuccess: (state) => queryClient.setQueryData(keys.index(project), state),
  });
}

/** What search_context gives the Refiner and Copilot for a question. */
export function useSearchContext(project: string) {
  return useMutation({
    mutationFn: (question: string) =>
      unwrap(api.POST("/projects/{project}/context-index/search", { params: { path: { project } }, body: { question } })),
  });
}
