import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "./client";
import type { components } from "./schema";

export type Chatbot = components["schemas"]["ChatbotResponse"];
export type ChatbotRequest = components["schemas"]["ChatbotRequest"];
export type Conversation = components["schemas"]["ConversationResponse"];
export type Message = components["schemas"]["MessageResponse"];
export type ChatRoute = components["schemas"]["ChatRouteResponse"];

/** Starts the replies given from the cache (CACHE_MARK of the backend). */
export const CACHE_MARK = "⚡";

export const chatKeys = {
  chatbots: (project: string) => ["projects", project, "chatbots"] as const,
  conversations: (chatbotId: number) => ["chatbots", chatbotId, "conversations"] as const,
  messages: (conversationId: number) => ["conversations", conversationId, "messages"] as const,
  routes: (chatbotId: number) => ["chatbots", chatbotId, "routes"] as const,
};

export function useChatbots(project: string) {
  return useQuery({
    queryKey: chatKeys.chatbots(project),
    queryFn: () => unwrap(api.GET("/projects/{project}/chatbots", { params: { path: { project } } })),
  });
}

/** Create (``id`` undefined) or update a chatbot. */
export function useSaveChatbot(project: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id?: number; body: ChatbotRequest }) =>
      unwrap(
        id === undefined
          ? api.POST("/projects/{project}/chatbots", { params: { path: { project } }, body })
          : api.PUT("/chatbots/{chatbot_id}", { params: { path: { chatbot_id: id } }, body }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: chatKeys.chatbots(project) }),
  });
}

export function useDeleteChatbot(project: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => unwrap(api.DELETE("/chatbots/{chatbot_id}", { params: { path: { chatbot_id: id } } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: chatKeys.chatbots(project) }),
  });
}

/** Most recently updated first. */
export function useConversations(chatbotId: number) {
  return useQuery({
    queryKey: chatKeys.conversations(chatbotId),
    queryFn: () => unwrap(api.GET("/chatbots/{chatbot_id}/conversations", { params: { path: { chatbot_id: chatbotId } } })),
  });
}

export function useDeleteConversation(chatbotId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => unwrap(api.DELETE("/conversations/{conversation_id}", { params: { path: { conversation_id: id } } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: chatKeys.conversations(chatbotId) }),
  });
}

/** Oldest first; none for a conversation not created yet. */
export function useMessages(conversationId: number | undefined) {
  return useQuery({
    queryKey: chatKeys.messages(conversationId ?? 0),
    queryFn: () => unwrap(api.GET("/conversations/{conversation_id}/messages", { params: { path: { conversation_id: conversationId! } } })),
    enabled: conversationId !== undefined,
  });
}

/** Send a message, creating the conversation first when there is none; the
 * reply arrives whole. Resolves to the conversation the message went to. */
export function useSendMessage(chatbotId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ conversationId, text }: { conversationId?: number; text: string }) => {
      const id =
        conversationId ??
        (await unwrap(api.POST("/chatbots/{chatbot_id}/conversations", { params: { path: { chatbot_id: chatbotId } } }))).id;
      await unwrap(api.POST("/conversations/{conversation_id}/messages", { params: { path: { conversation_id: id } }, body: { text } }));
      return id;
    },
    onSettled: (id) =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: chatKeys.conversations(chatbotId) }), // new one, title, order
        id !== undefined && queryClient.invalidateQueries({ queryKey: chatKeys.messages(id) }),
        queryClient.invalidateQueries({ queryKey: chatKeys.routes(chatbotId) }), // hits
      ]),
  });
}

export function useRoutes(chatbotId: number) {
  return useQuery({
    queryKey: chatKeys.routes(chatbotId),
    queryFn: () => unwrap(api.GET("/chatbots/{chatbot_id}/routes", { params: { path: { chatbot_id: chatbotId } } })),
  });
}

/** Put a user message in the cache: similar messages will launch the automation. */
export function useAddRoute(chatbotId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ messageId, pipelineId, input }: { messageId: number; pipelineId: number; input: string }) =>
      unwrap(api.POST("/messages/{message_id}/route", { params: { path: { message_id: messageId } }, body: { pipeline_id: pipelineId, input } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: chatKeys.routes(chatbotId) }),
  });
}

export function useDeleteRoute(chatbotId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (routeId: number) => unwrap(api.DELETE("/chat-routes/{route_id}", { params: { path: { route_id: routeId } } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: chatKeys.routes(chatbotId) }),
  });
}
