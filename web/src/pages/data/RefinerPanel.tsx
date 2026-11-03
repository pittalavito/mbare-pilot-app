import { Alert, Button, Group, Loader, Select, Stack, Text } from "@mantine/core";
import { useState } from "react";

import { type Chatbot, useChatbots, useConversations } from "../../api/chat";
import { type Reference, useReferences } from "../../api/projectData";
import { ChatbotDetails } from "../chat/ChatbotDetails";
import { ConversationView } from "../chat/ChatTab";
import { ReferenceModal } from "./ReferencesSection";

/** The project's refiner chatbot next to its agent tasks (the first one by
 * name, when there are more). A link to a reference in its answers (``…/data?note=
 * code-reference-…``) opens the reference here, to read and edit it.
 * «ℹ️ Dettagli» shows it and changes its model, as in the Chat tab. */
export function RefinerPanel({ project, openTask, draft }: { project: string; openTask?: Named; draft?: { text: string; id: number } }) {
  const chatbots = useChatbots(project);
  if (chatbots.isPending) return <Loader size="sm" />;
  if (chatbots.error) return <Alert color="red">{chatbots.error.message}</Alert>;
  const refiner = chatbots.data.find((bot) => bot.kind === "refiner");
  if (!refiner) {
    return <Text size="sm" c="dimmed">Nessun Refiner nel progetto: il chatbot di default si crea all'avvio dell'API (se manca, guarda il log).</Text>;
  }
  return <Refiner key={refiner.id} project={project} chatbot={refiner} openTask={openTask} draft={draft} />;
}

/** The note named by an app link to the Dati tab (``?note=``), or null. */
export function noteOfLink(href: string): string | null {
  const url = new URL(href, window.location.origin);
  return url.origin === window.location.origin && url.pathname.endsWith("/data") ? url.searchParams.get("note") : null;
}

/** A note by name and title (the agent task open next to the chat). */
type Named = { name: string; title: string };

function Refiner({ project, chatbot, openTask, draft }: { project: string; chatbot: Chatbot; openTask?: Named; draft?: { text: string; id: number } }) {
  const conversations = useConversations(chatbot.id);
  const references = useReferences(project);
  const [conversation, setConversation] = useState<number>();
  const [opened, setOpened] = useState<string>();
  const [details, setDetails] = useState(false);
  const reference: Reference | undefined = references.data?.find((item) => item.name === opened);

  return (
    <Stack gap="xs">
      <Group justify="space-between" wrap="nowrap">
        <Text fw={600}>🧠 {chatbot.name}</Text>
        <Group gap={4} wrap="nowrap">
          <Button size="compact-xs" variant="default" onClick={() => setDetails(true)}>ℹ️ Dettagli</Button>
          <Button size="compact-xs" variant="light" onClick={() => setConversation(undefined)}>💬 Nuova</Button>
        </Group>
      </Group>
      <Text size="xs" c="dimmed">Modello <code>{chatbot.model}</code></Text>
      <Text size="xs">
        {openTask ? <>Task aperto: <b>{openTask.title}</b> — per il Refiner è «questo task».</> : "Nessun task aperto."}
      </Text>
      {chatbot.description && <Text size="xs" c="dimmed">{chatbot.description}</Text>}
      {!!conversations.data?.length && (
        <Select
          size="xs"
          aria-label="Conversazione"
          placeholder="Conversazioni precedenti"
          data={conversations.data.map((item) => ({ value: String(item.id), label: item.title || "Nuova conversazione" }))}
          value={conversation === undefined ? null : String(conversation)}
          onChange={(value) => setConversation(value === null ? undefined : Number(value))}
        />
      )}
      <ConversationView
        chatbot={chatbot}
        conversationId={conversation}
        onOpen={setConversation}
        height={380}
        openNote={openTask?.name}
        draft={draft}
        onLinkClick={(event, href) => {
          const note = noteOfLink(href);
          if (!note?.match(/^(code|context)-reference-/)) return;
          event.preventDefault();
          setOpened(note);
        }}
      />
      {opened && references.data && !reference && (
        <Alert color="orange" withCloseButton onClose={() => setOpened(undefined)}>Il riferimento {opened} non c'è più.</Alert>
      )}
      <ReferenceModal
        project={project}
        reference={reference}
        opened={!!reference}
        onClose={() => setOpened(undefined)}
        onCreated={() => {}}
        onDeleted={() => setOpened(undefined)}
      />
      <ChatbotDetails chatbot={chatbot} opened={details} onClose={() => setDetails(false)} />
    </Stack>
  );
}
