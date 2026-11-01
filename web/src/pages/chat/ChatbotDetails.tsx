import { Alert, Badge, Button, Code, Group, Modal, Stack, Text } from "@mantine/core";
import { useEffect, useState } from "react";

import { useModelChoices } from "../../api/catalog";
import { CHATBOT_KINDS, type Chatbot, useSetChatbotModel } from "../../api/chat";
import { ModelSelect } from "../../components/ModelSelect";

/** A chatbot and its agent. Only the model changes here; the rest is read-only:
 * the default chatbots come from the code, the others from Impostazioni →
 * Definizioni da file (they also change them). */
export function ChatbotDetails({ chatbot, opened, onClose }: { chatbot: Chatbot; opened: boolean; onClose: () => void }) {
  const kind = CHATBOT_KINDS[chatbot.kind];
  return (
    <Modal opened={opened} onClose={onClose} title={`Chatbot «${chatbot.name}»`} size="lg">
      <Stack gap="sm">
        <Group gap="xs">
          <Badge variant="light" color={KIND_COLORS[chatbot.kind]}>{kind.label}</Badge>
          <Text size="xs" c="dimmed">{kind.description}</Text>
        </Group>
        {chatbot.description && <Text size="sm">{chatbot.description}</Text>}
        <ChatbotModel chatbot={chatbot} />
        <Text size="sm">Max steps {chatbot.max_steps} · prompt v{chatbot.prompt_version}</Text>
        <Text size="sm">Tool: <code>{chatbot.tool_names.join(", ") || "nessuno"}</code></Text>
        <div>
          <Text size="sm" fw={500} mb={4}>System prompt</Text>
          <Code block>{chatbot.system_prompt}</Code>
        </div>
        <Text size="xs" c="dimmed">
          Il resto è in sola lettura. Per cambiarlo, o aggiungere altri chatbot, scrivilo in <code>chat-bots.yml</code> /{" "}
          <code>global-chat-bots.yml</code> con lo stesso nome e sincronizzalo da Impostazioni → Definizioni da file.
        </Text>
      </Stack>
    </Modal>
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

export const KIND_COLORS: Record<Chatbot["kind"], string> = { automation: "grape", secretary: "teal", custom: "gray" };
