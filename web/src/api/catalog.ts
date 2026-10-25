import { useQuery } from "@tanstack/react-query";

import { api, unwrap } from "./client";
import type { components } from "./schema";

/** What agents can be built with, shared by the editors (chatbot, automation steps). */

export type FunctionSpec = components["schemas"]["FunctionResponse"];
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
