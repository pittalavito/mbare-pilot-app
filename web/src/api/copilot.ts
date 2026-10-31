import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "./client";
import { dataKeys } from "./projectData";
import type { components } from "./schema";

/** Agent tasks delegated to GitHub Copilot CLI: sessions, the planning chat
 * (each message is queued for the worker, which writes Copilot's answer: the
 * page polls), the ok, cancellation. */

export type CopilotSession = components["schemas"]["CopilotSessionResponse"];
export type CopilotMessage = components["schemas"]["CopilotMessageResponse"];
export type CopilotStatus = CopilotSession["status"];
export type CopilotUsage = components["schemas"]["CopilotUsageResponse"];
export type CopilotTurn = components["schemas"]["CopilotTurnResponse"];
export type CopilotModelOption = components["schemas"]["CopilotModelOptionResponse"];

/** Queued or running: the worker has it, the page follows it. */
export const isExecuting = (session: CopilotSession) => session.status === "queued" || session.status === "running";

/** A planning turn queued or running in the worker: Copilot's answer is on its way. */
export const isAnswering = (session: CopilotSession) => session.planning_turn !== null;

/** The worker has something of the session (an execution or a planning turn): the page polls it. */
export const isLive = (session: CopilotSession) => isExecuting(session) || isAnswering(session);

export const copilotKeys = {
  status: (project?: string) => ["copilot", "status", project ?? ""] as const,
  sessions: (project: string) => ["projects", project, "copilot-sessions"] as const,
  session: (id: number) => ["copilot-sessions", id] as const,
  messages: (id: number) => ["copilot-sessions", id, "messages"] as const,
  usage: (id: number) => ["copilot-sessions", id, "turns"] as const,
  turns: ["observability", "copilot", "turns"] as const,
  models: (days: number | null) => ["observability", "copilot", "models", days] as const,
};

/** Whether Copilot CLI is installed, its version, and what is wrong with the
 * coding-agent definition (the global one, plus the project's when given). */
export function useCopilotStatus(project?: string) {
  return useQuery({
    queryKey: copilotKeys.status(project),
    queryFn: () => unwrap(api.GET("/copilot/status", { params: { query: { project } } })),
    staleTime: 60_000,
  });
}

/** Newest first; refreshed every 3 seconds while the worker has one of them (execution or planning turn). */
export function useCopilotSessions(project: string) {
  return useQuery({
    queryKey: copilotKeys.sessions(project),
    queryFn: () => unwrap(api.GET("/projects/{project}/copilot-sessions", { params: { path: { project } } })),
    refetchInterval: (query) => (query.state.data?.some(isLive) ? 3_000 : false),
  });
}

/** The messages of a session; ``live`` refreshes them while the worker has it. */
export function useCopilotMessages(id: number | undefined, live: boolean) {
  return useQuery({
    queryKey: copilotKeys.messages(id ?? 0),
    queryFn: () => unwrap(api.GET("/copilot-sessions/{session_id}/messages", { params: { path: { session_id: id! } } })),
    enabled: id !== undefined,
    refetchInterval: live ? 3_000 : false,
  });
}

/** What each turn of a session used, and the sum; ``live`` refreshes it while the worker has it. */
export function useCopilotSessionUsage(id: number | undefined, live: boolean) {
  return useQuery({
    queryKey: copilotKeys.usage(id ?? 0),
    queryFn: () => unwrap(api.GET("/copilot-sessions/{session_id}/turns", { params: { path: { session_id: id! } } })),
    enabled: id !== undefined,
    refetchInterval: live ? 3_000 : false,
  });
}

/** Observability: every session's turns, newest first. */
export function useCopilotTurns() {
  return useQuery({ queryKey: copilotKeys.turns, queryFn: () => unwrap(api.GET("/observability/copilot/turns")) });
}

/** Observability: totals per model over the last ``days`` (null = ever). */
export function useCopilotModelUsage(days: number | null) {
  return useQuery({
    queryKey: copilotKeys.models(days),
    queryFn: () => unwrap(api.GET("/observability/copilot/models", { params: { query: { days: days ?? undefined } } })),
  });
}

/** After any change: the session list (status) and the session's messages; the task's status too. */
function useRefresh(project: string) {
  const queryClient = useQueryClient();
  return (id: number) =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: copilotKeys.sessions(project) }),
      queryClient.invalidateQueries({ queryKey: copilotKeys.messages(id) }),
      queryClient.invalidateQueries({ queryKey: copilotKeys.usage(id) }),
      queryClient.invalidateQueries({ queryKey: dataKeys.agentTasks(project) }),
    ]);
}

/** Delegate an agent task: resolves at once, with the first planning turn queued for the worker. */
export function useStartCopilot(project: string) {
  const refresh = useRefresh(project);
  return useMutation({
    mutationFn: (body: { task_note: string; repositories: string[]; prompt: string; model: string }) =>
      unwrap(api.POST("/projects/{project}/copilot-sessions", { params: { path: { project } }, body })),
    onSuccess: (session) => refresh(session.id),
  });
}

/** A message of the planning chat: resolves at once (queued for the worker); Copilot's answer arrives by polling. */
export function useSendCopilotMessage(project: string) {
  const refresh = useRefresh(project);
  return useMutation({
    mutationFn: ({ id, text }: { id: number; text: string }) =>
      unwrap(api.POST("/copilot-sessions/{session_id}/messages", { params: { path: { session_id: id } }, body: { text } })),
    onSettled: (_, __, { id }) => refresh(id),
  });
}

export function useApproveCopilot(project: string) {
  const refresh = useRefresh(project);
  return useMutation({
    mutationFn: (id: number) => unwrap(api.POST("/copilot-sessions/{session_id}/approve", { params: { path: { session_id: id } } })),
    onSettled: (_, __, id) => refresh(id),
  });
}

export function useCancelCopilot(project: string) {
  const refresh = useRefresh(project);
  return useMutation({
    mutationFn: (id: number) => unwrap(api.POST("/copilot-sessions/{session_id}/cancel", { params: { path: { session_id: id } } })),
    onSettled: (_, __, id) => refresh(id),
  });
}

/** Every session of an agent task (before deleting the task); 409 if one is queued or running. */
export function useDeleteTaskSessions(project: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (taskNote: string) =>
      unwrap(api.DELETE("/projects/{project}/copilot-sessions", { params: { path: { project }, query: { task_note: taskNote } } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: copilotKeys.sessions(project) }),
  });
}

export function useDeleteCopilotSession(project: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => unwrap(api.DELETE("/copilot-sessions/{session_id}", { params: { path: { session_id: id } } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: copilotKeys.sessions(project) }),
  });
}
