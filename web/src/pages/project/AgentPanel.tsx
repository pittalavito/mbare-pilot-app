import { Alert, Button, Group, Loader, Select, Stack, Text } from "@mantine/core";
import { type ReactNode, createContext, useContext, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { type Chatbot, useChatbots, useConversations } from "../../api/chat";
import { useCopilotSessions } from "../../api/copilot";
import { NOTE_PREFIXES, type Reference, useAgentTasks, useReferences } from "../../api/projectData";
import { ChatbotDetails } from "../chat/ChatbotDetails";
import { ConversationView } from "../chat/ConversationView";
import { SessionView } from "../copilot/SessionView";
import { ReferenceModal } from "../data/ReferencesSection";
import { isPlanOnly } from "../data/TypedNotes";

/** The agent panel (plan 13b): one chat at the right of the zones «Lavoro» and
 * «Automation», with the agent of what is open:
 *
 * | open                                         | agent        | its conversations are about |
 * |----------------------------------------------|--------------|-----------------------------|
 * | an activity                                  | Segretario   | that activity               |
 * | an agent task delegated to Copilot           | Copilot      | (its latest session)        |
 * | any other agent task                         | Refiner      | that task                   |
 * | nothing, the WIP note, «Tutti i task»        | Segretario   | the project                 |
 * | the zone Automation                          | Architetto   | the project                 |
 *
 * Its menu changes agent by hand (also to a chatbot of the project's own): the
 * choice lasts until what is open changes. A page asks the panel's agent to do
 * something (e.g. «Rifinisci con il Refiner») with ``useAgentPanel().ask``. */

export type Zone = "work" | "automation";

/** The note named by an app link to a note (``?note=``: the zones, or the Dati tab of before), or null. */
export function noteOfLink(href: string): string | null {
  const url = new URL(href, window.location.origin);
  const zone = ["/data", "/work", "/project"].some((suffix) => url.pathname.endsWith(suffix));
  return url.origin === window.location.origin && zone ? url.searchParams.get("note") : null;
}
type Draft = { text: string; id: number };
type PanelState = { draft?: Draft; ask: (text: string) => void };

const PanelContext = createContext<PanelState>({ ask: () => {} });

/** ``ask(text)`` puts ``text`` in the panel's box (not sent), for the agent of what is open. */
export const useAgentPanel = () => useContext(PanelContext);

export function AgentPanelProvider({ children }: { children: ReactNode }) {
  const [draft, setDraft] = useState<Draft>();
  const ask = (text: string) => setDraft((current) => ({ text, id: (current?.id ?? 0) + 1 }));
  return <PanelContext.Provider value={{ draft, ask }}>{children}</PanelContext.Provider>;
}

const COPILOT = "copilot";
type Choice = { key: string; label: string; chatbot?: Chatbot; context: string; why: string };

/** The agent of what is open, the context of its conversations and why it is the one. */
function useChoices(project: string, zone: Zone): { choices: Choice[]; preferred: string; openNote: string } | undefined {
  const [search] = useSearchParams();
  const chatbots = useChatbots(project);
  const tasks = useAgentTasks(project);
  const sessions = useCopilotSessions(project);
  if (!chatbots.data) return undefined;
  const note = zone === "work" ? search.get("note") ?? "" : "";
  const byKind = (kind: Chatbot["kind"]) => chatbots.data.find((bot) => bot.kind === kind);
  const task = note.startsWith(NOTE_PREFIXES.agent_task) ? tasks.data?.find((item) => item.name === note) : undefined;
  const delegated = !!task && !!sessions.data?.some((session) => session.task_note === task.name);
  const activity = note.startsWith(NOTE_PREFIXES.activity) ? note : "";

  let preferred: string;
  let context = "";
  let why: string;
  if (zone === "automation") {
    preferred = String(byKind("automation")?.id ?? "");
    why = "Sei nelle automation";
  } else if (task && delegated) {
    preferred = COPILOT;
    why = "Il task è delegato a Copilot";
  } else if (task) {
    preferred = String(byKind("refiner")?.id ?? "");
    context = task.name;
    why = "Hai aperto un task";
  } else {
    preferred = String(byKind("secretary")?.id ?? "");
    context = activity;
    why = activity ? "Hai aperto un'attività" : "Il progetto";
  }
  const choices: Choice[] = chatbots.data.map((bot) => ({
    key: String(bot.id), label: bot.kind === "custom" ? `${bot.name} (personalizzato)` : bot.name, chatbot: bot,
    context: bot.kind === "refiner" ? task?.name ?? "" : bot.kind === "secretary" ? activity : context, why,
  }));
  if (delegated) choices.unshift({ key: COPILOT, label: "Copilot", context: "", why });
  return { choices, preferred, openNote: note };
}

export function AgentPanel({ project, zone }: { project: string; zone: Zone }) {
  const resolved = useChoices(project, zone);
  const [search] = useSearchParams();
  const [manual, setManual] = useState<string>();
  const where = `${zone}:${search.get("note") ?? ""}`;
  useEffect(() => setManual(undefined), [where]); // a hand-picked agent lasts until what is open changes

  if (!resolved) return <Loader size="sm" />;
  const { choices, preferred, openNote } = resolved;
  const current = choices.find((choice) => choice.key === (manual ?? preferred)) ?? choices[0];
  if (!current) return <Text size="sm" c="dimmed">Nessun agente nel progetto: i chatbot di default si creano all'avvio dell'API.</Text>;
  return (
    <Stack gap="xs" data-testid="agent-panel">
      <Select
        aria-label="Agente"
        allowDeselect={false}
        data={choices.map((choice) => ({ value: choice.key, label: choice.label }))}
        value={current.key}
        onChange={(value) => value && setManual(value)}
        styles={{ input: { fontWeight: 600 } }}
      />
      <Text size="xs" c="dimmed">{manual ? "Scelto a mano: torna da solo quando apri altro" : current.why}</Text>
      {current.key === COPILOT ? (
        <CopilotChat project={project} task={openNote} />
      ) : current.chatbot && (
        <AgentChat key={`${current.chatbot.id}:${current.context}`} project={project} chatbot={current.chatbot} context={current.context} openNote={openNote} />
      )}
    </Stack>
  );
}

/** A chatbot's chat in the panel: the latest conversation about the context (or a new one), the others in a menu. */
function AgentChat({ project, chatbot, context, openNote }: { project: string; chatbot: Chatbot; context: string; openNote: string }) {
  const { draft } = useAgentPanel();
  const conversations = useConversations(chatbot.id, context);
  const references = useReferences(project);
  const [conversation, setConversation] = useState<number | null>(); // undefined: the latest; null: a new one
  const [details, setDetails] = useState(false);
  const [opened, setOpened] = useState<string>();
  const reference: Reference | undefined = references.data?.find((item) => item.name === opened);
  const shown = conversation === undefined ? conversations.data?.[0]?.id : conversation ?? undefined;
  return (
    <Stack gap="xs">
      <Group gap={4} wrap="nowrap">
        <Button size="compact-xs" variant="light" onClick={() => setConversation(null)}>💬 Nuova</Button>
        <Button size="compact-xs" variant="default" onClick={() => setDetails(true)}>ℹ️ Dettagli</Button>
        {(conversations.data?.length ?? 0) > 1 && (
          <Select
            size="xs" aria-label="Conversazione" style={{ flex: 1, minWidth: 0 }}
            data={conversations.data!.map((item) => ({ value: String(item.id), label: item.title || "Nuova conversazione" }))}
            value={shown === undefined ? null : String(shown)}
            onChange={(value) => setConversation(value === null ? null : Number(value))}
          />
        )}
      </Group>
      <ConversationView
        chatbot={chatbot}
        conversationId={shown}
        onOpen={(id) => setConversation(id ?? null)}
        height={420}
        openNote={openNote || undefined}
        context={context}
        draft={draft}
        onLinkClick={(event, href) => { // a reference in an answer opens here, to read and edit it
          const note = noteOfLink(href);
          if (!note?.match(/^(code|context)-reference-/)) return;
          event.preventDefault();
          setOpened(note);
        }}
      />
      {opened && references.data && !reference && (
        <Alert color="orange" withCloseButton onClose={() => setOpened(undefined)}>Il riferimento {opened} non c'è più.</Alert>
      )}
      <ReferenceModal project={project} reference={reference} opened={!!reference} onClose={() => setOpened(undefined)} onCreated={() => {}}
        onDeleted={() => setOpened(undefined)} />
      <ChatbotDetails chatbot={chatbot} opened={details} onClose={() => setDetails(false)} />
    </Stack>
  );
}

/** The chat with Copilot of a delegated task: its latest session, the others in a menu. */
function CopilotChat({ project, task }: { project: string; task: string }) {
  const sessions = useCopilotSessions(project);
  const tasks = useAgentTasks(project);
  const [chosen, setChosen] = useState<number>();
  const mine = (sessions.data ?? []).filter((session) => session.task_note === task); // newest first
  const session = mine.find((item) => item.id === chosen) ?? mine[0];
  if (!session) return <Loader size="sm" />;
  return (
    <Stack gap="xs">
      {mine.length > 1 && (
        <Select
          size="xs" aria-label="Sessione Copilot" allowDeselect={false}
          data={mine.map((item) => ({ value: String(item.id), label: `Sessione ${item.id} · ${item.repository || "progetto"} · ${item.status}` }))}
          value={String(session.id)} onChange={(value) => value && setChosen(Number(value))}
        />
      )}
      <SessionView key={session.id} project={project} session={session} onDeleted={() => setChosen(undefined)}
        planOnly={isPlanOnly(tasks.data?.find((item) => item.name === task)?.type)} />
    </Stack>
  );
}
