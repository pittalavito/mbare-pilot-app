import { useMutation, useQuery } from "@tanstack/react-query";

import { api, unwrap } from "./client";
import type { components } from "./schema";

/** What agents can be built with, shared by the editors (chatbot, automation steps). */

export type Agent = components["schemas"]["AgentResponse"];
export type Tool = components["schemas"]["ToolResponse"];

export function useModelChoices() {
  return useQuery({ queryKey: ["models", "choices"], queryFn: () => unwrap(api.GET("/models/choices")), staleTime: 60_000 });
}

/** The tools that can be used now; ``chatbot`` false leaves out the chatbot's own ones. */
export function useTools({ chatbot }: { chatbot: boolean }) {
  return useQuery({
    queryKey: ["tools"],
    queryFn: () => unwrap(api.GET("/tools")),
    staleTime: 60_000,
    select: (tools: Tool[]) => tools.filter((tool) => tool.available && (chatbot || !tool.chatbot_only)),
  });
}

export type ToolSpec = components["schemas"]["ToolSpecResponse"];
export type ToolArg = components["schemas"]["ToolArgResponse"];
export type ToolTry = components["schemas"]["ToolTryResponse"];

/** Every tool of the registry with its arguments (plan 15): a step offers the non chat-only ones. */
export function useToolSpecs() {
  return useQuery({ queryKey: ["tool-specs"], queryFn: () => unwrap(api.GET("/tool-specs")), staleTime: 60_000 });
}

/** Admin → Tool, «▶️ Prova»: a tool on a project with these arguments, no LLM. */
export function useTryTool() {
  return useMutation({
    mutationFn: ({ name, project, args }: { name: string; project: string; args: Record<string, unknown> }) =>
      unwrap(api.POST("/tools/{name}/try", { params: { path: { name } }, body: { project, args } })),
  });
}

/** The agents a step can use: the project's and the Library's. */
export function useStepAgents(project: string) {
  return useQuery({
    queryKey: ["agents", project, "with-global"],
    queryFn: () => unwrap(api.GET("/agents", { params: { query: { project, include_global: true } } })),
  });
}
