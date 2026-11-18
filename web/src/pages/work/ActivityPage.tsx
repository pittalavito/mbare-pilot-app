import {
  ActionIcon, Alert, Anchor, Badge, Button, Card, Group, Loader, MultiSelect, Select, Stack, Switch, Text, TextInput, Textarea, UnstyledButton,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { useRepositories } from "../../api/git";
import {
  type ActivityPath, type ActivityPlan, type PathStep, type PathTask, type PlanChoice, useActivityPath, useCloseActivity, useConfirmPlan,
  useDismissPlan, useMarkDone, usePausePlan, useProposeLearned, useProposePlan, useReopenActivity, useRetryStep, useSetPlanOptions,
} from "../../api/plan";
import { useStartWorker, useWorkerState } from "../../api/worker";
import { type Activity, type ActivityBody, useAgentTasks, useDeleteNote, useSaveActivity, useSaveAgentTask } from "../../api/projectData";
import { ConfirmButton } from "../../components/ConfirmButton";
import { eur } from "../../format";
import { DelegateModal } from "../copilot/DelegateModal";
import { SendBackModal } from "../copilot/SendBackModal";
import { ChecklistEditor } from "../data/ChecklistEditor";
import { ReferencesSection } from "../data/ReferencesSection";
import { useAgentPanel } from "../project/AgentPanel";
import { devRequest } from "./devRequest";

/** An activity in steps (plan 18): 1. Descrivi → 2. Pianifica → 3. Lavora →
 * 4. Chiudi. The step is in ``?step=`` (the bar goes back to one done,
 * «Avanti» goes on); without it, it comes from where the activity is. The
 * status follows the steps (to do, in progress once tasks exist, done when
 * closed): it is never chosen by hand. A task's row in «Lavora» is picked with
 * ``?task=``: the agent panel shows its Copilot chat; «Apri» opens the task
 * (``?from=`` the activity: «← Torna all'attività»). Pre/post development
 * tasks (plan 22) never go to Copilot: «Fallo fare a Dev» or by hand, «Fatto». */

export type StepKey = "describe" | "plan" | "work" | "close";
const STEPS: { key: StepKey; label: string; hint: string }[] = [
  { key: "describe", label: "Descrivi", hint: "descrizione, voci, riferimenti" },
  { key: "plan", label: "Pianifica", hint: "i task, in ordine" },
  { key: "work", label: "Lavora", hint: "il giro con Copilot e Dev" },
  { key: "close", label: "Chiudi", hint: "riepilogo e cosa ho imparato" },
];
const STATUS = { todo: ["Da fare", "gray"], in_progress: ["In corso", "blue"], done: ["Fatta", "green"] } as const;
const TYPES = [
  { value: "development", label: "Sviluppo" }, { value: "analysis", label: "Analisi" },
  { value: "confluence", label: "Confluence" }, { value: "jira", label: "Jira" },
  { value: "pre_dev", label: "Pre sviluppo" }, { value: "post_dev", label: "Post sviluppo" },
];
const isOperations = (type: string) => type === "pre_dev" || type === "post_dev";
/** The task's form, coming back to this activity (``?from=``). */
const taskLink = (project: string, task: string, activity: string) =>
  `/projects/${encodeURIComponent(project)}/work?note=${encodeURIComponent(task)}&from=${encodeURIComponent(activity)}`;
const typeLabel = (type: string) => TYPES.find((item) => item.value === type)?.label ?? type;
const STATE: Record<string, { icon: string; color: string; label: string }> = {
  todo: { icon: "○", color: "gray", label: "da fare" },
  you: { icon: "👤", color: "orange", label: "tocca a te" },
  running: { icon: "⏳", color: "blue", label: "in corso" },
  done: { icon: "✓", color: "green", label: "fatto" },
  failed: { icon: "✗", color: "red", label: "fallito" },
  skipped: { icon: "–", color: "gray", label: "saltato" },
};

/** Where the activity is, when ``?step=`` does not say. */
export function stepOf(activity: Activity, path: ActivityPath | undefined): StepKey {
  if (activity.status === "done") return "close";
  if (path?.tasks.length) return path.tasks.some((task) => task.current) ? "work" : "close";
  return path?.plan?.proposals?.length ? "plan" : "describe";
}

export function ActivityPage({ project, activity }: { project: string; activity: Activity }) {
  const path = useActivityPath(project, activity.name);
  const [search, setSearch] = useSearchParams();
  const requested = search.get("step") as StepKey | null;
  const hasTasks = !!path.data?.tasks.length;
  const reachable = (key: StepKey) => key !== "work" || hasTasks;
  const derived = stepOf(activity, path.data);
  const step = requested && STEPS.some((item) => item.key === requested) && reachable(requested) ? requested : derived;
  const go = (key: StepKey) => setSearch({ note: activity.name, step: key }, { replace: true });
  const index = STEPS.findIndex((item) => item.key === step);
  const [label, color] = STATUS[activity.status ?? "todo"];
  const reopen = useReopenActivity(project, activity.name);
  return (
    <Stack gap="md">
      <Group justify="space-between" align="flex-start">
        <div>
          <Text size="xs" c="dimmed"><code>{activity.name}</code></Text>
          <Text fw={700} size="xl">{activity.title}</Text>
        </div>
        <Group gap="xs">
          <Badge variant="light" color={color} title="Lo stato segue gli step">{label}</Badge>
          {activity.status === "done" && (
            <Button size="compact-sm" variant="default" loading={reopen.isPending}
              onClick={() => reopen.mutate(undefined, { onSuccess: () => { go("plan"); notifications.show({ message: `${activity.title}: riaperta.` }); } })}>
              ↩ Riapri
            </Button>
          )}
        </Group>
      </Group>
      <Group gap="xs" grow wrap="nowrap" role="tablist" aria-label="Step dell'attività">
        {STEPS.map((item, position) => {
          const done = position < index || (item.key === "close" && activity.status === "done");
          return (
            <UnstyledButton key={item.key} role="tab" aria-selected={item.key === step} disabled={!reachable(item.key)} onClick={() => go(item.key)}
              style={{
                border: `1px solid var(--mantine-color-${item.key === step ? "blue-6" : "default-border"})`, borderRadius: 8, padding: "6px 10px",
                opacity: reachable(item.key) ? 1 : 0.45, cursor: reachable(item.key) ? "pointer" : "not-allowed",
              }}>
              <Group gap={8} wrap="nowrap">
                <Badge circle size="lg" variant={item.key === step || done ? "filled" : "light"} color={done ? "green" : item.key === step ? "blue" : "gray"}>
                  {done ? "✓" : position + 1}
                </Badge>
                <div style={{ minWidth: 0 }}>
                  <Text size="sm" fw={600}>{item.label}</Text>
                  <Text size="xs" c="dimmed" truncate>{item.hint}</Text>
                </div>
              </Group>
            </UnstyledButton>
          );
        })}
      </Group>
      {path.error && <Alert color="red">{path.error.message}</Alert>}
      {path.isPending ? <Loader size="sm" /> : (
        <>
          {step === "describe" && <Describe key={activity.name} project={project} activity={activity} onNext={() => go("plan")} />}
          {step === "plan" && <Plan project={project} activity={activity} path={path.data!} onBack={() => go("describe")} onNext={() => go("work")} />}
          {step === "work" && <Work project={project} activity={activity.name} path={path.data!} onBack={() => go("plan")} onNext={() => go("close")} />}
          {step === "close" && <Close project={project} activity={activity} path={path.data!} onBack={() => go(hasTasks ? "work" : "plan")} />}
        </>
      )}
    </Stack>
  );
}

// -------------------------------------------------------------- 1. Descrivi

const body = (activity: Activity): ActivityBody => {
  const { name: _name, ...rest } = activity;
  return rest;
};

function Describe({ project, activity, onNext }: { project: string; activity: Activity; onNext: () => void }) {
  const save = useSaveActivity(project);
  const remove = useDeleteNote(project);
  const [form, setForm] = useState<ActivityBody>(() => body(activity));
  const [base, setBase] = useState<ActivityBody>(() => body(activity));
  const dirty = JSON.stringify(form) !== JSON.stringify(base);
  const latest = JSON.stringify(body(activity));
  useEffect(() => { // changed elsewhere (the secretary, a task done): reloaded when nothing is unsaved
    if (latest !== JSON.stringify(base) && !dirty) { setForm(body(activity)); setBase(body(activity)); }
  }, [latest]); // eslint-disable-line react-hooks/exhaustive-deps
  const set = (patch: Partial<ActivityBody>) => setForm((current) => ({ ...current, ...patch }));
  const write = (then?: () => void) => save.mutate(
    { name: activity.name, body: { ...form, items: (form.items ?? []).filter((item) => item.text.trim()) } },
    { onSuccess: (saved) => { setForm(body(saved)); setBase(body(saved)); notifications.show({ message: `${saved.title} salvata.` }); then?.(); } },
  );
  const items = form.items ?? [];
  return (
    <Stack gap="sm" onKeyDown={(event) => {
      if (event.key === "s" && (event.ctrlKey || event.metaKey)) { event.preventDefault(); if (dirty && form.title.trim()) write(); }
    }}>
      <TextInput label="Titolo" value={form.title} onChange={(event) => set({ title: event.currentTarget.value })} />
      <Textarea label="Descrizione" description="Di cosa si tratta, perché, per quando." autosize minRows={2} value={form.description ?? ""}
        onChange={(event) => set({ description: event.currentTarget.value })} />
      <div>
        <Text size="sm" fw={500} mb={4}>Voci della todo <Text span size="xs" c="dimmed">· {items.filter((item) => item.done).length} di {items.length} fatte</Text></Text>
        <ChecklistEditor items={items} onChange={(next) => set({ items: next })} withDetails addLabel="Voce" />
      </div>
      <ReferencesSection project={project} value={form.references ?? []} onChange={(references) => set({ references })} />
      {save.error && <Alert color="red">{save.error.message}</Alert>}
      <Group justify="space-between" pt="sm" style={{ borderTop: "1px solid var(--mantine-color-default-border)" }}>
        <Group gap="xs">
          <Button variant="default" onClick={() => write()} loading={save.isPending} disabled={!dirty || !form.title.trim()}>Salva</Button>
          {dirty && <Text size="xs" c="orange">modifiche non salvate · Ctrl+S</Text>}
          <ConfirmButton message={`Eliminare ${activity.name}? I suoi task restano.`} loading={remove.isPending} error={remove.error?.message}
            onConfirm={() => remove.mutate(activity.name)}>Elimina</ConfirmButton>
        </Group>
        <Button onClick={() => (dirty ? write(onNext) : onNext())} disabled={!form.title.trim()}>Avanti: Pianifica →</Button>
      </Group>
    </Stack>
  );
}

// ------------------------------------------------------------- 2. Pianifica

type Draft = { key: string; id: number | null; title: string; type: PlanChoice["type"]; repository: string; items: number[]; itemTexts: string[];
  isNew: boolean; reason: string; objective: string; criteria: string[]; steps: string[] };

const fromPlan = (plan: ActivityPlan | null | undefined): Draft[] => (plan?.proposals ?? []).map((proposal) => ({
  key: `p${proposal.id}`, id: proposal.id, title: proposal.title, type: proposal.type, repository: proposal.repository ?? "", items: proposal.items ?? [],
  itemTexts: proposal.item_texts ?? [], isNew: !!proposal.new, reason: proposal.reason ?? "", objective: proposal.objective ?? "", criteria: proposal.criteria ?? [],
  steps: proposal.steps ?? [],
}));

function Plan({ project, activity, path, onBack, onNext }: { project: string; activity: Activity; path: ActivityPath; onBack: () => void; onNext: () => void }) {
  const propose = useProposePlan(project, activity.name);
  const confirm = useConfirmPlan(project, activity.name);
  const dismiss = useDismissPlan(project, activity.name);
  const repositories = useRepositories(project);
  const [drafts, setDrafts] = useState<Draft[]>(() => fromPlan(path.plan));
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const proposalsKey = JSON.stringify(path.plan?.proposals ?? []);
  useEffect(() => setDrafts((current) => [...fromPlan(path.plan), ...current.filter((item) => item.id === null)]), [proposalsKey]); // eslint-disable-line react-hooks/exhaustive-deps
  const set = (key: string, patch: Partial<Draft>) => setDrafts((items) => items.map((item) => (item.key === key ? { ...item, ...patch } : item)));
  const move = (index: number, by: number) => setDrafts((items) => {
    const next = [...items];
    [next[index], next[index + by]] = [next[index + by], next[index]];
    return next;
  });
  const free = activity.items.map((item, position) => ({ number: position + 1, item })).filter(({ item }) => !item.done && !item.agent_task);
  const addByHand = () => {
    const key = `m${Date.now()}`;
    setDrafts((items) => [...items, { key, id: null, title: "", type: "development", repository: "", items: [], itemTexts: [], isNew: false, reason: "", objective: "", criteria: [], steps: [] }]);
    setOpen((current) => ({ ...current, [key]: true }));
  };
  const ready = drafts.filter((item) => item.title.trim());
  const create = () => confirm.mutate(ready.map((item) => ({
    id: item.id, items: item.id === null ? item.items : [], title: item.title.trim(), type: item.type, repository: item.repository,
    objective: item.objective, criteria: item.criteria.filter((text) => text.trim()),
    steps: isOperations(item.type) ? item.steps.filter((text) => text.trim()) : [],
  })), { onSuccess: () => { setDrafts([]); notifications.show({ message: `${ready.length} task creati, da fare.` }); onNext(); } });
  const repoData = (repositories.data ?? []).map((repo) => ({ value: repo.path, label: repo.path || "(cartella del progetto)" }));
  return (
    <Stack gap="sm">
      {!!path.tasks.length && (
        <Stack gap={4}>
          <Text size="xs" fw={700} c="dimmed" tt="uppercase">Task già creati</Text>
          {path.tasks.map((task, position) => (
            <Group key={task.task} gap="xs" wrap="nowrap">
              <Text size="sm" c="dimmed">{position + 1}.</Text>
              <Text size="sm" fw={500} style={{ flex: 1, minWidth: 0 }} truncate>{task.title}</Text>
              <Badge size="xs" variant="light">{typeLabel(task.type)}</Badge>
              <TaskStatusBadge status={task.status} />
            </Group>
          ))}
          <Text size="xs" fw={700} c="dimmed" tt="uppercase" mt="xs">Aggiungi</Text>
        </Stack>
      )}
      <Group gap="xs">
        <Button variant="light" onClick={() => propose.mutate()} loading={propose.isPending}>
          ✨ {path.tasks.length ? "Proponi altri task" : "Proponi i task"}
        </Button>
        <Button variant="default" onClick={addByHand}>➕ Task</Button>
        <Text size="xs" c="dimmed">
          {path.tasks.length ? "Il Pianificatore guarda solo le voci ancora senza task." : "Una chiamata al Pianificatore: legge descrizione, voci aperte, titoli dei riferimenti, repository, le regole di sviluppo (context/sviluppo.md) e un po' di contesto; attorno a ogni sviluppo propone un pre e un post sviluppo."}
          {path.plan?.cost_eur ? ` Finora: ${eur(path.plan.cost_eur)}.` : ""}
        </Text>
      </Group>
      {propose.error && <Alert color="red">{propose.error.message}</Alert>}
      {drafts.map((draft, position) => (
        <Card key={draft.key} withBorder p="xs" data-testid="plan-row">
          <Group gap="xs" wrap="nowrap">
            <Stack gap={0}>
              <ActionIcon size="xs" variant="subtle" aria-label="Su" disabled={position === 0} onClick={() => move(position, -1)}>▲</ActionIcon>
              <ActionIcon size="xs" variant="subtle" aria-label="Giù" disabled={position === drafts.length - 1} onClick={() => move(position, 1)}>▼</ActionIcon>
            </Stack>
            <TextInput size="xs" aria-label="Titolo del task" placeholder="Titolo del task" style={{ flex: 1 }} value={draft.title}
              onChange={(event) => set(draft.key, { title: event.currentTarget.value })} />
            <Badge size="xs" variant="light">{typeLabel(draft.type)}</Badge>
            {draft.repository && <Badge size="xs" variant="outline">{draft.repository}</Badge>}
            <Text size="xs" c="dimmed" style={{ whiteSpace: "nowrap" }}>
              {draft.id === null ? "a mano" : draft.isNew ? "nuovo" : draft.items.length ? `voci ${draft.items.join(", ")}` : "senza voci"}
            </Text>
            <Button size="compact-xs" variant="subtle" onClick={() => setOpen((current) => ({ ...current, [draft.key]: !current[draft.key] }))}>
              {open[draft.key] ? "▾ meno" : "▸ dettagli"}
            </Button>
            <ActionIcon size="sm" variant="subtle" color="gray" aria-label={`Scarta ${draft.title || "il task"}`}
              onClick={() => setDrafts((items) => items.filter((item) => item.key !== draft.key))}>✕</ActionIcon>
          </Group>
          {open[draft.key] && (
            <Stack gap={6} mt="xs">
              {draft.reason && <Text size="xs" c="dimmed">💡 {draft.reason}</Text>}
              {!!draft.itemTexts.length && <Text size="xs" c="dimmed">Dalle voci: {draft.itemTexts.join(" · ")}</Text>}
              {draft.isNew && <Text size="xs" c="dimmed">Non c'è nelle voci: creandolo diventa anche una voce dell'attività.</Text>}
              <Group grow gap="xs">
                <Select size="xs" label="Tipo" data={TYPES} value={draft.type} allowDeselect={false}
                  onChange={(value) => value && set(draft.key, { type: value as Draft["type"] })} />
                <Select size="xs" label="Repository" placeholder="Nessun repository" clearable data={repoData}
                  value={draft.repository || null} onChange={(value) => set(draft.key, { repository: value ?? "" })} />
              </Group>
              {draft.id === null && (
                <MultiSelect size="xs" label="Voci che copre" placeholder={free.length ? "Nessuna" : "Nessuna voce libera"} clearable
                  data={free.map(({ number, item }) => ({ value: String(number), label: `${number}. ${item.text}` }))}
                  value={draft.items.map(String)} onChange={(value) => set(draft.key, { items: value.map(Number) })} />
              )}
              <Textarea size="xs" label="Obiettivo" autosize minRows={1} value={draft.objective}
                onChange={(event) => set(draft.key, { objective: event.currentTarget.value })} />
              <Textarea size="xs" label="Criteri di accettazione" description="Uno per riga" autosize minRows={1} value={draft.criteria.join("\n")}
                onChange={(event) => set(draft.key, { criteria: event.currentTarget.value.split("\n") })} />
              {isOperations(draft.type) && (
                <Textarea size="xs" label="Passi" description="Uno per riga: li fa Dev o tu" autosize minRows={1} value={draft.steps.join("\n")}
                  onChange={(event) => set(draft.key, { steps: event.currentTarget.value.split("\n") })} />
              )}
            </Stack>
          )}
        </Card>
      ))}
      {(confirm.error || dismiss.error) && <Alert color="red">{(confirm.error ?? dismiss.error)?.message}</Alert>}
      <Group justify="space-between" pt="sm" style={{ borderTop: "1px solid var(--mantine-color-default-border)" }}>
        <Button variant="default" onClick={onBack}>← Descrivi</Button>
        <Group gap="xs">
          {!!path.plan?.proposals?.length && (
            <Button variant="subtle" color="gray" onClick={() => dismiss.mutate(undefined, { onSuccess: () => setDrafts((items) => items.filter((item) => item.id === null)) })}
              loading={dismiss.isPending}>Scarta le proposte</Button>
          )}
          {!!ready.length && (
            <>
              <Text size="xs" c="dimmed">Nascono «da fare»: niente conferma uno per uno.</Text>
              <Button onClick={create} loading={confirm.isPending}>Crea {ready.length} task</Button>
            </>
          )}
          {!ready.length && !!path.tasks.length && <Button onClick={onNext}>Avanti: Lavora →</Button>}
        </Group>
      </Group>
    </Stack>
  );
}

function TaskStatusBadge({ status }: { status: string }) {
  const [label, color] = ({
    created: ["creato", "gray"], refinement: ["in rifinitura", "violet"], todo: ["da fare", "gray"], in_progress: ["in corso", "blue"],
    to_verify: ["da verificare", "orange"], done: ["fatto", "green"], missing: ["cancellato", "red"], you: ["tocca a te", "orange"],
  } as Record<string, [string, string]>)[status] ?? [status, "gray"];
  return <Badge size="xs" variant="light" color={color}>{label}</Badge>;
}

// ---------------------------------------------------------------- 3. Lavora

function Work({ project, activity, path, onBack, onNext }: { project: string; activity: string; path: ActivityPath; onBack: () => void; onNext: () => void }) {
  const plan = path.plan!;
  const pause = usePausePlan(project, activity);
  const options = useSetPlanOptions(project, activity);
  const [search, setSearch] = useSearchParams();
  const selected = search.get("task");
  const current = path.tasks.find((task) => task.current);
  const started = path.tasks.some((task) => task.status !== "todo" || task.session_id);
  const pick = (task: string) => setSearch({ note: activity, step: "work", task }, { replace: true });
  const worker = useWorkerState();
  const startWorker = useStartWorker();
  const workerStopped = worker.data?.status === "stopped";
  return (
    <Stack gap="sm">
      {workerStopped && current && (
        <Alert color="red" p="xs" title="Il worker è fermo: il giro non parte">
          <Group gap="xs">
            <Text size="sm">La delega e l'ok del giro li fa il worker. La delega a mano funziona lo stesso.</Text>
            <Button size="compact-sm" onClick={() => startWorker.mutate()} loading={startWorker.isPending}>Avvia il worker</Button>
          </Group>
          {startWorker.error && <Text size="xs" c="red" mt={4}>{startWorker.error.message}</Text>}
        </Alert>
      )}
      {current ? (
        <Alert color={plan.paused ? "orange" : "blue"} p="xs">
          {plan.paused
            ? `${started ? "In pausa." : "Pronto."} Premi «${started ? "▶️ Riprendi" : "▶️ Avvia"}»: il giro delega a Copilot e lo segue da solo, e si ferma dove servi tu (i task pre e post sviluppo li fa Dev o tu).`
            : "Il giro è partito: delega a Copilot e lo segue da solo; si ferma dove servi tu (i task pre e post sviluppo li fa Dev o tu)."}
        </Alert>
      ) : <Alert color="green" p="xs">Tutti i task sono fatti: passa a Chiudi.</Alert>}
      <Card withBorder p="sm" bg="var(--mantine-color-default-hover)">
        <Group align="center" gap="sm" wrap="wrap">
          <Button color={plan.paused ? "blue" : "gray"} variant={plan.paused ? "filled" : "light"} disabled={!current}
            onClick={() => pause.mutate(!plan.paused)} loading={pause.isPending}>
            {plan.paused ? (started ? "▶️ Riprendi" : "▶️ Avvia") : "⏸ Pausa"}
          </Button>
          <Switch size="sm" label="Parti senza chiedermi l'ok al piano di Copilot" checked={!!plan.auto_approve}
            onChange={(event) => options.mutate({ auto_approve: event.currentTarget.checked })} />
        </Group>
        {(pause.error || options.error) && <Text size="xs" c="red" mt={4}>{(pause.error ?? options.error)?.message}</Text>}
      </Card>
      {path.tasks.map((task, position) => (
        <TaskRow key={task.task} project={project} activity={activity} task={task} number={position + 1} paused={!!plan.paused}
          selected={selected === task.task} onPick={() => pick(task.task)} />
      ))}
      <Group justify="space-between" pt="sm" style={{ borderTop: "1px solid var(--mantine-color-default-border)" }}>
        <Button variant="default" onClick={onBack}>← Pianifica (aggiungi task)</Button>
        <Button variant={current ? "default" : "filled"} onClick={onNext}>Avanti: Chiudi →</Button>
      </Group>
    </Stack>
  );
}

function TaskRow({ project, activity, task, number, paused, selected, onPick }: {
  project: string; activity: string; task: PathTask; number: number; paused: boolean; selected: boolean; onPick: () => void;
}) {
  const [, setSearch] = useSearchParams();
  const retry = useRetryStep(project, activity);
  const markDone = useMarkDone(project, activity);
  const tasks = useAgentTasks(project);
  const saveTask = useSaveAgentTask(project);
  const { ask } = useAgentPanel();
  const [delegating, setDelegating] = useState(false);
  const [sendingBack, setSendingBack] = useState(false);
  const steps = task.steps ?? [];
  const current = task.current ? steps.find((step) => step.state !== "done" && step.state !== "skipped") : undefined;
  const open = () => setSearch({ note: task.task, from: activity }, { replace: true });
  const stop = (event: { stopPropagation: () => void }) => event.stopPropagation();
  const found = tasks.data?.find((item) => item.name === task.task);
  const finish = () => {
    if (!found) return;
    const { name, ...rest } = found;
    saveTask.mutate({ name, body: { ...rest, status: "done" } }, { onSuccess: () => notifications.show({ message: `${task.title}: fatto.` }) });
  };
  const refining = task.current && (task.status === "created" || task.status === "refinement");
  return (
    <Card withBorder p="xs" onClick={onPick} data-testid="work-task" aria-selected={selected}
      style={{ cursor: "pointer", borderColor: selected ? "var(--mantine-color-blue-6)" : undefined, borderLeftWidth: task.current ? 4 : undefined,
        borderLeftColor: task.current ? "var(--mantine-color-blue-6)" : undefined }}>
      <Stack gap={6}>
        <Group gap={6} wrap="nowrap">
          <Text size="xs" c="dimmed">{number}.</Text>
          <Text size="sm" fw={600} style={{ flex: 1, minWidth: 0 }} truncate>{task.title}</Text>
          <Anchor size="xs" component={Link} to={taskLink(project, task.task, activity)} onClick={stop}>Apri</Anchor>
          <Badge size="xs" variant="light">{typeLabel(task.type)}</Badge>
          {task.repository && <Badge size="xs" variant="outline">{task.repository}</Badge>}
          <TaskStatusBadge status={current?.state === "you" ? "you" : task.status} />
        </Group>
        <Group gap={4}>{steps.map((step) => <StepBadge key={step.key} step={step} />)}</Group>
        <Group gap="xs" onClick={stop}>
          {refining && (
            <>
              <Text size="xs" c="dimmed">In rifinitura: il giro aspetta che il task torni «da fare».</Text>
              <Button size="compact-xs" variant="default" onClick={open}>Apri il task</Button>
            </>
          )}
          {!refining && current && (
            <>
              {current.key === "operation" && current.state === "you" && (
                <>
                  <Button size="compact-xs" onClick={() => found && ask(devRequest(found, task.repository), "operator")}>🤖 Fallo fare a Dev</Button>
                  <Button size="compact-xs" color="green" variant="light" onClick={() => markDone.mutate(task.task)} loading={markDone.isPending}>
                    ✅ Fatto
                  </Button>
                  <Text size="xs" c="dimmed">o fai tu i passi, poi «Fatto».</Text>
                </>
              )}
              {current.key === "delegate" && current.state === "todo" && (paused ? (
                <Button size="compact-xs" onClick={() => setDelegating(true)}>🤖 Delega a mano</Button>
              ) : <Text size="xs" c="dimmed">⏳ Il giro lo delega a breve.</Text>)}
              {(current.key === "copilot_plan" || current.key === "answer") && current.state === "you" && (
                <Button size="compact-xs" onClick={onPick}>💬 {current.key === "answer" ? "Leggi la risposta" : "Rispondi a Copilot"}</Button>
              )}
              {current.key === "answer" && current.state === "you" && (
                <Button size="compact-xs" color="green" variant="light" onClick={finish} loading={saveTask.isPending}>✅ Conferma</Button>
              )}
              {current.key === "final" && current.state === "you" && (
                <>
                  <Button size="compact-xs" color="green" onClick={finish} loading={saveTask.isPending}>✅ Controlla e conferma</Button>
                  <Button size="compact-xs" variant="default" onClick={() => setSendingBack(true)}>↩ Rimanda a Copilot</Button>
                </>
              )}
              {current.key === "delegate" && current.state === "failed" && (
                <>
                  <Button size="compact-xs" variant="light" onClick={() => retry.mutate({ task: task.task, step: current.key })} loading={retry.isPending}>
                    🔁 Riprova
                  </Button>
                  <Button size="compact-xs" variant="default" onClick={() => setDelegating(true)}>🤖 Delega a mano</Button>
                </>
              )}
              {current.state === "failed" && (current.key === "execution" || current.key === "answer") && (
                <Button size="compact-xs" color="red" variant="light" onClick={open}>Apri il task</Button>
              )}
            </>
          )}
        </Group>
        {current?.state === "failed" && current.detail && <Text size="xs" c="red" style={{ whiteSpace: "pre-wrap" }}>{current.detail}</Text>}
        {(retry.error || saveTask.error || markDone.error) && <Text size="xs" c="red">{(retry.error ?? saveTask.error ?? markDone.error)?.message}</Text>}
      </Stack>
      {delegating && <DelegateModal project={project} task={task.task} repository={task.repository} opened onClose={() => setDelegating(false)} />}
      {sendingBack && <SendBackModal project={project} task={task.task} opened onClose={() => setSendingBack(false)} />}
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

// ---------------------------------------------------------------- 4. Chiudi

function Close({ project, activity, path, onBack }: { project: string; activity: Activity; path: ActivityPath; onBack: () => void }) {
  const proposeLearned = useProposeLearned(project, activity.name);
  const close = useCloseActivity(project, activity.name);
  const [learned, setLearned] = useState("");
  const [confirming, setConfirming] = useState(false);
  const openTasks = path.tasks.filter((task) => task.status !== "done" && task.status !== "missing");
  const openItems = activity.items.filter((item) => !item.done);
  const doClose = () => close.mutate(learned, {
    onSuccess: (closed) => {
      setConfirming(false);
      notifications.show({ message: closed.context ? `${activity.title}: chiusa, scritto in context/${closed.context}.` : `${activity.title}: chiusa.` });
      if (closed.index_error) notifications.show({ color: "orange", message: `Indice del contesto non aggiornato: ${closed.index_error}` });
    },
  });
  if (activity.status === "done") {
    return (
      <Stack gap="sm">
        <Alert color="green">Attività chiusa. Quello che hai imparato è in <code>context/imparato.md</code>: resta anche se cancelli l'attività.</Alert>
        <Text size="sm" c="dimmed">«↩ Riapri», in alto, la riporta a Pianifica (in corso). La sezione già scritta resta; alla nuova chiusura se ne aggiunge un'altra.</Text>
      </Stack>
    );
  }
  return (
    <Stack gap="sm">
      <div>
        <Text size="xs" fw={700} c="dimmed" tt="uppercase" mb={4}>Riepilogo</Text>
        <Card withBorder p="xs" data-testid="close-summary">
          <Text size="xs" style={{ whiteSpace: "pre-wrap" }}>{path.summary || (path.tasks.length ? "Ci sono ancora task da fare." : "Nessun task: l'attività non è passata dal giro.")}</Text>
        </Card>
      </div>
      <div>
        <Group justify="space-between" mb={4}>
          <Text size="sm" fw={500}>Cosa ho imparato</Text>
          <Button size="compact-xs" variant="light" loading={proposeLearned.isPending}
            onClick={() => proposeLearned.mutate(undefined, { onSuccess: (draft) => setLearned(draft.points.map((point) => `- ${point}`).join("\n")) })}>
            ✨ Proponi cosa ho imparato
          </Button>
        </Group>
        <Textarea aria-label="Cosa ho imparato" autosize minRows={3} placeholder="- una cosa da ricordare per i lavori futuri, per riga"
          value={learned} onChange={(event) => setLearned(event.currentTarget.value)} />
        <Text size="xs" c="dimmed" mt={4}>
          Alla chiusura va in cima a <code>context/imparato.md</code> (nell'indice del contesto: lo leggono Pianificatore, Refiner e Copilot). Vuoto = non si scrive niente.
          {proposeLearned.data ? ` Proposta: ${eur(proposeLearned.data.cost_eur)}.` : ""}
        </Text>
        {proposeLearned.error && <Alert color="red" p="xs" mt={4}>{proposeLearned.error.message}</Alert>}
      </div>
      {confirming && (
        <Alert color="orange" title="Resta qualcosa aperto">
          <Stack gap={6}>
            {!!openTasks.length && <Text size="sm">Task non fatti: {openTasks.map((task) => task.title).join(", ")}</Text>}
            {!!openItems.length && <Text size="sm">Voci non fatte: {openItems.map((item) => item.text).join(", ")}</Text>}
            <Group gap="xs">
              <Button size="xs" color="orange" onClick={doClose} loading={close.isPending}>Chiudi lo stesso</Button>
              <Button size="xs" variant="default" onClick={() => setConfirming(false)}>No</Button>
            </Group>
          </Stack>
        </Alert>
      )}
      {close.error && <Alert color="red">{close.error.message}</Alert>}
      <Group justify="space-between" pt="sm" style={{ borderTop: "1px solid var(--mantine-color-default-border)" }}>
        <Button variant="default" onClick={onBack}>← Indietro</Button>
        <Button color="green" loading={close.isPending && !confirming}
          onClick={() => (openTasks.length || openItems.length ? setConfirming(true) : doClose())}>✅ Chiudi attività</Button>
      </Group>
    </Stack>
  );
}
