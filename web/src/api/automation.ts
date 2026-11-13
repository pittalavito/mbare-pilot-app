import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "./client";
import type { components } from "./schema";

export type Pipeline = components["schemas"]["PipelineResponse"];
export type PipelineRequest = components["schemas"]["PipelineRequest"];
export type Step = components["schemas"]["StepBody"];
export type StepAgent = components["schemas"]["StepAgentBody"];
export type Edge = components["schemas"]["EdgeBody"];
export type Run = components["schemas"]["RunResponse"];
export type StepRun = components["schemas"]["StepRunResponse"];

export const automationKeys = {
  pipelines: (project: string) => ["projects", project, "pipelines"] as const,
  runs: (pipelineId: number) => ["pipelines", pipelineId, "runs"] as const,
};

/** A run is over once it is done or failed: until then the history polls. */
export const isFinished = (run: Run) => run.status === "done" || run.status === "failed";

export function usePipelines(project: string) {
  return useQuery({
    queryKey: automationKeys.pipelines(project),
    queryFn: () => unwrap(api.GET("/projects/{project}/pipelines", { params: { path: { project } } })),
  });
}

/** The history of an automation, refreshed every 2 seconds while a run is queued or running. */
export function useRuns(pipelineId: number | undefined) {
  return useQuery({
    queryKey: automationKeys.runs(pipelineId ?? 0),
    queryFn: () => unwrap(api.GET("/pipelines/{pipeline_id}/runs", { params: { path: { pipeline_id: pipelineId! } } })),
    enabled: pipelineId !== undefined,
    refetchInterval: (query) => (query.state.data?.some((run) => !isFinished(run)) ? 2_000 : false),
  });
}

export function useEnqueueRun(pipelineId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: string) =>
      unwrap(api.POST("/pipelines/{pipeline_id}/runs", { params: { path: { pipeline_id: pipelineId } }, body: { input } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: automationKeys.runs(pipelineId) }),
  });
}

export function useDeleteRun(pipelineId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (runId: number) => unwrap(api.DELETE("/pipeline-runs/{run_id}", { params: { path: { run_id: runId } } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: automationKeys.runs(pipelineId) }),
  });
}

/** Create (``id`` undefined) or update an automation. */
export function useSavePipeline(project: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id?: number; body: PipelineRequest }) =>
      unwrap(
        id === undefined
          ? api.POST("/projects/{project}/pipelines", { params: { path: { project } }, body })
          : api.PUT("/pipelines/{pipeline_id}", { params: { path: { pipeline_id: id } }, body }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: automationKeys.pipelines(project) }),
  });
}

export function useDeletePipeline(project: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => unwrap(api.DELETE("/pipelines/{pipeline_id}", { params: { path: { pipeline_id: id } } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: automationKeys.pipelines(project) }),
  });
}

// -------------------------------------------------------------------- YAML

export type AutomationCheck = components["schemas"]["AutomationYamlCheckResponse"];

/** An automation in YAML (the Architect's proposal) validated as a save would; nothing saved. */
export function useCheckAutomationYaml(project: string, yaml: string) {
  return useQuery({
    queryKey: ["projects", project, "pipelines", "yaml-check", yaml],
    queryFn: () => unwrap(api.POST("/projects/{project}/pipelines/yaml/check", { params: { path: { project } }, body: { yaml } })),
    retry: false,
  });
}

/** «Salva» of a proposal: created, or the automation with the same name updated. */
export function useSaveAutomationYaml(project: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (yaml: string) => unwrap(api.POST("/projects/{project}/pipelines/yaml", { params: { path: { project } }, body: { yaml } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: automationKeys.pipelines(project) }),
  });
}

/** «Esporta YAML»: the automation in the definitions' format. */
export function useExportAutomationYaml() {
  return useMutation({
    mutationFn: (pipelineId: number) => unwrap(api.GET("/pipelines/{pipeline_id}/yaml", { params: { path: { pipeline_id: pipelineId } } })),
  });
}

export type LearnDraft = components["schemas"]["LearnDraft"];
export type LearnedStep = components["schemas"]["LearnedStep"];
export type LearnRequest = components["schemas"]["LearnRequest"];

/** «✅ Giusto: fanne un'automation» (plan 11): what the agent did right in an answer (404 once its trace expired). */
export function useLearnDraft() {
  return useMutation({
    mutationFn: (messageId: number) => unwrap(api.GET("/messages/{message_id}/learn-draft", { params: { path: { message_id: messageId } } })),
  });
}

export function useSaveLearned(project: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: LearnRequest) => unwrap(api.POST("/projects/{project}/pipelines/learned", { params: { path: { project } }, body })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: automationKeys.pipelines(project) }),
  });
}

/** The values of an automation's fields as its run input (a JSON object). */
export const fieldsInput = (values: Record<string, string>) => JSON.stringify(values);
