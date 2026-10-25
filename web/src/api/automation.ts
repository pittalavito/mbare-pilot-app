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
export type FunctionSpec = components["schemas"]["FunctionResponse"];
export type Agent = components["schemas"]["AgentResponse"];
export type Tool = components["schemas"]["ToolResponse"];

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

// ------------------------------------------------------------- catalogs

export function useFunctions() {
  return useQuery({ queryKey: ["functions"], queryFn: () => unwrap(api.GET("/functions")), staleTime: 60_000 });
}

/** The agents a step can use: the project's and the Library's. */
export function useStepAgents(project: string) {
  return useQuery({
    queryKey: ["agents", project, "with-global"],
    queryFn: () => unwrap(api.GET("/agents", { params: { query: { project, include_global: true } } })),
  });
}

export function useModelChoices() {
  return useQuery({ queryKey: ["models", "choices"], queryFn: () => unwrap(api.GET("/models/choices")), staleTime: 60_000 });
}

/** The tools an automation's agent can use (not the chatbot's own ones). */
export function useStepTools() {
  return useQuery({
    queryKey: ["tools"],
    queryFn: () => unwrap(api.GET("/tools")),
    staleTime: 60_000,
    select: (tools: Tool[]) => tools.filter((tool) => tool.available && !tool.chatbot_only),
  });
}
