import { Accordion, Alert, Badge, Button, Code, CopyButton, Group, Loader, Modal, SegmentedControl, Stack, Text } from "@mantine/core";
import { Fragment, type ReactNode, useState } from "react";

import { type RunTranscript, useRunTranscript } from "../api/admin";
import { Markdown } from "./Markdown";

type View = RunTranscript["masked"];

/** «🔍 Cosa ha visto il modello»: what went to and came from the model in one run
 * (system prompt, input and history, tool calls, answer), masked as it left or in clear;
 * one accordion section per part, the aliases highlighted in the masked view, «Copia» on each block. */
export function TranscriptModal({ runId, opened, onClose }: { runId: string; opened: boolean; onClose: () => void }) {
  const transcript = useRunTranscript(opened ? runId : undefined);
  const [mode, setMode] = useState<"masked" | "clear">("masked");
  const data = transcript.data;
  const raw: View | undefined = data ? data[mode] : undefined;
  const view = raw ? { ...raw, history: raw.history ?? [], tool_calls: raw.tool_calls ?? [], system_prompt: raw.system_prompt ?? "",
    input: raw.input ?? "", output: raw.output ?? "" } : undefined;
  const aliases = mode === "masked" ? data?.aliases ?? [] : [];
  return (
    <Modal opened={opened} onClose={onClose} size="xl" title="🔍 Cosa ha visto il modello">
      <Stack gap="sm">
        <Group justify="space-between">
          <SegmentedControl value={mode} onChange={(value) => setMode(value as "masked" | "clear")}
            data={[{ value: "masked", label: "🎭 Mascherato" }, { value: "clear", label: "👁 In chiaro" }]} />
          <Text size="xs" c="dimmed">
            {mode === "masked" ? "Quello che è uscito verso il modello: gli alias sono evidenziati." : "Gli alias rimessi in chiaro con la mappa del progetto."}
          </Text>
        </Group>
        {transcript.isPending && <Loader size="sm" />}
        {transcript.error && <Alert color="orange">{transcript.error.message}</Alert>}
        {view && (
          <Accordion multiple defaultValue={["input", "output"]} variant="separated">
            <Section value="system" title="System prompt" copy={view.system_prompt}>
              <Body aliases={aliases} text={view.system_prompt} />
            </Section>
            <Section value="input" title={`Input${view.history.length ? ` e storia (${view.history.length} messaggi prima)` : ""}`} copy={view.input}>
              <Stack gap="xs">
                {view.history.map((message, index) => (
                  <div key={index}>
                    <Badge size="xs" variant="light" color={message.role === "user" ? "blue" : "gray"}>{message.role === "user" ? "utente" : "assistente"}</Badge>
                    <Body aliases={aliases} text={message.content} />
                  </div>
                ))}
                <div>
                  {!!view.history.length && <Badge size="xs" variant="filled">messaggio</Badge>}
                  <Body aliases={aliases} text={view.input} />
                </div>
              </Stack>
            </Section>
            <Section value="tools" title={`Chiamate ai tool (${view.tool_calls.length})`}>
              {!view.tool_calls.length && <Text size="sm" c="dimmed">Nessun tool chiamato.</Text>}
              <Stack gap="sm">
                {view.tool_calls.map((tool, index) => (
                  <Stack key={index} gap={4}>
                    <Group gap="xs"><Badge size="sm" variant="light">{index + 1}. {tool.name}</Badge>{tool.error && <Badge size="sm" color="red">errore</Badge>}</Group>
                    <Block label="Argomenti" text={tool.arguments} aliases={aliases} />
                    <Block label={tool.error ? "Errore" : "Risultato"} text={tool.error ?? tool.result} aliases={aliases} />
                  </Stack>
                ))}
              </Stack>
            </Section>
            <Section value="output" title="Risposta" copy={view.output}>
              <Body aliases={aliases} text={view.output} />
            </Section>
          </Accordion>
        )}
      </Stack>
    </Modal>
  );
}

function Section({ value, title, copy, children }: { value: string; title: string; copy?: string; children: ReactNode }) {
  return (
    <Accordion.Item value={value}>
      <Accordion.Control>{title}</Accordion.Control>
      <Accordion.Panel>
        <Stack gap="xs">
          {copy !== undefined && <Group justify="flex-end"><Copy text={copy} /></Group>}
          {children}
        </Stack>
      </Accordion.Panel>
    </Accordion.Item>
  );
}

function Copy({ text }: { text: string }) {
  return (
    <CopyButton value={text}>
      {({ copied, copy }) => <Button size="compact-xs" variant="subtle" onClick={copy}>{copied ? "Copiato" : "Copia"}</Button>}
    </CopyButton>
  );
}

/** Markdown; in the masked view each alias becomes inline code, so it stands out. */
function Body({ text, aliases }: { text: string; aliases: string[] }) {
  if (!text.trim()) return <Text size="sm" c="dimmed">(vuoto)</Text>;
  const marked = aliases.length ? text.replace(aliasPattern(aliases), (alias) => `\`${alias}\``) : text;
  return <Markdown>{marked}</Markdown>;
}

/** A tool's arguments or result: monospace (JSON already indented), aliases highlighted. */
function Block({ label, text, aliases }: { label: string; text: string; aliases: string[] }) {
  const parts = aliases.length ? text.split(aliasPattern(aliases, true)) : [text];
  return (
    <div>
      <Group justify="space-between"><Text size="xs" c="dimmed">{label}</Text><Copy text={text} /></Group>
      <Code block style={{ maxHeight: 280, overflow: "auto", whiteSpace: "pre-wrap" }}>
        {parts.map((part, index) => (aliases.includes(part) ? <mark key={index}>{part}</mark> : <Fragment key={index}>{part}</Fragment>))}
      </Code>
    </div>
  );
}

function aliasPattern(aliases: string[], capture = false): RegExp {
  const body = [...aliases].sort((a, b) => b.length - a.length).map((alias) => alias.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|");
  return new RegExp(capture ? `\\b(${body})\\b` : `\\b(?:${body})\\b`, "g");
}

