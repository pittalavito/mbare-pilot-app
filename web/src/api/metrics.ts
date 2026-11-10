import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "./client";
import type { components } from "./schema";

/** The Metriche page: the numbers (cost and latency per agent, Copilot apart,
 * the WIP acceptance) and the evaluations (queued for the worker, their reports). */

export type Metrics = components["schemas"]["MetricsResponse"];
export type EvaluationRun = components["schemas"]["EvaluationRun"];

const keys = {
  metrics: (days: number | null, project: string | null) => ["observability", "metrics", days, project] as const,
  evaluations: ["observability", "evaluations"] as const,
};

export function useMetrics(days: number | null, project: string | null) {
  return useQuery({
    queryKey: keys.metrics(days, project),
    queryFn: () => unwrap(api.GET("/observability/metrics", { params: { query: { days: days ?? undefined, project: project ?? undefined } } })),
  });
}

/** The evaluations launched from the page and every report; refreshed while one is queued or running. */
export function useEvaluations() {
  return useQuery({
    queryKey: keys.evaluations,
    queryFn: () => unwrap(api.GET("/observability/evaluations")),
    refetchInterval: (query) => (query.state.data?.runs.some((run) => run.status === "queued" || run.status === "running") ? 3000 : false),
  });
}

export function useLaunchEvaluation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ kind, models = [], embedders = [] }: { kind: "wip" | "rag"; models?: string[]; embedders?: string[] }) =>
      unwrap(api.POST("/observability/evaluations", { body: { kind, models, embedders } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.evaluations }),
  });
}

/** A report's markdown, to read it in the page. */
export function useEvaluationReport(name: string | undefined) {
  return useQuery({
    queryKey: ["observability", "evaluations", "report", name],
    queryFn: () => unwrap(api.GET("/observability/evaluations/reports/{name}", {
      params: { path: { name: name! }, query: { format: "md" } }, parseAs: "text",
    })) as Promise<string>,
    enabled: !!name,
  });
}

export const reportUrl = (name: string, format: "md" | "json" = "md") =>
  `${window.location.origin}/api/observability/evaluations/reports/${encodeURIComponent(name)}?format=${format}`;
