import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "./client";
import type { components } from "./schema";

/** «🚀 Mbare Pilot»: the app's future changes, from board/roadmap.yml (written by the UI into the data folder). */
export type RoadmapItem = components["schemas"]["RoadmapItem"];
export type RoadmapCard = components["schemas"]["RoadmapCard"];
export type RoadmapStatus = RoadmapItem["status"];

const KEY = ["roadmap"] as const;

export function useRoadmap() {
  return useQuery({ queryKey: KEY, queryFn: () => unwrap(api.GET("/roadmap")) });
}

/** Every write answers with the whole board: it becomes the cache. */
function useWrite<A>(write: (args: A) => Promise<components["schemas"]["Roadmap"]>) {
  const queryClient = useQueryClient();
  return useMutation({ mutationFn: write, onSuccess: (board) => queryClient.setQueryData(KEY, board) });
}

export const useSaveRoadmapHeader = () =>
  useWrite((body: { goal: string; vision: string }) => unwrap(api.PUT("/roadmap/header", { body })));

export const useAddRoadmapItem = () =>
  useWrite((body: RoadmapCard) => unwrap(api.POST("/roadmap/items", { body })));

export const useUpdateRoadmapItem = () =>
  useWrite(({ id, body }: { id: string; body: RoadmapCard }) => unwrap(api.PUT("/roadmap/items/{item_id}", { params: { path: { item_id: id } }, body })));

export const useMoveRoadmapItem = () =>
  useWrite(({ id, status }: { id: string; status: RoadmapStatus }) =>
    unwrap(api.POST("/roadmap/items/{item_id}/move", { params: { path: { item_id: id } }, body: { status } })));

export const useDeleteRoadmapItem = () =>
  useWrite((id: string) => unwrap(api.DELETE("/roadmap/items/{item_id}", { params: { path: { item_id: id } } })));
