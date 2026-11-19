import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "./client";
import { dataKeys } from "./projectData";
import type { components } from "./schema";
import { todayKey } from "./today";

/** An activity's steps «Pianifica», «Lavora», «Chiudi» (plan 18): the
 * Pianificatore's proposals, creating the tasks, the round and its settings,
 * what was learned and the closing. */

export type ActivityPath = components["schemas"]["ActivityPath"];
export type ActivityPlan = components["schemas"]["ActivityPlan"];
export type PlanProposal = components["schemas"]["PlanProposal"];
export type PlanChoice = components["schemas"]["PlanChoice"];
export type PathTask = components["schemas"]["PathTask"];
export type PathStep = components["schemas"]["PathStep"];

/** The round is moving by itself (Copilot works, or the worker is about to prepare and delegate): refreshed. */
export function pathMoving(path: ActivityPath | undefined): boolean {
  if (!path?.plan || !path.tasks.length) return false;
  if (path.tasks.some((task) => task.steps.some((step) => step.state === "running"))) return true;
  const current = path.tasks.find((task) => task.current);
  const step = current?.steps.find((item) => item.state !== "done" && item.state !== "skipped");
  if (path.plan.paused || !step) return false;
  return (["prepare", "delegate", "after"].includes(step.key) && step.state === "todo")
    || (step.key === "copilot_plan" && step.state === "you" && !!path.plan.auto_approve);
}

const pathKey = (project: string, activity: string) => ["projects", project, "activities", activity, "path"] as const;

/** The plan (proposals waiting, tasks with their steps, the summary), refreshed while the round moves. */
export function useActivityPath(project: string, activity: string) {
  return useQuery({
    queryKey: pathKey(project, activity),
    queryFn: () => unwrap(api.GET("/projects/{project}/activities/{activity}/path", { params: { path: { project, activity } } })),
    refetchInterval: (query) => (pathMoving(query.state.data) ? 4000 : false),
  });
}

/** After a change: the path, the notes (tasks, the activity's items) and «Oggi». */
function useRefresh(project: string, activity: string) {
  const queryClient = useQueryClient();
  return () => {
    queryClient.invalidateQueries({ queryKey: pathKey(project, activity) });
    queryClient.invalidateQueries({ queryKey: dataKeys.typed(project) });
    queryClient.invalidateQueries({ queryKey: todayKey(project) });
  };
}

export function useProposePlan(project: string, activity: string) {
  const refresh = useRefresh(project, activity);
  return useMutation({
    mutationFn: () => unwrap(api.POST("/projects/{project}/activities/{activity}/plan", { params: { path: { project, activity } } })),
    onSuccess: refresh,
  });
}

export function useConfirmPlan(project: string, activity: string) {
  const refresh = useRefresh(project, activity);
  return useMutation({
    mutationFn: (choices: PlanChoice[]) =>
      unwrap(api.POST("/projects/{project}/activities/{activity}/plan/confirm", { params: { path: { project, activity } }, body: { choices } })),
    onSuccess: refresh,
  });
}

export function useDismissPlan(project: string, activity: string) {
  const refresh = useRefresh(project, activity);
  return useMutation({
    mutationFn: () => unwrap(api.POST("/projects/{project}/activities/{activity}/plan/dismiss", { params: { path: { project, activity } } })),
    onSuccess: refresh,
  });
}

export function usePausePlan(project: string, activity: string) {
  const refresh = useRefresh(project, activity);
  return useMutation({
    mutationFn: (paused: boolean) =>
      unwrap(api.POST("/projects/{project}/activities/{activity}/plan/pause", { params: { path: { project, activity } }, body: { paused } })),
    onSuccess: refresh,
  });
}

type StepBody = components["schemas"]["StepRequest"];

export function useRetryStep(project: string, activity: string) {
  const refresh = useRefresh(project, activity);
  return useMutation({
    mutationFn: (body: StepBody) =>
      unwrap(api.POST("/projects/{project}/activities/{activity}/plan/retry", { params: { path: { project, activity } }, body })),
    onSuccess: refresh,
  });
}

/** «✅ Fatto» on a pre/post development task (plan 22): done by Dev or by hand, the round goes on. */
export function useMarkDone(project: string, activity: string) {
  const refresh = useRefresh(project, activity);
  return useMutation({
    mutationFn: (task: string) =>
      unwrap(api.POST("/projects/{project}/activities/{activity}/plan/done", { params: { path: { project, activity } }, body: { task } })),
    onSuccess: refresh,
  });
}

/** «🤖 Automatico» on a pre/post development task (plan 25): its commands, then its automation, run by the worker;
 * ``pending_commands`` = commands not allowed, nothing started (answer them, then again). */
export function useStartAuto(project: string, activity: string) {
  const refresh = useRefresh(project, activity);
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (task: string) =>
      unwrap(api.POST("/projects/{project}/activities/{activity}/plan/auto", { params: { path: { project, activity } }, body: { task } })),
    onSuccess: () => {
      refresh();
      queryClient.invalidateQueries({ queryKey: ["projects", project, "command-requests"] });
    },
  });
}

export type OperationRun = components["schemas"]["OperationRun"];

export type PlanOptions = components["schemas"]["PlanOptions"];

/** The automatic ok to Copilot's plan. */
export function useSetPlanOptions(project: string, activity: string) {
  const refresh = useRefresh(project, activity);
  return useMutation({
    mutationFn: (body: PlanOptions) =>
      unwrap(api.POST("/projects/{project}/activities/{activity}/plan/options", { params: { path: { project, activity } }, body })),
    onSuccess: refresh,
  });
}

export type LearnedDraft = components["schemas"]["LearnedDraft"];

/** «✨ Proponi cosa ho imparato»: one call to the agent ``imparato``. */
export function useProposeLearned(project: string, activity: string) {
  return useMutation({
    mutationFn: () => unwrap(api.POST("/projects/{project}/activities/{activity}/learned", { params: { path: { project, activity } } })),
  });
}

/** «✅ Chiudi attività»: what was learned at the top of context/imparato.md, the activity done. */
export function useCloseActivity(project: string, activity: string) {
  const refresh = useRefresh(project, activity);
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (learned: string) =>
      unwrap(api.POST("/projects/{project}/activities/{activity}/close", { params: { path: { project, activity } }, body: { learned } })),
    onSuccess: () => { refresh(); queryClient.invalidateQueries({ queryKey: ["projects", project, "context"] }); },
  });
}

/** «🗄 Archivia» (plan 33): a summary note stays; the activity, its tasks and the references chosen go. */
export function useArchiveActivity(project: string, activity: string) {
  const refresh = useRefresh(project, activity);
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (deleteReferences: string[]) =>
      unwrap(api.POST("/projects/{project}/activities/{activity}/archive", {
        params: { path: { project, activity } }, body: { delete_references: deleteReferences },
      })),
    onSuccess: () => { refresh(); queryClient.invalidateQueries({ queryKey: ["projects", project] }); },
  });
}

/** «↩ Riapri»: back to «in progress». */
export function useReopenActivity(project: string, activity: string) {
  const refresh = useRefresh(project, activity);
  return useMutation({
    mutationFn: () => unwrap(api.POST("/projects/{project}/activities/{activity}/reopen", { params: { path: { project, activity } } })),
    onSuccess: refresh,
  });
}
