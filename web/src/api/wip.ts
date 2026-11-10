import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "./client";
import { dataKeys } from "./projectData";
import type { components } from "./schema";

/** «Elabora WIP»: the note's state, the preview of what the secretary's model
 * would get (masked), the call that gives the proposals, applying the chosen ones. */

export type WipPreview = components["schemas"]["WipPreview"];
export type WipProposal = components["schemas"]["WipProposal"];
export type WipResult = components["schemas"]["WipResult"];
export type WipApplied = components["schemas"]["WipApplied"];
export type WipChoice = components["schemas"]["WipChoice"];

export const WIP_NOTE = "wip.md";

export const wipKeys = {
  state: (project: string) => ["projects", project, "wip"] as const,
};

/** The note (``""`` when missing) and the words of its new text. */
export function useWipState(project: string) {
  return useQuery({
    queryKey: wipKeys.state(project),
    queryFn: () => unwrap(api.GET("/projects/{project}/wip", { params: { path: { project } } })),
  });
}

/** What the model would get, masked; the ``mask{}`` terms enter the map. */
export function useWipPreview(project: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (paragraphs: number | null) =>
      unwrap(api.POST("/projects/{project}/wip/preview", { params: { path: { project } }, body: { paragraphs } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["projects", project, "masking"] }),
  });
}

/** One call to the secretary's model: the proposals, in clear. */
export function useProcessWip(project: string) {
  return useMutation({
    mutationFn: (paragraphs: number | null) =>
      unwrap(api.POST("/projects/{project}/wip/process", { params: { path: { project } }, body: { paragraphs } })),
  });
}

/** The proposals closed without applying any: all of them count as discarded (metrics), no sign. */
export function useDismissWip(project: string) {
  return useMutation({
    mutationFn: (runId: string) =>
      unwrap(api.POST("/projects/{project}/wip/dismiss", { params: { path: { project } }, body: { run_id: runId } })),
  });
}

/** The chosen proposals, then the sign in the note. */
export function useApplyWip(project: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { run_id: string; choices: WipChoice[] }) =>
      unwrap(api.POST("/projects/{project}/wip/apply", { params: { path: { project } }, body })),
    onSettled: () => Promise.all([
      queryClient.invalidateQueries({ queryKey: wipKeys.state(project) }),
      queryClient.invalidateQueries({ queryKey: dataKeys.note(project, WIP_NOTE) }),
      queryClient.invalidateQueries({ queryKey: dataKeys.typed(project) }),
    ]),
  });
}
