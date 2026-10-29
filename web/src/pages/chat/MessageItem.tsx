import { ActionIcon, Alert, Avatar, Button, Group, Paper, Popover, Select, Stack, Text, TextInput } from "@mantine/core";
import { useState } from "react";

import type { Pipeline } from "../../api/automation";
import { CACHE_MARK, type AutomationCacheEntry, type Message, useAddToAutomationCache, useRemoveFromAutomationCache } from "../../api/chat";
import { Markdown } from "../../components/Markdown";

type Props = {
  chatbotId: number;
  message: Message;
  /** The message after this one: for a user message, the reply (it proposes the automation to cache). */
  reply?: Message;
  entry?: AutomationCacheEntry;
  automations: Pipeline[];
};

/** A message of the conversation: the user's on the right with its cache
 * controls, the chatbot's on the left (⚡ when it came from the cache). */
export function MessageItem({ chatbotId, message, reply, entry, automations }: Props) {
  if (message.role === "user") {
    return (
      <Stack gap={4} align="flex-end">
        <Paper bg="var(--mantine-primary-color-light)" px="md" py="xs" radius="md" maw="85%">
          <Text size="sm" style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{message.content}</Text>
        </Paper>
        {message.id > 0 && <CacheControls chatbotId={chatbotId} message={message} reply={reply} entry={entry} automations={automations} />}
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
      <Markdown>{message.content}</Markdown>
    </Group>
  );
}

/** Under a user message: what it launches when in cache, else «Metti in cache». */
function CacheControls({ chatbotId, message, reply, entry, automations }: Omit<Props, "entry"> & { entry?: AutomationCacheEntry }) {
  const remove = useRemoveFromAutomationCache(chatbotId);
  if (entry) {
    const name = automations.find((item) => item.id === entry.pipeline_id)?.name ?? `automation ${entry.pipeline_id}`;
    return (
      <Group gap={4}>
        <Text size="xs" c="dimmed">
          ⚡ In cache → <b>{name}</b>
          {entry.pipeline_input ? ` · input «${entry.pipeline_input}»` : ""} · usata {entry.hits} volte
        </Text>
        <ActionIcon size="xs" variant="subtle" color="red" title="Togli dalla cache" loading={remove.isPending} onClick={() => remove.mutate(entry.id)}>
          🗑
        </ActionIcon>
        {remove.error && <Text size="xs" c="red">{remove.error.message}</Text>}
      </Group>
    );
  }
  if (!automations.length) return null;
  return <AddToAutomationCache chatbotId={chatbotId} message={message} reply={reply} automations={automations} />;
}

function AddToAutomationCache({ chatbotId, message, reply, automations }: { chatbotId: number; message: Message; reply?: Message; automations: Pipeline[] }) {
  // Proposed: the automation the reply names (e.g. the one the agent launched).
  const mentioned = automations.find((item) => reply?.content.includes(item.name)) ?? automations[0];
  const [opened, setOpened] = useState(false);
  const [pipelineId, setPipelineId] = useState(String(mentioned.id));
  const [input, setInput] = useState("");
  const add = useAddToAutomationCache(chatbotId);
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
