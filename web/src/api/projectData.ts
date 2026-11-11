import { notifications } from "@mantine/notifications";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, api, detail, unwrap } from "./client";
import type { components } from "./schema";

/** The project's own data (apart from its code): markdown notes and uploaded files.
 * Agent tasks, activities and the code/context references they link are notes too,
 * read and written as their template's fields. */

export type DataFile = components["schemas"]["DataFileResponse"];
export type NoteType = "generic" | "agent_task" | "activity" | "code_reference" | "context_reference";
export type AgentTask = components["schemas"]["AgentTaskResponse"];
export type AgentTaskBody = components["schemas"]["AgentTaskBody"];
export type Activity = components["schemas"]["ActivityResponse"];
export type ActivityBody = components["schemas"]["ActivityBody"];
export type TaskType = AgentTaskBody["type"];
/** An item checked or unchecked by itself, because its agent task got or left «done». */
export type ItemChange = components["schemas"]["ItemChange"];
export type Reference = components["schemas"]["ReferenceResponse"];
export type ReferenceBody = components["schemas"]["ReferenceBody"];
export type ReferenceKind = components["schemas"]["ReferenceCreateBody"]["kind"];

/** The name of a typed note starts with the prefix of its type (as the backend decides it). */
export const NOTE_PREFIXES = {
  agent_task: "agent-task-", activity: "attivita-", code_reference: "code-reference-", context_reference: "context-reference-",
} as const;

export type CodeTodoScan = components["schemas"]["CodeTodoScanResponse"];

export const dataKeys = {
  notes: (project: string) => ["projects", project, "notes"] as const,
  note: (project: string, note: string) => ["projects", project, "notes", note] as const,
  typed: (project: string) => ["projects", project, "notes", "typed"] as const,
  agentTasks: (project: string) => ["projects", project, "notes", "typed", "agent_task"] as const,
  activities: (project: string) => ["projects", project, "notes", "typed", "activity"] as const,
  references: (project: string) => ["projects", project, "notes", "typed", "references"] as const,
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

/** What a save says about the items born from the task: a notification each. */
function notifyItems(changes: ItemChange[]) {
  for (const change of changes) {
    notifications.show({
      color: change.done ? "green" : "orange",
      message: change.done
        ? `Voce «${change.text}» di «${change.activity_title}» spuntata: il task è fatto.`
        : `Voce «${change.text}» di «${change.activity_title}»: tolta la spunta, il task non è più fatto.`,
    });
  }
}

/** Create (``name`` undefined: the note is named after the title) or rewrite an agent task.
 * A rewrite may check or uncheck the items born from it (notified; activities refreshed). */
export function useSaveAgentTask(project: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ name, body }: { name?: string; body: AgentTaskBody }): Promise<AgentTask> => {
      if (name === undefined) return unwrap(api.POST("/projects/{project}/agent-tasks", { params: { path: { project } }, body }));
      const { items_changed: changes = [], ...task } = await unwrap(
        api.PUT("/projects/{project}/agent-tasks/{note}", { params: { path: { project, note: name } }, body }),
      );
      notifyItems(changes);
      return task;
    },
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: dataKeys.activities(project) }),
        queryClient.invalidateQueries({ queryKey: dataKeys.agentTasks(project) }),
        queryClient.invalidateQueries({ queryKey: dataKeys.notes(project), exact: true }),
        queryClient.invalidateQueries({ queryKey: ["projects", project, "today"] }), // «📌 Oggi» lists them
      ]),
  });
}

export function useActivities(project: string) {
  return useQuery({
    queryKey: dataKeys.activities(project),
    queryFn: () => unwrap(api.GET("/projects/{project}/activities", { params: { path: { project } } })),
  });
}

/** «🤖» on an item (1-based, checked against its text): a task «created» from it, linked to the item. */
export function useCreateTaskFromItem(project: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ activity, item, text, type }: { activity: string; item: number; text: string; type: TaskType }) =>
      unwrap(api.POST("/projects/{project}/activities/{note}/items/{item}/agent-task", {
        params: { path: { project, note: activity, item } }, body: { text, type },
      })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: dataKeys.typed(project) }),
  });
}

/** Create (``name`` undefined: the note is named after the title) or rewrite an activity. */
export function useSaveActivity(project: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ name, body }: { name?: string; body: ActivityBody }) =>
      unwrap(
        name === undefined
          ? api.POST("/projects/{project}/activities", { params: { path: { project } }, body })
          : api.PUT("/projects/{project}/activities/{note}", { params: { path: { project, note: name } }, body }),
      ),
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: dataKeys.activities(project) }),
        queryClient.invalidateQueries({ queryKey: dataKeys.notes(project), exact: true }),
        queryClient.invalidateQueries({ queryKey: ["projects", project, "today"] }), // «📌 Oggi» lists them
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
/** How a task or an activity links an uploaded file (the backend's FILE_LINK_PREFIX). */
export const FILE_LINK_PREFIX = "files/";

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
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: dataKeys.files(project) }),
        queryClient.invalidateQueries({ queryKey: dataKeys.typed(project) }), // unlinked from tasks and activities
      ]),
  });
}

// --------------------------------------------------------------- references

/** Every code and context reference, with the tasks and activities that link it. */
export function useReferences(project: string) {
  return useQuery({
    queryKey: dataKeys.references(project),
    queryFn: () => unwrap(api.GET("/projects/{project}/references", { params: { path: { project } } })),
  });
}

/** Create (``kind`` given) or rewrite (``name`` given) a reference; linking it is the task's or activity's job. */
/** Gather the code's todoMbarePilot{...} comments into the note
 * ``code-reference-todo-mbare-pilot.md``: counts back, ``note`` null when nothing was found. */
export function useScanCodeTodos(project: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/projects/{project}/code-todos", { params: { path: { project } } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: dataKeys.references(project) }),
  });
}

export function useSaveReference(project: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ name, kind, body }: { name?: string; kind?: ReferenceKind; body: ReferenceBody }) =>
      unwrap(
        name === undefined
          ? api.POST("/projects/{project}/references", { params: { path: { project } }, body: { ...body, kind: kind! } })
          : api.PUT("/projects/{project}/references/{note}", { params: { path: { project, note: name } }, body }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: dataKeys.references(project) }),
  });
}

/** Delete a reference: it is unlinked from every task and activity too. */
export function useDeleteReference(project: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => unwrap(api.DELETE("/projects/{project}/references/{note}", { params: { path: { project, note: name } } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: dataKeys.typed(project) }),
  });
}

// ----------------------------------------------------------------- settings

export type DataSettings = components["schemas"]["DataSettingsBody"];

const settingsKey = (project: string) => ["projects", project, "data-settings"] as const;

/** Which note types the Dati tab shows (the default ones until the project chooses). */
export function useDataSettings(project: string) {
  return useQuery({
    queryKey: settingsKey(project),
    queryFn: () => unwrap(api.GET("/projects/{project}/data-settings", { params: { path: { project } } })),
  });
}

export function useSaveDataSettings(project: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: DataSettings) => unwrap(api.PUT("/projects/{project}/data-settings", { params: { path: { project } }, body })),
    onSuccess: (saved) => queryClient.setQueryData(settingsKey(project), saved),
  });
}
