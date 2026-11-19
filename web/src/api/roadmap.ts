import { useQuery } from "@tanstack/react-query";

import { api, unwrap } from "./client";
import type { components } from "./schema";

/** «🚀 Mbare Pilot» (plan 30): the app's future activities, from roadmap.yml of the definitions. */
export type Roadmap = components["schemas"]["Roadmap"];
export type RoadmapItem = components["schemas"]["RoadmapItem"];

export function useRoadmap() {
  return useQuery({ queryKey: ["roadmap"], queryFn: () => unwrap(api.GET("/roadmap")) });
}
