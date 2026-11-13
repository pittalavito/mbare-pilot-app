import { ActionIcon, Alert, Badge, Button, Card, Checkbox, Group, Loader, Select, Stack, Text, TextInput, Textarea } from "@mantine/core";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { useRepositories } from "../../api/git";
import {
  type ActivityPlan, type PathStep, type PathTask, type PlanProposal, useActivityPath, useConfirmPlan, useConfirmTask, useDismissPlan, useProposePlan,
} from "../../api/plan";
import { eur } from "../../format";
import { DelegateModal } from "../copilot/DelegateModal";

/** «▶️ Lavora attività» (plan 12a), at the top of an activity: the Pianificatore
 * proposes the agent tasks (one call with the small model), the user keeps,
 * corrects and orders them, then the **Percorso**: the tasks in order with
 * their steps and, where it is the user's turn, the button to go on. */

const TYPES = [
  { value: "development", label: "Sviluppo" }, { value: "analysis", label: "Analisi" },
  { value: "confluence", label: "Confluence" }, { value: "jira", label: "Jira" },
];
const STATE: Record<string, { icon: string; color: string; label: string }> = {
  todo: { icon: "○", color: "gray", label: "da fare" },
  you: { icon: "👤", color: "orange", label: "tocca a te" },
  running: { icon: "⏳", color: "blue", label: "in corso" },
  done: { icon: "✓", color: "green", label: "fatto" },
  failed: { icon: "✗", color: "red", label: "fallito" },
  skipped: { icon: "–", color: "gray", label: "saltato" },
};

export function ActivityPath({ project, activity }: { project: string; activity: string }) {
  const path = useActivityPath(project, activity);
  const propose = useProposePlan(project, activity);
  if (path.isPending) return <Loader size="xs" />;
  if (path.error) return <Alert color="red">{path.error.message}</Alert>;
  const { plan, tasks } = path.data;
  return (
    <Card withBorder p="sm">
      <Stack gap="xs">
        {plan?.status === "proposed" ? (
          <Proposals key={plan.id} project={project} activity={activity} plan={plan} />
        ) : tasks.length ? (
          <Path project={project} activity={activity} tasks={tasks} onReplan={() => propose.mutate()} replanning={propose.isPending} />
        ) : (
          <Group justify="space-between" wrap="nowrap">
            <Text size="sm" c="dimmed">Il Pianificatore propone gli agent task dell'attività, in ordine, con obiettivo e criteri: li confermi tu.</Text>
            <Button size="xs" onClick={() => propose.mutate()} loading={propose.isPending}>▶️ Lavora attività</Button>
          </Group>
        )}
        {propose.error && <Alert color="red">{propose.error.message}</Alert>}
      </Stack>
    </Card>
  );
}

type Draft = PlanProposal & { keep: boolean };

/** The proposals: keep, correct and order them, then «Crea i task» (no LLM). */
function Proposals({ project, activity, plan }: { project: string; activity: string; plan: ActivityPlan }) {
  const confirm = useConfirmPlan(project, activity);
  const dismiss = useDismissPlan(project, activity);
  const repositories = useRepositories(project);
  const [drafts, setDrafts] = useState<Draft[]>(() => (plan.proposals ?? []).map((proposal) => ({ ...proposal, keep: true })));
  useEffect(() => setDrafts((plan.proposals ?? []).map((proposal) => ({ ...proposal, keep: true }))), [plan.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const set = (id: number, patch: Partial<Draft>) => setDrafts((items) => items.map((item) => (item.id === id ? { ...item, ...patch } : item)));
  const move = (index: number, by: number) => setDrafts((items) => {
    const next = [...items];
    [next[index], next[index + by]] = [next[index + by], next[index]];
    return next;
  });
  const kept = drafts.filter((item) => item.keep && item.title.trim());
  const create = () => confirm.mutate(kept.map(({ id, title, type, repository, objective, criteria }) => ({ id, title, type, repository, objective, criteria: (criteria ?? []).filter((text) => text.trim()) })));
  return (
    <>
      <Group justify="space-between">
        <Text fw={600} size="sm">▶️ Il piano del Pianificatore</Text>
        <Text size="xs" c="dimmed">{plan.cost_eur ? `costato ${eur(plan.cost_eur)}` : ""}</Text>
      </Group>
      {!drafts.length && <Text size="sm" c="dimmed">Nessun task proposto: scarta il piano o aggiungi voci all'attività e riprova.</Text>}
      {drafts.map((draft, index) => (
        <Card key={draft.id} withBorder p="xs" opacity={draft.keep ? 1 : 0.5} data-testid="plan-proposal">
          <Stack gap={6}>
            <Group gap="xs" wrap="nowrap">
              <Checkbox aria-label={`Tieni ${draft.title}`} checked={draft.keep} onChange={(event) => set(draft.id, { keep: event.currentTarget.checked })} />
              <Text size="xs" c="dimmed">{index + 1}.</Text>
              <TextInput size="xs" aria-label="Titolo del task" style={{ flex: 1 }} value={draft.title} onChange={(event) => set(draft.id, { title: event.currentTarget.value })} />
              {draft.new && <Badge size="xs" color="violet" variant="light">nuovo</Badge>}
              <ActionIcon size="sm" variant="subtle" aria-label="Su" disabled={index === 0} onClick={() => move(index, -1)}>↑</ActionIcon>
              <ActionIcon size="sm" variant="subtle" aria-label="Giù" disabled={index === drafts.length - 1} onClick={() => move(index, 1)}>↓</ActionIcon>
            </Group>
            {draft.keep && (
              <>
                {draft.reason && <Text size="xs" c="dimmed">💡 {draft.reason}</Text>}
                {!!draft.item_texts?.length && <Text size="xs" c="dimmed">Dalle voci: {draft.item_texts.join(" · ")}</Text>}
                {draft.new && <Text size="xs" c="dimmed">Non c'è nelle voci: confermandolo diventa anche una voce dell'attività.</Text>}
                <Group grow gap="xs">
                  <Select size="xs" aria-label="Tipo" data={TYPES} value={draft.type} allowDeselect={false}
                    onChange={(value) => value && set(draft.id, { type: value as Draft["type"] })} />
                  <Select size="xs" aria-label="Repository" placeholder="Nessun repository" clearable
                    data={(repositories.data ?? []).map((repo) => ({ value: repo.path, label: repo.path || "(cartella del progetto)" }))}
                    value={draft.repository || null} onChange={(value) => set(draft.id, { repository: value ?? "" })} />
                </Group>
                <Textarea size="xs" aria-label="Obiettivo" placeholder="Obiettivo" autosize minRows={1} value={draft.objective ?? ""}
                  onChange={(event) => set(draft.id, { objective: event.currentTarget.value })} />
                <Textarea size="xs" aria-label="Criteri" placeholder="Criteri di accettazione, uno per riga" autosize minRows={1}
                  value={(draft.criteria ?? []).join("\n")} onChange={(event) => set(draft.id, { criteria: event.currentTarget.value.split("\n") })} />
              </>
            )}
          </Stack>
        </Card>
      ))}
      {(confirm.error || dismiss.error) && <Alert color="red">{(confirm.error ?? dismiss.error)?.message}</Alert>}
      <Group justify="flex-end">
        <Button size="xs" variant="default" onClick={() => dismiss.mutate()} loading={dismiss.isPending}>Scarta</Button>
        <Button size="xs" onClick={create} loading={confirm.isPending} disabled={!kept.length}>Crea {kept.length} task</Button>
      </Group>
    </>
  );
}

/** The confirmed plan: the tasks in order, their steps, the button where it is the user's turn. */
function Path({ project, activity, tasks, onReplan, replanning }: {
  project: string; activity: string; tasks: PathTask[]; onReplan: () => void; replanning: boolean;
}) {
  const doneCount = tasks.filter((task) => task.status === "done").length;
  return (
    <>
      <Group justify="space-between">
        <Text fw={600} size="sm">🧭 Percorso · {doneCount} di {tasks.length} task fatti</Text>
        <Button size="compact-xs" variant="subtle" onClick={onReplan} loading={replanning}>Nuovo piano</Button>
      </Group>
      {tasks.map((task, index) => <TaskRow key={task.task} project={project} activity={activity} task={task} number={index + 1} />)}
    </>
  );
}

function TaskRow({ project, activity, task, number }: { project: string; activity: string; task: PathTask; number: number }) {
  const [, setSearch] = useSearchParams();
  const confirmTask = useConfirmTask(project, activity);
  const [delegating, setDelegating] = useState(false);
  const steps = task.steps ?? [];
  const current = task.current ? steps.find((step) => step.state !== "done" && step.state !== "skipped") : undefined;
  const open = () => setSearch({ note: task.task }, { replace: true });
  return (
    <Card withBorder p="xs" bg={task.current ? "var(--mantine-color-blue-light)" : undefined} data-testid="path-task">
      <Stack gap={6}>
        <Group justify="space-between" wrap="nowrap">
          <Group gap={6} wrap="nowrap" style={{ minWidth: 0 }}>
            <Text size="xs" c="dimmed">{number}.</Text>
            <Button size="compact-sm" variant="subtle" onClick={open} disabled={task.status === "missing"}>{task.title}</Button>
            {task.repository && <Badge size="xs" variant="outline">{task.repository}</Badge>}
          </Group>
          {task.status === "missing" && <Badge size="xs" color="red">cancellato</Badge>}
        </Group>
        <Group gap={4}>
          {steps.map((step) => <StepBadge key={step.key} step={step} />)}
        </Group>
        {current && (
          <Group gap="xs">
            {current.key === "confirm" && (
              <>
                <Button size="compact-xs" onClick={() => confirmTask.mutate(task.task)} loading={confirmTask.isPending}>✅ Conferma il task</Button>
                <Button size="compact-xs" variant="default" onClick={open}>✏️ Correggi</Button>
              </>
            )}
            {current.key === "delegate" && <Button size="compact-xs" onClick={() => setDelegating(true)}>🤖 Delega a Copilot</Button>}
            {(current.key === "copilot_plan" || current.key === "answer") && current.state === "you" && (
              <Button size="compact-xs" onClick={open}>💬 Rispondi a Copilot</Button>
            )}
            {current.key === "final" && current.state === "you" && <Button size="compact-xs" onClick={open}>🔍 Controlla e conferma</Button>}
            {current.state === "failed" && <Button size="compact-xs" color="red" variant="light" onClick={open}>Apri il task</Button>}
          </Group>
        )}
        {confirmTask.error && <Text size="xs" c="red">{confirmTask.error.message}</Text>}
      </Stack>
      {delegating && (
        <DelegateModal project={project} task={task.task} repository={task.repository} opened onClose={() => setDelegating(false)} />
      )}
    </Card>
  );
}

function StepBadge({ step }: { step: PathStep }) {
  const state = STATE[step.state] ?? STATE.todo;
  return (
    <Badge size="sm" variant={step.state === "you" ? "filled" : "light"} color={state.color} title={`${step.label}: ${state.label}${step.detail ? ` · ${step.detail}` : ""}`}>
      {state.icon} {step.label}
    </Badge>
  );
}
