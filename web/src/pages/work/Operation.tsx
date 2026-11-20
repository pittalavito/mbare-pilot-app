import { Alert, Badge, Button, Card, Code, Fieldset, Group, Select, Stack, Text, TextInput, Textarea } from "@mantine/core";
import { useEffect, useRef, useState } from "react";

import { type Pipeline, isFinished, useEnqueueRun, usePipelines, useRuns } from "../../api/automation";
import { useAnswerCommand, useRunCommand } from "../../api/dev";
import { useGitStatus } from "../../api/git";
import { type PathTask, type Phase, useMarkDone, useSkipPhase, useStartAuto } from "../../api/plan";
import type { AgentTask } from "../../api/projectData";
import { useAgentPanel } from "../project/AgentPanel";
import { devRequest } from "./devRequest";

/** A development's Pre and Post, done without an agent when they can.
 * «🤖 Automatico» runs the commands, then the automation (the worker; first
 * error = stop), or asks Dev when there are neither; «✋ A mano» opens the
 * dashboard under the row: the commands one by one, the automation, the git
 * status, Dev in chat and «✅ Fatto»; «⏭ Salta» when there is nothing to do. */

export type DevPhase = { steps: string[]; commands: string[]; automation: string };
export const EMPTY_PHASE: DevPhase = { steps: [], commands: [], automation: "" };
const PHASE_TEXT: Record<Phase, { title: string; hint: string }> = {
  pre: { title: "Pre", hint: "Prima di delegare: branch, aggiornamento, build" },
  post: { title: "Post", hint: "Dopo la conferma finale: pulizia, test, commit" },
};

/** The task's commands (one per line) and automation, in the planner's draft and in the task's form. */
export function OperationFields({ project, commands, automation, onChange }: {
  project: string; commands: string[]; automation: string; onChange: (patch: { commands?: string[]; automation?: string }) => void;
}) {
  const pipelines = usePipelines(project);
  const names = (pipelines.data ?? []).map((pipeline) => pipeline.name);
  return (
    <>
      <Textarea size="xs" label="Comandi" description="Uno per riga, lanciati nel repository del task senza agente (🤖 Automatico)"
        autosize minRows={1} value={commands.join("\n")} onChange={(event) => onChange({ commands: event.currentTarget.value.split("\n") })} />
      <Select size="xs" label="Automation" description="Lanciata dopo i comandi" placeholder="Nessuna" clearable searchable
        data={automation && !names.includes(automation) ? [...names, automation] : names} value={automation || null}
        onChange={(value) => onChange({ automation: value ?? "" })} />
    </>
  );
}

/** A Pre or a Post: steps in words, commands, automation (the planner's draft, the task's form). */
export function PhaseFields({ project, phase, value, onChange }: { project: string; phase: Phase; value: DevPhase; onChange: (value: DevPhase) => void }) {
  const text = PHASE_TEXT[phase];
  return (
    <Fieldset legend={`${text.title} · ${text.hint}`} p="xs">
      <Stack gap={6}>
        <Textarea size="xs" label="Passi" description="Uno per riga, a parole: per Dev o per te" autosize minRows={1} value={value.steps.join("\n")}
          onChange={(event) => onChange({ ...value, steps: event.currentTarget.value.split("\n") })} />
        <OperationFields project={project} commands={value.commands} automation={value.automation} onChange={(patch) => onChange({ ...value, ...patch })} />
      </Stack>
    </Fieldset>
  );
}

/** Pre and Post of a development. */
export function PrePostFields({ project, pre, post, onChange }: {
  project: string; pre?: DevPhase; post?: DevPhase; onChange: (patch: { pre?: DevPhase; post?: DevPhase }) => void;
}) {
  return (
    <>
      <PhaseFields project={project} phase="pre" value={pre ?? EMPTY_PHASE} onChange={(value) => onChange({ pre: value })} />
      <PhaseFields project={project} phase="post" value={post ?? EMPTY_PHASE} onChange={(value) => onChange({ post: value })} />
    </>
  );
}

export const phaseOf = (task: AgentTask | undefined, phase: Phase): DevPhase => (task ? task[phase] ?? EMPTY_PHASE : EMPTY_PHASE);
const hasWork = (work: DevPhase) => work.commands.some((command) => command.trim()) || !!work.automation.trim();

/** «🤖 Automatico», «✋ A mano» and «⏭ Salta» on a development's Pre or Post. */
export function OperationButtons({ project, activity, task, phase, found }: {
  project: string; activity: string; task: PathTask; phase: Phase; found?: AgentTask;
}) {
  const start = useStartAuto(project, activity);
  const skip = useSkipPhase(project, activity);
  const { ask } = useAgentPanel();
  const [pending, setPending] = useState<string[]>([]);
  const [manual, setManual] = useState(false);
  const work = phaseOf(found, phase);
  const auto = () => {
    if (!found) return;
    if (!hasWork(work)) return ask(devRequest(found, phase, task.repository), "operator");
    start.mutate({ task: task.task, phase }, { onSuccess: (result) => setPending(result.pending_commands ?? []) });
  };
  return (
    <Stack gap={6} style={{ flex: 1 }}>
      <Group gap="xs">
        <Text size="xs" fw={600}>{PHASE_TEXT[phase].title}:</Text>
        <Button size="compact-xs" onClick={auto} loading={start.isPending}
          title={hasWork(work) ? "Comandi e automation, senza agente" : "Niente comandi né automation: lo fa Dev"}>
          🤖 Automatico
        </Button>
        <Button size="compact-xs" variant={manual ? "filled" : "default"} onClick={() => setManual((value) => !value)}>
          {manual ? "✋ Chiudi a mano" : "✋ A mano"}
        </Button>
        <Button size="compact-xs" variant="subtle" color="gray" onClick={() => skip.mutate({ task: task.task, phase })} loading={skip.isPending}>⏭ Salta</Button>
      </Group>
      {!!pending.length && (
        <PendingCommands project={project} commands={pending} onAnswered={(command) => setPending((items) => items.filter((item) => item !== command))} />
      )}
      {(start.error || skip.error) && <Text size="xs" c="red">{(start.error ?? skip.error)?.message}</Text>}
      {manual && <ManualDashboard project={project} activity={activity} task={task} phase={phase} found={found} />}
    </Stack>
  );
}

/** The commands not allowed: «Sempre», «Solo stavolta» or «No», then «Automatico» again. */
function PendingCommands({ project, commands, onAnswered }: { project: string; commands: string[]; onAnswered: (command: string) => void }) {
  return (
    <Alert color="yellow" p="xs" title="Comandi da permettere prima di partire">
      <Stack gap={4}>
        {commands.map((command) => <CommandAsk key={command} project={project} command={command} onAnswered={() => onAnswered(command)} />)}
        <Text size="xs" c="dimmed">Poi premi di nuovo «🤖 Automatico».</Text>
      </Stack>
    </Alert>
  );
}

function CommandAsk({ project, command, onAnswered }: { project: string; command: string; onAnswered: () => void }) {
  const answer = useAnswerCommand(project);
  const reply = (allow: boolean, always = false) => answer.mutate({ command, allow, always }, { onSuccess: onAnswered });
  return (
    <Group gap={4} wrap="nowrap">
      <Code style={{ flex: 1 }}>{command}</Code>
      <Button size="compact-xs" onClick={() => reply(true, true)} loading={answer.isPending}>Sempre</Button>
      <Button size="compact-xs" variant="light" onClick={() => reply(true)} loading={answer.isPending}>Solo stavolta</Button>
      <Button size="compact-xs" variant="subtle" color="red" onClick={() => reply(false)} loading={answer.isPending}>No</Button>
    </Group>
  );
}

/** The automatic run's log (commands and automation), folded. */
export function OperationOutput({ output }: { output: string }) {
  return (
    <details onClick={(event) => event.stopPropagation()}>
      <summary><Text span size="xs" c="dimmed">Esito dell'automatico</Text></summary>
      <Code block fz="xs" mah={240} style={{ overflow: "auto" }}>{output}</Code>
    </details>
  );
}

/** «✋ A mano»: the user's dashboard of the Pre or Post. */
function ManualDashboard({ project, activity, task, phase, found }: { project: string; activity: string; task: PathTask; phase: Phase; found?: AgentTask }) {
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => { box.current?.scrollIntoView?.({ behavior: "smooth", block: "nearest" }); }, []); // it opens under the row, often below the fold
  const work = phaseOf(found, phase);
  const [commands, setCommands] = useState<string[]>(() => work.commands.filter((command) => command.trim()));
  const pipelines = usePipelines(project);
  const [automation, setAutomation] = useState<string | null>(work.automation || null);
  const markDone = useMarkDone(project, activity);
  const { ask } = useAgentPanel();
  const chosen = pipelines.data?.find((pipeline) => pipeline.name === automation);
  return (
    <Card ref={box} withBorder p="xs" bg="var(--mantine-color-default-hover)" data-testid="manual-dashboard">
      <Stack gap="xs">
        {!!work.steps.length && (
          <>
            <Text size="xs" fw={700} c="dimmed" tt="uppercase">Passi</Text>
            {work.steps.map((step, index) => <Text key={index} size="xs">• {step}</Text>)}
          </>
        )}
        <Text size="xs" fw={700} c="dimmed" tt="uppercase">Comandi{task.repository ? ` · ${task.repository}` : ""}</Text>
        {commands.map((command, index) => (
          <CommandLine key={index} project={project} repository={task.repository} command={command}
            onChange={(value) => setCommands((items) => items.map((item, position) => (position === index ? value : item)))} />
        ))}
        <Group><Button size="compact-xs" variant="subtle" onClick={() => setCommands((items) => [...items, ""])}>➕ Comando</Button></Group>
        <Text size="xs" fw={700} c="dimmed" tt="uppercase">Automation</Text>
        <Group gap="xs" align="flex-end">
          <Select size="xs" aria-label="Automation da lanciare" placeholder="Scegli un'automation" clearable searchable style={{ flex: 1 }}
            data={(pipelines.data ?? []).map((pipeline) => pipeline.name)} value={automation} onChange={setAutomation} />
          {chosen && <AutomationRun pipeline={chosen} input={task.repository} />}
        </Group>
        <GitStatusLine project={project} repository={task.repository} />
        <Group gap="xs">
          <Button size="compact-xs" variant="default" onClick={() => found && ask(devRequest(found, phase, task.repository), "operator")}>💬 Dev in chat</Button>
          <Button size="compact-xs" color="green" variant="light" onClick={() => markDone.mutate({ task: task.task, phase })} loading={markDone.isPending}>✅ Fatto</Button>
        </Group>
        {markDone.error && <Text size="xs" c="red">{markDone.error.message}</Text>}
      </Stack>
    </Card>
  );
}

function CommandLine({ project, repository, command, onChange }: { project: string; repository: string; command: string; onChange: (value: string) => void }) {
  const run = useRunCommand(project);
  const result = run.data;
  return (
    <Stack gap={4}>
      <Group gap="xs" wrap="nowrap">
        <TextInput size="xs" ff="monospace" style={{ flex: 1 }} aria-label="Comando" value={command} onChange={(event) => onChange(event.currentTarget.value)} />
        <Button size="compact-xs" aria-label={`Lancia ${command}`} disabled={!command.trim()} loading={run.isPending}
          onClick={() => run.mutate({ repository, command })}>▶️</Button>
        {result?.allowed && <Badge size="xs" color={result.exit_code === 0 ? "green" : "red"}>{result.exit_code === 0 ? "ok" : `uscita ${result.exit_code}`}</Badge>}
      </Group>
      {result && !result.allowed && <CommandAsk project={project} command={command} onAnswered={() => run.reset()} />}
      {result?.allowed && result.output && <Code block fz="xs" mah={200} style={{ overflow: "auto" }}>{result.output}</Code>}
      {run.error && <Text size="xs" c="red">{run.error.message}</Text>}
    </Stack>
  );
}

function AutomationRun({ pipeline, input }: { pipeline: Pipeline; input: string }) {
  const enqueue = useEnqueueRun(pipeline.id);
  const runs = useRuns(pipeline.id);
  const latest = enqueue.data ? runs.data?.find((run) => run.id === enqueue.data?.id) ?? enqueue.data : undefined;
  return (
    <Group gap="xs">
      <Button size="compact-xs" onClick={() => enqueue.mutate(input)} loading={enqueue.isPending}>▶️ Lancia</Button>
      {latest && (
        <Badge size="xs" color={latest.status === "done" ? "green" : latest.status === "failed" ? "red" : "blue"}>
          {isFinished(latest) ? latest.status === "done" ? "fatta" : "fallita" : "in corso"}
        </Badge>
      )}
      {latest?.error && <Text size="xs" c="red">{latest.error}</Text>}
      {enqueue.error && <Text size="xs" c="red">{enqueue.error.message}</Text>}
    </Group>
  );
}

function GitStatusLine({ project, repository }: { project: string; repository: string }) {
  const status = useGitStatus(project);
  const data = status.data;
  return (
    <Group gap="xs">
      <Button size="compact-xs" variant="default" onClick={() => status.mutate(repository)} loading={status.isPending}>🌿 Stato git</Button>
      {data && (
        <Text size="xs">
          {data.branch ? <>branch <Code>{data.branch}</Code></> : "HEAD staccato"} · {data.is_clean ? "nessun file modificato" : `${data.changes.length} file modificati`}
        </Text>
      )}
      {status.error && <Text size="xs" c="red">{status.error.message}</Text>}
    </Group>
  );
}
