import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "./client";
import type { components } from "./schema";

/** Agents, roles and their versioned system prompts, with a scope: the Library
 * (``scope`` null, global ones) or a project (its own ones). */

export type Agent = components["schemas"]["AgentResponse"];
export type AgentCreateRequest = components["schemas"]["AgentCreateRequest"];
export type AgentUpdateRequest = components["schemas"]["AgentUpdateRequest"];
export type Role = components["schemas"]["RoleResponse"];
export type Prompt = components["schemas"]["PromptResponse"];
export type Scope = string | null;

const query = (scope: Scope, includeGlobal = false) => (scope === null ? {} : { project: scope, include_global: includeGlobal });

export const agentKeys = {
  agents: (scope: Scope) => ["agents", scope ?? "global"] as const,
  roles: (scope: Scope, includeGlobal = false) => ["roles", scope ?? "global", includeGlobal] as const,
  prompts: (role: string) => ["roles", "prompts", role] as const,
};

export function useAgents(scope: Scope) {
  return useQuery({ queryKey: agentKeys.agents(scope), queryFn: () => unwrap(api.GET("/agents", { params: { query: query(scope) } })) });
}

/** Create (``name`` undefined) or update an agent. */
export function useSaveAgent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ name, create, update }: { name?: string; create?: AgentCreateRequest; update?: AgentUpdateRequest }) =>
      unwrap(
        name === undefined
          ? api.POST("/agents", { body: create! })
          : api.PUT("/agents/{name}", { params: { path: { name } }, body: update! }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["agents"] }),
  });
}

export function useDeleteAgent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => unwrap(api.DELETE("/agents/{name}", { params: { path: { name } } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["agents"] }),
  });
}

/** The roles of the scope; a project's agents may also use the global ones. */
export function useRoles(scope: Scope, includeGlobal = false) {
  return useQuery({
    queryKey: agentKeys.roles(scope, includeGlobal),
    queryFn: () => unwrap(api.GET("/roles", { params: { query: query(scope, includeGlobal) } })),
  });
}

export function useCreateRole(scope: Scope) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ name, description }: { name: string; description: string }) =>
      unwrap(api.POST("/roles", { body: { name, project_name: scope, description } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["roles"] }),
  });
}

export function useSetRoleActive() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ name, active }: { name: string; active: boolean }) =>
      unwrap(api.PATCH("/roles/{name}", { params: { path: { name } }, body: { active } })),
    onSuccess: () => Promise.all([queryClient.invalidateQueries({ queryKey: ["roles"] }), queryClient.invalidateQueries({ queryKey: ["agents"] })]),
  });
}

/** The versions of a role's prompt, newest first. */
export function usePrompts(role: string | undefined) {
  return useQuery({
    queryKey: agentKeys.prompts(role ?? ""),
    queryFn: () => unwrap(api.GET("/roles/{name}/prompts", { params: { path: { name: role! } } })),
    enabled: !!role,
  });
}

/** A new version; ``created`` false when the text equals the latest one. */
export function useCreatePrompt(role: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (text: string) => unwrap(api.POST("/roles/{name}/prompts", { params: { path: { name: role } }, body: { text } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: agentKeys.prompts(role) }),
  });
}

export function useSetPromptActive(role: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, active }: { id: number; active: boolean }) =>
      unwrap(api.PATCH("/prompts/{prompt_id}", { params: { path: { prompt_id: id } }, body: { active } })),
    onSuccess: () => Promise.all([queryClient.invalidateQueries({ queryKey: agentKeys.prompts(role) }), queryClient.invalidateQueries({ queryKey: ["agents"] })]),
  });
}
