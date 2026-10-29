import { Badge, Code, Group, Modal, Stack, Text } from "@mantine/core";

import { CHATBOT_KINDS, type Chatbot } from "../../api/chat";

/** A chatbot and its agent, read-only: the default chatbots come from the code,
 * the others from Impostazioni → Definizioni da file (they also change them). */
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
        <Text size="sm">
          Modello <code>{chatbot.model}</code> · max steps {chatbot.max_steps} · prompt v{chatbot.prompt_version}
        </Text>
        <Text size="sm">Tool: <code>{chatbot.tool_names.join(", ") || "nessuno"}</code></Text>
        <div>
          <Text size="sm" fw={500} mb={4}>System prompt</Text>
          <Code block>{chatbot.system_prompt}</Code>
        </div>
        <Text size="xs" c="dimmed">
          Sola lettura. Per cambiarlo, o aggiungere altri chatbot, scrivilo in <code>chat-bots.yml</code> / <code>global-chat-bots.yml</code> con
          lo stesso nome e sincronizzalo da Impostazioni → Definizioni da file.
        </Text>
      </Stack>
    </Modal>
  );
}

export const KIND_COLORS: Record<Chatbot["kind"], string> = { automation: "grape", secretary: "teal", custom: "gray" };
