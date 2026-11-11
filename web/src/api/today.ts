import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "./client";
import { dataKeys } from "./projectData";
import type { components } from "./schema";

/** «📌 Oggi»: what needs the user in the open project (the panel at the top of
 * the Attività tab), computed by the app; and the two quick actions on an item. */

export type Today = components["schemas"]["Today"];
export type TodayItem = components["schemas"]["TodayItem"];

const todayKey = (project: string) => ["projects", project, "today"] as const;

/** Refreshed every minute, and after any change to the project's notes (``invalidateToday``). */
export function useToday(project: string) {
  return useQuery({
    queryKey: todayKey(project),
    queryFn: () => unwrap(api.GET("/projects/{project}/today", { params: { path: { project } } })),
    refetchInterval: 60_000,
  });
}

/** The panel and the activities: both change when an item does. */
function useRefresh(project: string) {
  const queryClient = useQueryClient();
  return () => Promise.all([
    queryClient.invalidateQueries({ queryKey: todayKey(project) }),
    queryClient.invalidateQueries({ queryKey: dataKeys.activities(project) }),
  ]);
}

/** ✅ Spunta: the item done (checked against its text: 409 when it changed meanwhile). */
export function useCheckItem(project: string) {
  const refresh = useRefresh(project);
  return useMutation({
    mutationFn: ({ activity, item, text }: { activity: string; item: number; text: string }) =>
      unwrap(api.POST("/projects/{project}/activities/{note}/items/{item}/check", {
        params: { path: { project, note: activity, item } }, body: { text },
      })),
    onSettled: refresh,
  });
}

/** 📅 Rimanda: the item's new due date. */
export function useSetDue(project: string) {
  const refresh = useRefresh(project);
  return useMutation({
    mutationFn: ({ activity, item, text, due }: { activity: string; item: number; text: string; due: string }) =>
      unwrap(api.POST("/projects/{project}/activities/{note}/items/{item}/due", {
        params: { path: { project, note: activity, item } }, body: { text, due },
      })),
    onSettled: refresh,
  });
}

export { todayKey };
