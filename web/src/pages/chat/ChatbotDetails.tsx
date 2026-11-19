import { Alert, Badge, Button, Group, Modal, Stack, Text, Textarea } from "@mantine/core";
import { useEffect, useState } from "react";

import { useModelChoices } from "../../api/catalog";
import { CHATBOT_KINDS, type Chatbot, ORIGINS, useRevertChatbot, useSaveChatbotPrompt, useSetChatbotModel } from "../../api/chat";
import { ModelSelect } from "../../components/ModelSelect";

/** A chatbot and its agent: model and system prompt change here. A chatbot of
 * the definition files saved here is written back to the data folder (plan 28:
 * «tuo», it wins over the app's default after a restart); «↩ Torna al default»
 * brings the app's back. */
export function ChatbotDetails({ chatbot, opened, onClose }: { chatbot: Chatbot; opened: boolean; onClose: () => void }) {
  const kind = CHATBOT_KINDS[chatbot.kind];
  return (
    <Modal opened={opened} onClose={onClose} title={`Chatbot «${chatbot.name}»`} size="lg">
      <Stack gap="sm">
        <Group gap="xs">
          <Badge variant="light" color={KIND_COLORS[chatbot.kind]}>{kind.label}</Badge>
          <Text size="xs" c="dimmed">{kind.description}</Text>
          {chatbot.origin && (
            <Badge variant="outline" color={ORIGINS[chatbot.origin]?.color} title={ORIGINS[chatbot.origin]?.hint}>{ORIGINS[chatbot.origin]?.label ?? chatbot.origin}</Badge>
          )}
        </Group>
        {chatbot.description && <Text size="sm">{chatbot.description}</Text>}
        <ChatbotModel chatbot={chatbot} />
        <Text size="sm">Max steps {chatbot.max_steps} · prompt v{chatbot.prompt_version}</Text>
        <Text size="sm">Tool: <code>{chatbot.tool_names.join(", ") || "nessuno"}</code></Text>
        <ChatbotPrompt chatbot={chatbot} />
        <Text size="xs" c="dimmed">
          {chatbot.origin
            ? "Salvato qui, il chatbot va nella cartella dati (definition/) e resta anche dopo il riavvio. Tool e tipo si cambiano nei file."
            : "Creato dalla UI: non viene dai file delle definizioni."}
        </Text>
      </Stack>
    </Modal>
  );
}

/** The system prompt, saved on «Salva prompt»; «↩ Torna al default» when the user changed an app's default. */
function ChatbotPrompt({ chatbot }: { chatbot: Chatbot }) {
  const [prompt, setPrompt] = useState(chatbot.system_prompt);
  const save = useSaveChatbotPrompt(chatbot);
  const revert = useRevertChatbot(chatbot);
  useEffect(() => setPrompt(chatbot.system_prompt), [chatbot.id, chatbot.system_prompt]);
  return (
    <Stack gap={6}>
      <Textarea label="System prompt" autosize minRows={6} maxRows={18} value={prompt} onChange={(event) => setPrompt(event.currentTarget.value)} />
      <Group gap="xs">
        <Button size="xs" onClick={() => save.mutate(prompt)} disabled={prompt === chatbot.system_prompt || !prompt.trim()} loading={save.isPending}>
          Salva prompt
        </Button>
        {chatbot.origin === "tuo" && (
          <Button size="xs" variant="default" onClick={() => revert.mutate()} loading={revert.isPending}>↩ Torna al default</Button>
        )}
      </Group>
      {(save.error || revert.error) && <Alert color="red" p="xs">{(save.error ?? revert.error)?.message}</Alert>}
    </Stack>
  );
}

/** The chatbot's model, changed on «Salva» (only a known model whose provider has a key). */
function ChatbotModel({ chatbot }: { chatbot: Chatbot }) {
  const [model, setModel] = useState(chatbot.model);
  const save = useSetChatbotModel(chatbot);
  const usable = useModelChoices().data?.usable ?? [];
  useEffect(() => setModel(chatbot.model), [chatbot.id, chatbot.model]); // another chatbot, or saved
  const changed = model !== chatbot.model;
  return (
    <Stack gap={4}>
      <Group align="flex-end" gap="xs">
        <ModelSelect value={model} onChange={setModel} style={{ flex: 1 }} />
        <Button onClick={() => save.mutate(model)} disabled={!changed || !usable.includes(model)} loading={save.isPending}>
          Salva
        </Button>
      </Group>
      {save.error && <Alert color="red">{save.error.message}</Alert>}
      {save.isSuccess && !changed && <Text size="xs" c="teal">Modello salvato: vale dal prossimo messaggio.</Text>}
      <Text size="xs" c="dimmed">
        Se questo chatbot è in <code>chat-bots.yml</code> / <code>global-chat-bots.yml</code>, sincronizzarlo da file rimette il modello del file.
      </Text>
    </Stack>
  );
}

export const KIND_COLORS: Record<Chatbot["kind"], string> = { automation: "grape", secretary: "teal", refiner: "yellow", operator: "orange", custom: "gray" };
