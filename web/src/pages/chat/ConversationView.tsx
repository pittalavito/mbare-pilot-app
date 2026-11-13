import { Alert, Box, Button, Card, Group, Loader, ScrollArea, Stack, Text, Textarea } from "@mantine/core";
import { useEffect, useRef, useState } from "react";

import { type Chatbot, useAutomationCache, useConversations, useDeleteConversation, useMessages, useSendMessage } from "../../api/chat";
import { usePipelines } from "../../api/automation";
import { ConfirmButton } from "../../components/ConfirmButton";
import { MessageItem } from "./MessageItem";

/** A chatbot's conversation: the messages (markdown; ```automation blocks become
 * the Architect's proposal) and the box to write. Shown by the agent panel
 * (pages/project/AgentPanel.tsx). A reply arrives whole (no streaming yet). The
 * automation cache controls show only for a chatbot that has the cache (none today). */
export function ConversationView({ chatbot, conversationId, onOpen: open, height = 520, onLinkClick, openNote, draft, context, learnable }: {
  chatbot: Chatbot;
  /** The note a new conversation belongs to (the agent panel); its conversations are those about it. */
  context?: string;
  /** A message to put in the box (not sent): a new ``id`` puts it again. */
  draft?: { text: string; id: number };
  /** The answers that used tools can become automations (the Operator, plan 11). */
  learnable?: boolean;
  /** The note open next to the chat: sent with every message (not saved in it). */
  openNote?: string;
  conversationId: number | undefined;
  onOpen: (id: number | undefined) => void;
  height?: number;
  onLinkClick?: (event: React.MouseEvent, href: string) => void;
}) {
  const conversations = useConversations(chatbot.id, context);
  const known = conversations.data?.some((conversation) => conversation.id === conversationId);
  const current = known ? conversationId : undefined; // a deleted or foreign id: a new conversation
  const messages = useMessages(current);
  const cache = useAutomationCache(chatbot.id);
  const pipelines = usePipelines(chatbot.project_name);
  const send = useSendMessage(chatbot.id, chatbot.project_name);
  const [text, setText] = useState("");
  const [pending, setPending] = useState<string>();
  const bottom = useRef<HTMLDivElement>(null);
  const box = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    if (!draft) return;
    setText(draft.text);
    box.current?.focus();
  }, [draft?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const list = current === undefined ? [] : (messages.data ?? []);
  const hasCache = !!chatbot.automation_cache; // none since the automation chatbot became the Architect (blocco 05): the cache stays in the code
  const automations = hasCache ? (pipelines.data ?? []).filter((pipeline) => pipeline.active && pipeline.steps.length) : [];
  const cacheByMessage = new Map(hasCache ? (cache.data ?? []).flatMap((entry) => (entry.message_id === null ? [] : [[entry.message_id, entry]])) : []);

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "end" }); // braces: browsers may return a promise, not a cleanup
  }, [list.length, pending]);

  const submit = () => {
    const message = text.trim();
    if (!message || send.isPending) return;
    setPending(message);
    setText("");
    send.mutate(
      { conversationId: current, text: message, openNote, context },
      {
        onSuccess: (id) => id !== current && open(id),
        onError: () => setText(message), // to try again
        onSettled: () => setPending(undefined),
      },
    );
  };

  return (
    <Stack gap="sm">
      <Card
        withBorder
        p={0}
        onClickCapture={onLinkClick && ((event: React.MouseEvent) => {
          const link = (event.target as HTMLElement).closest("a");
          const href = link?.getAttribute("href");
          if (href) onLinkClick(event, href);
        })}
      >
        <ScrollArea h={height} p="md">
          <Stack gap="md">
            {!list.length && !pending && (
              <Text size="sm" c="dimmed">Scrivi per iniziare una conversazione con <b>{chatbot.name}</b>.</Text>
            )}
            {list.map((message, index) => (
              <MessageItem
                key={message.id}
                chatbotId={chatbot.id}
                message={message}
                reply={list[index + 1]}
                entry={cacheByMessage.get(message.id)}
                automations={automations}
                learnable={learnable}
              />
            ))}
            {pending && (
              <>
                <MessageItem chatbotId={chatbot.id} message={{ id: -1, conversation_id: 0, role: "user", content: pending, run_id: null, created_at: "" }} automations={[]} />
                <Group gap="xs">
                  <Loader size="xs" type="dots" />
                  <Text size="sm" c="dimmed">{chatbot.name} sta rispondendo…</Text>
                </Group>
              </>
            )}
            <Box ref={bottom} />
          </Stack>
        </ScrollArea>
      </Card>
      {send.error && <Alert color="red">{send.error.message}</Alert>}
      <Group align="flex-end" wrap="nowrap">
        <Textarea
          ref={box}
          style={{ flex: 1 }}
          autosize
          minRows={1}
          maxRows={8}
          placeholder={`Scrivi a ${chatbot.name}… (Invio per mandare, Maiusc+Invio per andare a capo${hasCache ? "; inizia con ! per saltare la cache" : ""})`}
          value={text}
          onChange={(event) => setText(event.currentTarget.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault();
              submit();
            }
          }}
        />
        <Button onClick={submit} loading={send.isPending} disabled={!text.trim()}>Invia</Button>
      </Group>
      {current !== undefined && <DeleteConversation chatbotId={chatbot.id} conversationId={current} onDeleted={() => open(undefined)} />}
    </Stack>
  );
}

function DeleteConversation({ chatbotId, conversationId, onDeleted }: { chatbotId: number; conversationId: number; onDeleted: () => void }) {
  const remove = useDeleteConversation(chatbotId);
  return (
    <ConfirmButton
      size="xs"
      style={{ alignSelf: "flex-start" }}
      message="Eliminare questa conversazione e i suoi messaggi?"
      loading={remove.isPending}
      error={remove.error?.message}
      onConfirm={() => remove.mutate(conversationId, { onSuccess: onDeleted })}
    >
      🗑️ Elimina conversazione
    </ConfirmButton>
  );
}
