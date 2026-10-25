import { ActionIcon, Alert, Avatar, Button, Group, Paper, Popover, Select, Stack, Text, TextInput, TypographyStylesProvider } from "@mantine/core";
import { useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import type { Pipeline } from "../../api/automation";
import { CACHE_MARK, type ChatRoute, type Message, useAddRoute, useDeleteRoute } from "../../api/chat";

type Props = {
  chatbotId: number;
  message: Message;
  /** The message after this one: for a user message, the reply (it proposes the automation to cache). */
  reply?: Message;
  route?: ChatRoute;
  automations: Pipeline[];
};

/** A message of the conversation: the user's on the right with its cache
 * controls, the chatbot's on the left (⚡ when it came from the cache). */
export function MessageItem({ chatbotId, message, reply, route, automations }: Props) {
  if (message.role === "user") {
    return (
      <Stack gap={4} align="flex-end">
        <Paper bg="var(--mantine-primary-color-light)" px="md" py="xs" radius="md" maw="85%">
          <Text size="sm" style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{message.content}</Text>
        </Paper>
        {message.id > 0 && <CacheControls chatbotId={chatbotId} message={message} reply={reply} route={route} automations={automations} />}
      </Stack>
    );
  }
  if (message.role === "error") {
    return (
      <Alert color="red" icon="⚠️" maw="85%">
        <Text size="sm" style={{ whiteSpace: "pre-wrap" }}>{message.content}</Text>
      </Alert>
    );
  }
  return (
    <Group align="flex-start" wrap="nowrap" gap="sm" maw="85%">
      <Avatar size="sm" radius="xl" color={message.content.startsWith(CACHE_MARK) ? "yellow" : "indigo"}>
        {message.content.startsWith(CACHE_MARK) ? "⚡" : "🤖"}
      </Avatar>
      <TypographyStylesProvider p={0} style={{ fontSize: "var(--mantine-font-size-sm)", minWidth: 0 }}>
        <Markdown remarkPlugins={[remarkGfm]}>{message.content}</Markdown>
      </TypographyStylesProvider>
    </Group>
  );
}

/** Under a user message: what it launches when in cache, else «Metti in cache». */
function CacheControls({ chatbotId, message, reply, route, automations }: Omit<Props, "route"> & { route?: ChatRoute }) {
  const remove = useDeleteRoute(chatbotId);
  if (route) {
    const name = automations.find((item) => item.id === route.pipeline_id)?.name ?? `automation ${route.pipeline_id}`;
    return (
      <Group gap={4}>
        <Text size="xs" c="dimmed">
          ⚡ In cache → <b>{name}</b>
          {route.pipeline_input ? ` · input «${route.pipeline_input}»` : ""} · usata {route.hits} volte
        </Text>
        <ActionIcon size="xs" variant="subtle" color="red" title="Togli dalla cache" loading={remove.isPending} onClick={() => remove.mutate(route.id)}>
          🗑
        </ActionIcon>
        {remove.error && <Text size="xs" c="red">{remove.error.message}</Text>}
      </Group>
    );
  }
  if (!automations.length) return null;
  return <AddRoute chatbotId={chatbotId} message={message} reply={reply} automations={automations} />;
}

function AddRoute({ chatbotId, message, reply, automations }: { chatbotId: number; message: Message; reply?: Message; automations: Pipeline[] }) {
  // Proposed: the automation the reply names (e.g. the one the agent launched).
  const mentioned = automations.find((item) => reply?.content.includes(item.name)) ?? automations[0];
  const [opened, setOpened] = useState(false);
  const [pipelineId, setPipelineId] = useState(String(mentioned.id));
  const [input, setInput] = useState("");
  const add = useAddRoute(chatbotId);
  return (
    <Popover opened={opened} onChange={setOpened} withArrow position="bottom-end">
      <Popover.Target>
        <Button size="compact-xs" variant="subtle" onClick={() => setOpened((value) => !value)}>⚡ Metti in cache</Button>
      </Popover.Target>
      <Popover.Dropdown>
        <Stack gap="xs" w={300}>
          <Text size="xs" c="dimmed">I messaggi simili lanceranno questa automation direttamente, senza l'agente.</Text>
          <Select
            label="Automation"
            allowDeselect={false}
            data={automations.map((item) => ({ value: String(item.id), label: item.name }))}
            value={pipelineId}
            onChange={(value) => value && setPipelineId(value)}
            comboboxProps={{ withinPortal: false }}
          />
          <TextInput
            label="Input fisso"
            description="Lo stesso per ogni messaggio simile (vuoto = nessuno)."
            value={input}
            onChange={(event) => setInput(event.currentTarget.value)}
          />
          {add.error && <Text size="xs" c="red">{add.error.message}</Text>}
          <Button
            size="xs"
            loading={add.isPending}
            onClick={() => add.mutate({ messageId: message.id, pipelineId: Number(pipelineId), input }, { onSuccess: () => setOpened(false) })}
          >
            Salva
          </Button>
        </Stack>
      </Popover.Dropdown>
    </Popover>
  );
}
