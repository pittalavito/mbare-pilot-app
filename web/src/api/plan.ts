import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "./client";
import { dataKeys } from "./projectData";
import type { components } from "./schema";
import { todayKey } from "./today";

/** «▶️ Lavora attività» (plan 12a): the Pianificatore's proposals for an
 * activity, confirming them (the tasks are created), the activity's path and
 * «Conferma del task». */

export type ActivityPath = components["schemas"]["ActivityPath"];
export type ActivityPlan = components["schemas"]["ActivityPlan"];
export type PlanProposal = components["schemas"]["PlanProposal"];
export type PlanChoice = components["schemas"]["PlanChoice"];
export type PathTask = components["schemas"]["PathTask"];
export type PathStep = components["schemas"]["PathStep"];

/** The path is moving by itself (Copilot works, or the worker is about to prepare and delegate): refreshed. */
export function pathMoving(path: ActivityPath | undefined): boolean {
  if (!path?.plan || path.plan.status !== "confirmed") return false;
  if (path.tasks.some((task) => task.steps.some((step) => step.state === "running"))) return true;
  const current = path.tasks.find((task) => task.current);
  const step = current?.steps.find((item) => item.state !== "done" && item.state !== "skipped");
  if (path.plan.paused || !step) return false;
  return (["before", "prepare", "delegate", "after"].includes(step.key) && step.state === "todo")
    || (step.key === "copilot_plan" && step.state === "you" && !!path.plan.auto_approve);
}

const pathKey = (project: string, activity: string) => ["projects", project, "activities", activity, "path"] as const;

/** The plan waiting for a choice, or the confirmed one with each task's steps (refreshed while Copilot works). */
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

/** «Conferma del task»: from «in refinement» to «to do». */
export function useConfirmTask(project: string, activity: string) {
  const refresh = useRefresh(project, activity);
  return useMutation({
    mutationFn: (task: string) => unwrap(api.POST("/projects/{project}/agent-tasks/{task}/confirm", { params: { path: { project, task } } })),
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

/** How the path prepares the repositories: ``""`` (automatic), ``none``, ``dev``, ``learned:<id>``. */
export function useSetPrepare(project: string, activity: string) {
  const refresh = useRefresh(project, activity);
  return useMutation({
    mutationFn: (prepare: string) =>
      unwrap(api.POST("/projects/{project}/activities/{activity}/plan/prepare", { params: { path: { project, activity } }, body: { prepare } })),
    onSuccess: refresh,
  });
}

type StepBody = components["schemas"]["StepRequest"];

export function useSkipStep(project: string, activity: string) {
  const refresh = useRefresh(project, activity);
  return useMutation({
    mutationFn: (body: StepBody) =>
      unwrap(api.POST("/projects/{project}/activities/{activity}/plan/skip", { params: { path: { project, activity } }, body })),
    onSuccess: refresh,
  });
}

export function useRetryStep(project: string, activity: string) {
  const refresh = useRefresh(project, activity);
  return useMutation({
    mutationFn: (body: StepBody) =>
      unwrap(api.POST("/projects/{project}/activities/{activity}/plan/retry", { params: { path: { project, activity } }, body })),
    onSuccess: refresh,
  });
}

export type PlanOptions = components["schemas"]["PlanOptions"];

/** 12c: the automations before and after each task and the automatic ok to Copilot's plan. */
export function useSetPlanOptions(project: string, activity: string) {
  const refresh = useRefresh(project, activity);
  return useMutation({
    mutationFn: (body: PlanOptions) =>
      unwrap(api.POST("/projects/{project}/activities/{activity}/plan/options", { params: { path: { project, activity } }, body })),
    onSuccess: refresh,
  });
}
