import { Alert, Box, Button, Card, Grid, Group, Loader, NavLink, ScrollArea, Stack, Text, Textarea } from "@mantine/core";
import { useEffect, useRef, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";

import { type Chatbot, useChatbots, useConversations, useDeleteConversation, useMessages, useRoutes, useSendMessage } from "../../api/chat";
import { usePipelines } from "../../api/automation";
import { ConfirmButton } from "../../components/ConfirmButton";
import { ChatbotModal } from "./ChatbotModal";
import { MessageItem } from "./MessageItem";

/** The Chat tab of a project: its chatbot (one per project), its conversations
 * on the left and the open one (``?c=``) on the right. A reply arrives whole
 * (no streaming yet). A message starting with ``!`` skips the cache. */
export function ChatTab() {
  const { project = "" } = useParams();
  const chatbots = useChatbots(project);
  const [editing, setEditing] = useState(false);

  if (chatbots.isPending) return <Loader size="sm" />;
  if (chatbots.error) return <Alert color="red">{chatbots.error.message}</Alert>;
  const chatbot = chatbots.data[0]; // one per project (the first by name, if more were created before)
  const modal = <ChatbotModal project={project} chatbot={chatbot} opened={editing} onClose={() => setEditing(false)} />;
  if (!chatbot) {
    return (
      <Stack align="flex-start">
        <Text c="dimmed">Nessun chatbot: crea quello del progetto e configura il suo agente (prompt, modello, tool).</Text>
        <Button onClick={() => setEditing(true)}>➕ Crea il chatbot</Button>
        {modal}
      </Stack>
    );
  }
  return (
    <Grid gutter="md">
      <Grid.Col span={{ base: 12, md: 3 }}>
        <Sidebar chatbot={chatbot} onEdit={() => setEditing(true)} />
      </Grid.Col>
      <Grid.Col span={{ base: 12, md: 9 }}>
        <ConversationView key={chatbot.id} chatbot={chatbot} />
      </Grid.Col>
      {modal}
    </Grid>
  );
}

/** ``?c=`` is the open conversation; none = a new one, created on the first message. */
function useOpenConversation(): [number | undefined, (id: number | undefined) => void] {
  const [search, setSearch] = useSearchParams();
  const value = search.get("c");
  const open = (id: number | undefined) => setSearch(id === undefined ? {} : { c: String(id) }, { replace: true });
  return [value ? Number(value) : undefined, open];
}

function Sidebar({ chatbot, onEdit }: { chatbot: Chatbot; onEdit: () => void }) {
  const conversations = useConversations(chatbot.id);
  const [openId, open] = useOpenConversation();
  return (
    <Stack gap="xs">
      <Group justify="space-between" wrap="nowrap">
        <Text fw={600}>{chatbot.name}</Text>
        <Button size="xs" variant="default" onClick={onEdit}>✏️ Modifica</Button>
      </Group>
      <Text size="xs" c="dimmed">
        <code>{chatbot.model}</code> · prompt v{chatbot.prompt_version} · {chatbot.tool_names.join(", ") || "nessun tool"}
      </Text>
      {chatbot.description && <Text size="xs" c="dimmed">{chatbot.description}</Text>}
      <Button variant="light" onClick={() => open(undefined)}>💬 Nuova conversazione</Button>
      <ScrollArea.Autosize mah={480}>
        {conversations.data?.map((conversation) => (
          <NavLink
            key={conversation.id}
            label={conversation.title || "Nuova conversazione"}
            active={conversation.id === openId}
            onClick={() => open(conversation.id)}
          />
        ))}
        {conversations.data && !conversations.data.length && <Text size="sm" c="dimmed">Nessuna conversazione.</Text>}
      </ScrollArea.Autosize>
    </Stack>
  );
}

function ConversationView({ chatbot }: { chatbot: Chatbot }) {
  const [conversationId, open] = useOpenConversation();
  const conversations = useConversations(chatbot.id);
  const known = conversations.data?.some((conversation) => conversation.id === conversationId);
  const current = known ? conversationId : undefined; // a deleted or foreign id: a new conversation
  const messages = useMessages(current);
  const routes = useRoutes(chatbot.id);
  const pipelines = usePipelines(chatbot.project_name);
  const send = useSendMessage(chatbot.id);
  const [text, setText] = useState("");
  const [pending, setPending] = useState<string>();
  const bottom = useRef<HTMLDivElement>(null);

  const list = current === undefined ? [] : (messages.data ?? []);
  const automations = (pipelines.data ?? []).filter((pipeline) => pipeline.active && pipeline.steps.length);
  const routeByMessage = new Map((routes.data ?? []).flatMap((route) => (route.message_id === null ? [] : [[route.message_id, route]])));

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "end" }); // braces: browsers may return a promise, not a cleanup
  }, [list.length, pending]);

  const submit = () => {
    const message = text.trim();
    if (!message || send.isPending) return;
    setPending(message);
    setText("");
    send.mutate(
      { conversationId: current, text: message },
      {
        onSuccess: (id) => id !== current && open(id),
        onError: () => setText(message), // to try again
        onSettled: () => setPending(undefined),
      },
    );
  };

  return (
    <Stack gap="sm">
      <Card withBorder p={0}>
        <ScrollArea h={520} p="md">
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
                route={routeByMessage.get(message.id)}
                automations={automations}
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
          style={{ flex: 1 }}
          autosize
          minRows={1}
          maxRows={8}
          placeholder={`Scrivi a ${chatbot.name}… (Invio per mandare, Maiusc+Invio per andare a capo; inizia con ! per saltare la cache)`}
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
