import { Alert, Badge, Box, Button, Card, Grid, Group, Loader, NavLink, ScrollArea, Stack, Text, Textarea } from "@mantine/core";
import { useEffect, useRef, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";

import { CHATBOT_KINDS, type Chatbot, useAutomationCache, useChatbots, useConversations, useDeleteConversation, useMessages, useSendMessage } from "../../api/chat";
import { usePipelines } from "../../api/automation";
import { ConfirmButton } from "../../components/ConfirmButton";
import { ChatbotDetails, KIND_COLORS } from "./ChatbotDetails";
import { MessageItem } from "./MessageItem";

/** The Chat tab of a project: its chatbots (each with its own agent) on the
 * left, ``?bot=`` the open one with its conversations, ``?c=`` the open
 * conversation on the right. The chatbots are not created nor edited here:
 * every project has the default ones (from the code), the others come from
 * Impostazioni → Definizioni da file. A reply arrives whole (no streaming yet). An
 * automation chatbot has the automation cache: «Metti in cache» on a message,
 * and a message starting with ``!`` skips it. */
export function ChatTab() {
  const { project = "" } = useParams();
  const chatbots = useChatbots(project);
  const [botId, , openBot] = useChatParams();
  const [details, setDetails] = useState(false);

  if (chatbots.isPending) return <Loader size="sm" />;
  if (chatbots.error) return <Alert color="red">{chatbots.error.message}</Alert>;
  const chatbot = chatbots.data.find((bot) => bot.id === botId) ?? chatbots.data[0]; // unknown or none: the first by name
  if (!chatbot) {
    return (
      <Text c="dimmed">
        Nessun chatbot: i chatbot di default si creano all'avvio dell'API (se mancano, guarda il log: ad esempio il modello non è nel
        catalogo); gli altri da Impostazioni → Definizioni da file.
      </Text>
    );
  }
  return (
    <Grid gutter="md">
      <Grid.Col span={{ base: 12, md: 3 }}>
        <Stack gap="md">
          <ChatbotList chatbots={chatbots.data} selected={chatbot} onSelect={(bot) => openBot(bot.id)} />
          <Sidebar key={chatbot.id} chatbot={chatbot} onDetails={() => setDetails(true)} />
        </Stack>
      </Grid.Col>
      <Grid.Col span={{ base: 12, md: 9 }}>
        <ConversationView key={chatbot.id} chatbot={chatbot} />
      </Grid.Col>
      <ChatbotDetails chatbot={chatbot} opened={details} onClose={() => setDetails(false)} />
    </Grid>
  );
}

/** ``?bot=`` is the open chatbot, ``?c=`` its open conversation (none = a new
 * one, created on the first message). Opening a chatbot starts from a new conversation. */
function useChatParams(): [number | undefined, number | undefined, (bot: number) => void, (conversation: number | undefined) => void] {
  const [search, setSearch] = useSearchParams();
  const number = (key: string) => (search.get(key) ? Number(search.get(key)) : undefined);
  const bot = number("bot");
  const openBot = (id: number) => setSearch({ bot: String(id) }, { replace: true });
  const openConversation = (id: number | undefined) =>
    setSearch({ ...(bot === undefined ? {} : { bot: String(bot) }), ...(id === undefined ? {} : { c: String(id) }) }, { replace: true });
  return [bot, number("c"), openBot, openConversation];
}

function useOpenConversation(): [number | undefined, (id: number | undefined) => void] {
  const [, conversation, , open] = useChatParams();
  return [conversation, open];
}

/** The project's chatbots: one click opens it. */
function ChatbotList({ chatbots, selected, onSelect }: { chatbots: Chatbot[]; selected: Chatbot; onSelect: (bot: Chatbot) => void }) {
  return (
    <Stack gap={4}>
      <Text size="xs" fw={600} c="dimmed" tt="uppercase">Chatbot</Text>
      {chatbots.map((bot) => (
        <NavLink
          key={bot.id}
          label={bot.name}
          description={bot.description || undefined}
          rightSection={<Badge size="xs" variant="light" color={KIND_COLORS[bot.kind]}>{CHATBOT_KINDS[bot.kind].label}</Badge>}
          active={bot.id === selected.id}
          onClick={() => onSelect(bot)}
        />
      ))}
    </Stack>
  );
}

function Sidebar({ chatbot, onDetails }: { chatbot: Chatbot; onDetails: () => void }) {
  const conversations = useConversations(chatbot.id);
  const [openId, open] = useOpenConversation();
  return (
    <Stack gap="xs">
      <Group justify="space-between" wrap="nowrap">
        <Text fw={600}>{chatbot.name}</Text>
        <Button size="xs" variant="default" onClick={onDetails}>ℹ️ Dettagli</Button>
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
  const cache = useAutomationCache(chatbot.id);
  const pipelines = usePipelines(chatbot.project_name);
  const send = useSendMessage(chatbot.id);
  const [text, setText] = useState("");
  const [pending, setPending] = useState<string>();
  const bottom = useRef<HTMLDivElement>(null);

  const list = current === undefined ? [] : (messages.data ?? []);
  const hasCache = chatbot.kind === "automation"; // only an automation chatbot has the automation cache
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
                entry={cacheByMessage.get(message.id)}
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
