import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "./client";
import type { components } from "./schema";

/** Admin → «Richieste di tool» (plan 20): the tools the Architetto asked for,
 * worked by Claude Code through its MCP server (/mcp-dev, with a token). */

export type ToolRequest = components["schemas"]["ToolRequest"];

const key = ["admin", "tool-requests"] as const;

export function useToolRequests() {
  return useQuery({ queryKey: key, queryFn: () => unwrap(api.GET("/admin/tool-requests")), refetchInterval: 15_000 });
}

/** A new token for Claude Code (shown once; the old one stops working) and the command to add the server. */
export function useNewDevToken() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/admin/tool-requests/token")),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: key }),
  });
}

export function useDismissToolRequest() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, reason }: { id: number; reason: string }) =>
      unwrap(api.POST("/admin/tool-requests/{request_id}/dismiss", { params: { path: { request_id: id } }, body: { reason } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: key }),
  });
}
