import { Alert, Avatar, Badge, Box, Button, Card, Grid, Group, List, Loader, NavLink, Paper, ScrollArea, Stack, Text, Textarea } from "@mantine/core";
import { useEffect, useRef, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";

import {
  type CopilotMessage, type CopilotSession, isExecuting, useApproveCopilot, useCancelCopilot, useCopilotMessages, useCopilotSessionUsage,
  useCopilotSessions, useCopilotStatus, useDeleteCopilotSession, useSendCopilotMessage,
} from "../../api/copilot";
import { useWorkerState } from "../../api/worker";
import { ConfirmButton } from "../../components/ConfirmButton";
import { Markdown } from "../../components/Markdown";
import { count, credits } from "../../format";
import { DelegateModal } from "./DelegateModal";

/** The Copilot tab of a project: the agent tasks delegated to GitHub Copilot
 * (sessions on the left, ``?session=`` the open one) and the open session's
 * chat: Copilot's questions, «Ok, parti», then the execution followed live. */

export const STATUS: Record<string, { label: string; color: string }> = {
  planning: { label: "Preparazione", color: "blue" },
  queued: { label: "In coda", color: "gray" },
  running: { label: "In esecuzione", color: "orange" },
  done: { label: "Finita", color: "green" },
  failed: { label: "Fallita", color: "red" },
  cancelled: { label: "Annullata", color: "gray" },
};

/** ``agent-task-fix-porto.md`` → ``fix porto``: the task's name without prefix and suffix. */
const taskLabel = (note: string) => note.replace(/^agent-task-/i, "").replace(/\.md$/i, "").replace(/-/g, " ");
const repoLabel = (path: string) => path || "(cartella del progetto)";

export function CopilotTab() {
  const { project = "" } = useParams();
  const [search, setSearch] = useSearchParams();
  const sessions = useCopilotSessions(project);
  const status = useCopilotStatus(project);
  const [delegating, setDelegating] = useState(false);
  const requested = Number(search.get("session"));
  const selected = sessions.data?.find((session) => session.id === requested) ?? sessions.data?.[0];

  return (
    <Grid gutter="md">
      <Grid.Col span={{ base: 12, md: 3 }}>
        <Stack gap="xs">
          <Button onClick={() => setDelegating(true)} disabled={status.data && (!status.data.installed || !!status.data.definition_error)}>
            🤖 Delega un task
          </Button>
          {status.data && !status.data.installed && (
            <Alert color="orange" p="xs">
              <Text size="xs">Copilot CLI non è installato: <code>npm install -g @github/copilot</code>, poi <code>copilot</code> → <code>/login</code>.</Text>
            </Alert>
          )}
          {status.data?.definition_error && (
            <Alert color="orange" p="xs">
              <Text size="xs">Prompt e divieti di Copilot: {status.data.definition_error}</Text>
            </Alert>
          )}
          {sessions.isPending && <Loader size="sm" />}
          {sessions.error && <Alert color="red">{sessions.error.message}</Alert>}
          {sessions.data && !sessions.data.length && (
            <Text size="sm" c="dimmed">Nessun task delegato. Delegane uno da qui o dal form di un agent task (Dati → Agent task).</Text>
          )}
          {sessions.data?.map((session) => (
            <NavLink
              key={session.id}
              label={taskLabel(session.task_note)}
              description={repoLabel(session.repository)}
              rightSection={<Badge size="xs" variant="light" color={STATUS[session.status]?.color}>{STATUS[session.status]?.label}</Badge>}
              active={session.id === selected?.id}
              onClick={() => setSearch({ session: String(session.id) }, { replace: true })}
            />
          ))}
        </Stack>
      </Grid.Col>
      <Grid.Col span={{ base: 12, md: 9 }}>
        {selected ? (
          <SessionView key={selected.id} project={project} session={selected} onDeleted={() => setSearch({}, { replace: true })} />
        ) : (
          <Text c="dimmed">
            Delega un agent task a GitHub Copilot: nella chat Copilot legge il codice, ti fa le sue domande e propone un piano; con «Ok,
            parti» modifica i file del repository, senza mai fare commit.
          </Text>
        )}
      </Grid.Col>
      <DelegateModal project={project} opened={delegating} onClose={() => setDelegating(false)} />
    </Grid>
  );
}

function SessionView({ project, session, onDeleted }: { project: string; session: CopilotSession; onDeleted: () => void }) {
  const executing = isExecuting(session);
  const messages = useCopilotMessages(session.id, executing);
  const usage = useCopilotSessionUsage(session.id, executing);
  const send = useSendCopilotMessage(project);
  const approve = useApproveCopilot(project);
  const cancel = useCancelCopilot(project);
  const remove = useDeleteCopilotSession(project);
  const [text, setText] = useState("");
  const [pending, setPending] = useState<string>();
  const bottom = useRef<HTMLDivElement>(null);
  const list = messages.data ?? [];
  const answered = list.some((message) => message.role === "copilot");

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "end" }); // braces: browsers may return a promise, not a cleanup
  }, [list.length, pending]);

  const submit = () => {
    const message = text.trim();
    if (!message || send.isPending || executing) return;
    setPending(message);
    setText("");
    send.mutate({ id: session.id, text: message }, { onError: () => setText(message), onSettled: () => setPending(undefined) });
  };

  return (
    <Stack gap="sm">
      <Group justify="space-between" align="flex-start">
        <Stack gap={2}>
          <Group gap="xs">
            <Text fw={600}>{taskLabel(session.task_note)}</Text>
            <Badge variant="light" color={STATUS[session.status]?.color}>{STATUS[session.status]?.label}</Badge>
          </Group>
          <Text size="xs" c="dimmed">
            <code>{repoLabel(session.repository)}</code> · prompt: {session.prompt || "predefinito"} · modello:{" "}
            {session.model || "predefinito"}
          </Text>
          {usage.data && (
            <Text size="xs" c="dimmed" title={`${usage.data.turns.length} turni · cache letta ${count(usage.data.total.cache_read_tokens)} · scritta ${count(usage.data.total.cache_write_tokens)} · reasoning ${count(usage.data.total.reasoning_tokens)}`}>
              Uso: {credits(usage.data.total.ai_credits)} crediti AI · {usage.data.total.premium_requests} richieste premium · token{" "}
              {count(usage.data.total.input_tokens)} in / {count(usage.data.total.output_tokens)} out
            </Text>
          )}
        </Stack>
        <Group gap="xs">
          {session.status === "planning" && (
            <Button color="green" onClick={() => approve.mutate(session.id)} loading={approve.isPending} disabled={!answered || send.isPending}
                    title={answered ? undefined : "Aspetta la risposta di Copilot"}>
              ✅ Ok, parti
            </Button>
          )}
          {executing && (
            <Button color="red" variant="light" onClick={() => cancel.mutate(session.id)} loading={cancel.isPending} disabled={session.cancel_requested}>
              {session.cancel_requested ? "Annullamento in corso…" : "⏹️ Annulla"}
            </Button>
          )}
          {!executing && (
            <ConfirmButton
              size="xs"
              message="Eliminare la sessione e i suoi messaggi? Le modifiche di Copilot ai file restano."
              loading={remove.isPending}
              error={remove.error?.message}
              onConfirm={() => remove.mutate(session.id, { onSuccess: onDeleted })}
            >
              Elimina
            </ConfirmButton>
          )}
        </Group>
      </Group>
      {(approve.error || cancel.error) && <Alert color="red">{(approve.error ?? cancel.error)!.message}</Alert>}
      {session.head_moved && (
        <Alert color="red" title="L'HEAD è cambiato durante l'esecuzione">
          Un commit o un'altra operazione git non autorizzata ({session.head_before?.slice(0, 8) || "nessun commit"} → {session.head_after?.slice(0, 8)}). Controlla il
          repository: non è stato annullato niente.
        </Alert>
      )}
      {session.changed_files.length > 0 && !executing && (
        <Card withBorder padding="sm">
          <Text size="sm" fw={600}>File modificati nel repository ({session.changed_files.length})</Text>
          <List size="xs" mt={4}>
            {session.changed_files.map((path) => <List.Item key={path}><code>{path}</code></List.Item>)}
          </List>
          <Text size="xs" c="dimmed" mt={4}>Il commit lo fai tu: controlla le modifiche con il tuo editor o da Git.</Text>
        </Card>
      )}

      <Card withBorder p={0}>
        <ScrollArea h={460} p="md">
          <Stack gap="md">
            {messages.isPending && <Loader size="sm" />}
            {list.map((message) => <MessageItem key={message.id} message={message} />)}
            {pending && <MessageItem message={{ id: -1, role: "user", content: pending, created_at: "" }} />}
            {(send.isPending || session.status === "running") && (
              <Group gap="xs">
                <Loader size="xs" type="dots" />
                <Text size="sm" c="dimmed">{session.status === "running" ? "Copilot sta lavorando sui file…" : "Copilot sta pensando…"}</Text>
              </Group>
            )}
            <Box ref={bottom} />
          </Stack>
        </ScrollArea>
      </Card>
      {send.error && <Alert color="red">{send.error.message}</Alert>}
      {session.status === "queued" && <QueueHint />}
      <Group align="flex-end" wrap="nowrap">
        <Textarea
          style={{ flex: 1 }}
          autosize
          minRows={1}
          maxRows={8}
          disabled={executing}
          placeholder={executing ? "Copilot sta eseguendo: aspetta che finisca o annulla." : "Rispondi a Copilot… (Invio per mandare, Maiusc+Invio per andare a capo)"}
          value={text}
          onChange={(event) => setText(event.currentTarget.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault();
              submit();
            }
          }}
        />
        <Button onClick={submit} loading={send.isPending} disabled={!text.trim() || executing}>Invia</Button>
      </Group>
    </Stack>
  );
}

/** Who runs the execution: the worker, which must be on and started after the app's last update. */
function QueueHint() {
  const worker = useWorkerState();
  if (worker.isPending) return null;
  if (!worker.data?.workers.length) {
    return <Alert color="orange">Nessun worker attivo: l'esecuzione resta in coda. Avvialo dal menu Worker in alto a destra.</Alert>;
  }
  return (
    <Text size="xs" c="dimmed">
      In coda per il worker. Se non parte, riavvia il worker dal menu in alto a destra: dopo un aggiornamento dell'app un worker già acceso
      usa ancora il codice vecchio.
    </Text>
  );
}

/** Yours on the right; Copilot's on the left (markdown); the app's events in the middle. */
function MessageItem({ message }: { message: CopilotMessage }) {
  if (message.role === "user") {
    return (
      <Group justify="flex-end">
        <Paper bg="var(--mantine-primary-color-light)" px="md" py="xs" radius="md" maw="85%">
          <Text size="sm" style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{message.content}</Text>
        </Paper>
      </Group>
    );
  }
  if (message.role === "event") {
    return <Text size="xs" c="dimmed" ta="center" style={{ whiteSpace: "pre-wrap" }}>{message.content}</Text>;
  }
  return (
    <Group align="flex-start" wrap="nowrap" gap="sm" maw="90%">
      <Avatar size="sm" radius="xl" color="dark">🤖</Avatar>
      <Markdown>{message.content}</Markdown>
    </Group>
  );
}
