import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, api, detail, unwrap } from "./client";
import type { components } from "./schema";

/** The project's own data (apart from its code): markdown notes and uploaded files.
 * Agent tasks and todo lists are notes too, read and written as their template's fields. */

export type DataFile = components["schemas"]["DataFileResponse"];
export type NoteType = "generic" | "agent_task" | "todo_list";
export type AgentTask = components["schemas"]["AgentTaskResponse"];
export type AgentTaskBody = components["schemas"]["AgentTaskBody"];
export type TodoList = components["schemas"]["TodoListResponse"];
export type TodoListBody = components["schemas"]["TodoListBody"];

/** The name of a typed note starts with the prefix of its type (as the backend decides it). */
export const NOTE_PREFIXES = { agent_task: "agent-task-", todo_list: "todo-list-" } as const;

export const dataKeys = {
  notes: (project: string) => ["projects", project, "notes"] as const,
  note: (project: string, note: string) => ["projects", project, "notes", note] as const,
  typed: (project: string) => ["projects", project, "notes", "typed"] as const,
  agentTasks: (project: string) => ["projects", project, "notes", "typed", "agent_task"] as const,
  todoLists: (project: string) => ["projects", project, "notes", "typed", "todo_list"] as const,
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
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: dataKeys.notes(project), exact: true }),
        queryClient.invalidateQueries({ queryKey: dataKeys.typed(project) }),
      ]),
  });
}

// -------------------------------------------------------------- typed notes

export function useAgentTasks(project: string) {
  return useQuery({
    queryKey: dataKeys.agentTasks(project),
    queryFn: () => unwrap(api.GET("/projects/{project}/agent-tasks", { params: { path: { project } } })),
  });
}

/** Create (``name`` undefined: the note is named after the title) or rewrite an agent task. */
export function useSaveAgentTask(project: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ name, body }: { name?: string; body: AgentTaskBody }) =>
      unwrap(
        name === undefined
          ? api.POST("/projects/{project}/agent-tasks", { params: { path: { project } }, body })
          : api.PUT("/projects/{project}/agent-tasks/{note}", { params: { path: { project, note: name } }, body }),
      ),
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: dataKeys.agentTasks(project) }),
        queryClient.invalidateQueries({ queryKey: dataKeys.notes(project), exact: true }),
      ]),
  });
}

export function useTodoLists(project: string) {
  return useQuery({
    queryKey: dataKeys.todoLists(project),
    queryFn: () => unwrap(api.GET("/projects/{project}/todo-lists", { params: { path: { project } } })),
  });
}

/** Create (``name`` undefined: the note is named after the title) or rewrite a todo list. */
export function useSaveTodoList(project: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ name, body }: { name?: string; body: TodoListBody }) =>
      unwrap(
        name === undefined
          ? api.POST("/projects/{project}/todo-lists", { params: { path: { project } }, body })
          : api.PUT("/projects/{project}/todo-lists/{note}", { params: { path: { project, note: name } }, body }),
      ),
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: dataKeys.todoLists(project) }),
        queryClient.invalidateQueries({ queryKey: dataKeys.notes(project), exact: true }),
      ]),
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
