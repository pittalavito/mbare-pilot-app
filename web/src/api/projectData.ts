import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, api, detail, unwrap } from "./client";
import type { components } from "./schema";

/** The project's own data (apart from its code): markdown notes and uploaded files. */

export type DataFile = components["schemas"]["DataFileResponse"];

export const dataKeys = {
  notes: (project: string) => ["projects", project, "notes"] as const,
  note: (project: string, note: string) => ["projects", project, "notes", note] as const,
  files: (project: string) => ["projects", project, "files"] as const,
};

export function useNotes(project: string) {
  return useQuery({
    queryKey: dataKeys.notes(project),
    queryFn: () => unwrap(api.GET("/projects/{project}/notes", { params: { path: { project } } })),
  });
}

export function useNote(project: string, note: string | undefined) {
  return useQuery({
    queryKey: dataKeys.note(project, note ?? ""),
    queryFn: () => unwrap(api.GET("/projects/{project}/notes/{note}", { params: { path: { project, note: note! } } })),
    enabled: note !== undefined,
  });
}

/** Create or overwrite a note (the API adds ``.md`` when missing). */
export function useSaveNote(project: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ note, content }: { note: string; content: string }) =>
      unwrap(api.PUT("/projects/{project}/notes/{note}", { params: { path: { project, note } }, body: { content } })),
    onSuccess: (saved, { content }) => {
      queryClient.setQueryData(dataKeys.note(project, saved.name), { name: saved.name, content });
      return queryClient.invalidateQueries({ queryKey: dataKeys.notes(project), exact: true });
    },
  });
}

export function useDeleteNote(project: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (note: string) => unwrap(api.DELETE("/projects/{project}/notes/{note}", { params: { path: { project, note } } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: dataKeys.notes(project), exact: true }),
  });
}

export function useFiles(project: string) {
  return useQuery({
    queryKey: dataKeys.files(project),
    queryFn: () => unwrap(api.GET("/projects/{project}/files", { params: { path: { project } } })),
  });
}

/** Where a file is downloaded from (the browser saves it). */
export const fileUrl = (project: string, name: string) =>
  `${window.location.origin}/api/projects/${encodeURIComponent(project)}/files/${encodeURIComponent(name)}`;

/** Upload files; one with the same name is overwritten. The body is the raw content. */
export function useUploadFiles(project: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (files: File[]) => {
      for (const file of files) {
        const response = await globalThis.fetch(new Request(fileUrl(project, file.name), { method: "PUT", body: file }));
        if (!response.ok) {
          const body = await response.json().catch(() => undefined);
          throw new ApiError(response.status, detail(body) ?? `${file.name}: errore ${response.status}`);
        }
      }
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: dataKeys.files(project) }),
  });
}

export function useDeleteFile(project: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (name: string) =>
      unwrap(api.DELETE("/projects/{project}/files/{file_name}", { params: { path: { project, file_name: name } } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: dataKeys.files(project) }),
  });
}
