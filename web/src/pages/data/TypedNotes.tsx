import {
  ActionIcon, Alert, Anchor, Badge, Button, Checkbox, Grid, Group, Loader, Menu, Modal, NavLink, SegmentedControl, Select, Stack, Stepper, Text,
  TextInput, Textarea, UnstyledButton,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { type ReactNode, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { useCopilotSessions, useDeleteTaskSessions } from "../../api/copilot";
import {
  type Activity, type ActivityBody, type AgentTask, type AgentTaskBody, useActivities, useAgentTasks, useDeleteNote, useSaveActivity, useSaveAgentTask,
} from "../../api/projectData";
import { ConfirmButton } from "../../components/ConfirmButton";
import { DelegateModal } from "../copilot/DelegateModal";
import { SendBackModal } from "../copilot/SendBackModal";
import { ChecklistEditor } from "./ChecklistEditor";
import { ReferencesSection } from "./ReferencesSection";
import { RefinerPanel } from "./RefinerPanel";
import { TodayPanel } from "./TodayPanel";

/** The typed notes of the Dati tab: activities and agent tasks. On disk they
 * are notes (``attivita-<title>.md``, ``agent-task-<title>.md``) written with
 * their template; here each one is a form of its fields, with the code and
 * context references it links (ReferencesSection). */

/** In order: created and refinement come before todo, ready to delegate;
 * a development goes through «to verify» (the user checks Copilot's changes). */
export const STATUS = [
  { value: "created", label: "Creato", group: "Creati", color: "gray" },
  { value: "refinement", label: "In rifinitura", group: "In rifinitura", color: "yellow" },
  { value: "todo", label: "Da fare", group: "Da fare", color: "indigo" },
  { value: "in_progress", label: "In corso", group: "In corso", color: "blue" },
  { value: "to_verify", label: "Da verificare", group: "Da verificare", color: "orange" },
  { value: "done", label: "Fatto", group: "Fatti", color: "green" },
] as const;

/** What the task asks for; it picks Copilot's planning prompt (type_prompts).
 * Only a development changes the code: the others stay in planning and
 * Copilot's answer is saved as a note (``planOnly``). */
export const TYPES = [
  { value: "development", label: "Sviluppo", color: "teal" },
  { value: "analysis", label: "Analisi", color: "orange" },
  { value: "confluence", label: "Doc Confluence", color: "blue" },
  { value: "jira", label: "Task Jira", color: "grape" },
] as const;

export const isPlanOnly = (type?: string) => (type ?? "development") !== "development";

const ALL = "all";

/** The statuses in which the task is the Refiner's: it sits next to them. */
const REFINABLE: readonly string[] = ["created", "refinement"];
type Draft = { text: string; id: number };

/** The agent tasks grouped by status, with the Refiner on the right while the
 * open task is created or in refinement (it can be hidden). */
export function AgentTasks({ project }: { project: string }) {
  const [hidden, setHidden] = useState(false);
  const [open, setOpen] = useState<AgentTask>();
  const [draft, setDraft] = useState<Draft>();
  const refinable = !!open && REFINABLE.includes(open.status ?? "created");
  const refiner = refinable && !hidden;
  const refine = () => {
    setHidden(false);
    setDraft((current) => ({ text: "Rifinisci questo task.", id: (current?.id ?? 0) + 1 }));
  };
  return (
    <Grid gutter="md">
      <Grid.Col span={{ base: 12, lg: refiner ? 8 : 12 }}>
        {refinable && (
          <Group justify="flex-end" mb="xs">
            <Button size="compact-xs" variant="subtle" onClick={() => setHidden(!hidden)}>{hidden ? "🧠 Mostra il Refiner" : "Nascondi il Refiner"}</Button>
          </Group>
        )}
        <AgentTaskList project={project} onSelected={setOpen} onRefine={refine} />
      </Grid.Col>
      {refiner && <Grid.Col span={{ base: 12, lg: 4 }}><RefinerPanel project={project} openTask={open} draft={draft} /></Grid.Col>}
    </Grid>
  );
}

function AgentTaskList({ project, onSelected, onRefine }: {
  project: string; onSelected: (task: AgentTask | undefined) => void; onRefine: () => void;
}) {
  const tasks = useAgentTasks(project);
  const save = useSaveAgentTask(project);
  const [type, setType] = useState<string>(ALL);
  return (
    <TypedNotes
      project={project}
      items={tasks.data?.filter((task) => type === ALL || task.type === type)}
      error={tasks.error?.message}
      newLabel="Nuovo task"
      intro="Un agent task è un compito per un agente: obiettivo, contesto, criteri di accettazione e vincoli. È una nota agent-task-<titolo>.md."
      toolbar={
        <SegmentedControl
          size="xs" fullWidth aria-label="Filtra per tipo"
          data={[{ value: ALL, label: "Tutti" }, ...TYPES.map(({ value, label }) => ({ value, label }))]}
          value={type}
          onChange={setType}
        />
      }
      groups={STATUS.map((status) => ({ key: status.value, label: status.group, color: status.color, collapsed: status.value === "done" }))}
      groupOf={(task) => task.status ?? "created"}
      describe={(task) => {
        const kind = TYPES.find((item) => item.value === task.type) ?? TYPES[0];
        return <Badge size="xs" variant="outline" color={kind.color}>{kind.label}</Badge>;
      }}
      create={(title, done) => save.mutate({
        body: { title, status: "created", type: type === ALL ? "development" : type as AgentTaskBody["type"], objective: "", context: "", criteria: [], constraints: "", references: [] },
      }, done)}
      creating={save.isPending}
      onSelected={onSelected}
      renderEditor={(task) => <AgentTaskEditor key={task.name} project={project} task={task} onRefine={onRefine} />}
    />
  );
}

/** In order; the editor suggests «done» when every item is. */
export const ACTIVITY_STATUS = [
  { value: "todo", label: "Da fare", color: "gray" },
  { value: "in_progress", label: "In corso", color: "blue" },
  { value: "done", label: "Fatta", color: "green" },
] as const;

export function Activities({ project }: { project: string }) {
  const activities = useActivities(project);
  const save = useSaveActivity(project);
  return (
    <>
      <TodayPanel project={project} />
      <TypedNotes
        project={project}
        items={activities.data}
        error={activities.error?.message}
        newLabel="Nuova attività"
        intro="Un'attività è una cosa da fare: una descrizione, la sua todo list (priorità e scadenza facoltative per voce) e gli agent task che ne nascono. È una nota attivita-<titolo>.md."
        describe={(activity) => {
          const status = ACTIVITY_STATUS.find((item) => item.value === activity.status) ?? ACTIVITY_STATUS[0];
          const done = activity.items.filter((item) => item.done).length;
          return (
            <Group gap={4} wrap="nowrap">
              {!!activity.items.length && <Text size="xs" c="dimmed">{done}/{activity.items.length}</Text>}
              <Badge size="xs" variant="light" color={status.color}>{status.label}</Badge>
            </Group>
          );
        }}
        create={(title, done) => save.mutate({ body: { title, status: "todo", description: "", items: [], agent_tasks: [], references: [], learned: "" } }, done)}
        creating={save.isPending}
        renderEditor={(activity) => <ActivityEditor key={activity.name} project={project} activity={activity} />}
      />
    </>
  );
}

// ------------------------------------------------------------------- layout

type Named = { name: string; title: string };
type Done = { onSuccess: (created: Named) => void; onError: (error: Error) => void };

/** The notes of one type on the left (``?note=`` is the open one), its form on the right. */
/** A section of the list (by status, for the agent tasks). */
type Group = { key: string; label: string; color: string; collapsed?: boolean };

function TypedNotes<T extends Named>({ items, error, newLabel, intro, toolbar, groups, groupOf, describe, create, creating, onSelected, renderEditor }: {
  project: string;
  items?: T[];
  error?: string;
  newLabel: string;
  intro: string;
  /** Under «New»: e.g. a filter of the list. */
  toolbar?: ReactNode;
  /** Sections of the list, in order, each with its count (``collapsed``: closed at first); ``groupOf`` puts an item in one. */
  groups?: Group[];
  groupOf?: (item: T) => string;
  describe: (item: T) => ReactNode;
  create: (title: string, done: Done) => void;
  creating: boolean;
  /** The open one (or none), whenever it changes. */
  onSelected?: (item: T | undefined) => void;
  renderEditor: (item: T) => ReactNode;
}) {
  const [search, setSearch] = useSearchParams();
  const [adding, setAdding] = useState(false);
  const requested = search.get("note");
  const selected = items?.find((item) => item.name === requested) ?? items?.[0];
  const select = (name: string) => setSearch({ note: name }, { replace: true });
  useEffect(() => onSelected?.(selected), [selected && JSON.stringify(selected)]); // eslint-disable-line react-hooks/exhaustive-deps
  const [toggled, setToggled] = useState<Record<string, boolean>>({});
  const link = (item: T) => (
    <NavLink key={item.name} label={item.title} rightSection={describe(item)} active={item.name === selected?.name} onClick={() => select(item.name)} />
  );
  return (
    <Grid gutter="md">
      <Grid.Col span={{ base: 12, md: 3 }}>
        <Stack gap="xs">
          <Button onClick={() => setAdding(true)}>➕ {newLabel}</Button>
          {toolbar}
          {!items && !error && <Loader size="sm" />}
          {error && <Alert color="red">{error}</Alert>}
          {items && !items.length && <Text size="sm" c="dimmed">Nessuna, per ora.</Text>}
          {groups && groupOf && items?.length ? groups.map((group) => {
            const members = items.filter((item) => groupOf(item) === group.key);
            const open = toggled[group.key] ?? (!group.collapsed || members.some((item) => item.name === selected?.name));
            return (
              <Stack key={group.key} gap={0}>
                <UnstyledButton
                  aria-expanded={open}
                  onClick={() => setToggled({ ...toggled, [group.key]: !open })}
                  disabled={!members.length}
                >
                  <Group gap={6} wrap="nowrap">
                    <Text size="xs" c="dimmed" w={10}>{members.length ? (open ? "▾" : "▸") : ""}</Text>
                    <Badge size="sm" variant="light" color={group.color}>{group.label}</Badge>
                    <Text size="xs" c="dimmed">{members.length}</Text>
                  </Group>
                </UnstyledButton>
                {open && members.map(link)}
              </Stack>
            );
          }) : items?.map(link)}
        </Stack>
      </Grid.Col>
      <Grid.Col span={{ base: 12, md: 9 }}>{selected ? renderEditor(selected) : <Text c="dimmed">{intro}</Text>}</Grid.Col>
      <TitleModal
        title={newLabel}
        opened={adding}
        loading={creating}
        onClose={() => setAdding(false)}
        onCreate={(title, onError) => create(title, { onSuccess: (created) => { setAdding(false); select(created.name); }, onError })}
      />
    </Grid>
  );
}

function TitleModal({ title, opened, loading, onClose, onCreate }: {
  title: string; opened: boolean; loading: boolean; onClose: () => void; onCreate: (title: string, onError: (error: Error) => void) => void;
}) {
  const [value, setValue] = useState("");
  const [error, setError] = useState<string>();
  useEffect(() => {
    if (opened) {
      setValue("");
      setError(undefined);
    }
  }, [opened]);
  const submit = () => (value.trim() ? onCreate(value.trim(), (exc) => setError(exc.message)) : setError("Il titolo è obbligatorio."));
  return (
    <Modal opened={opened} onClose={onClose} title={title}>
      <Stack>
        <TextInput label="Titolo" data-autofocus value={value} error={error} onChange={(event) => setValue(event.currentTarget.value)} onKeyDown={(event) => event.key === "Enter" && submit()} />
        <Group><Button onClick={submit} loading={loading}>Crea</Button></Group>
      </Stack>
    </Modal>
  );
}

/** Save (Ctrl+S too) and delete, with the unsaved marker; shared by the two editors. */
function EditorShell({ project, name, dirty, valid, saving, error, onSave, actions, alsoDelete, children }: {
  project: string; name: string; dirty: boolean; valid: boolean; saving: boolean; error?: string; onSave: () => void;
  /** More buttons next to «Salva». */
  actions?: ReactNode;
  /** Something to delete with the note, offered as a checkbox (checked) in the confirmation. */
  alsoDelete?: { label: string; run: () => Promise<unknown>; error?: string };
  children: ReactNode;
}) {
  const remove = useDeleteNote(project);
  const [withExtra, setWithExtra] = useState(true);
  const [extraPending, setExtraPending] = useState(false);
  const onDelete = async () => {
    if (alsoDelete && withExtra) {
      setExtraPending(true);
      try {
        await alsoDelete.run();
      } catch {
        return; // its error shows in the popover; the note stays
      } finally {
        setExtraPending(false);
      }
    }
    remove.mutate(name);
  };
  return (
    <Stack
      gap="sm"
      onKeyDown={(event) => {
        if (event.key === "s" && (event.ctrlKey || event.metaKey)) {
          event.preventDefault();
          if (dirty && valid) onSave();
        }
      }}
    >
      <Text size="xs" c="dimmed"><code>{name}</code>{dirty && <Text span c="orange"> · modifiche non salvate</Text>}</Text>
      {children}
      {error && <Alert color="red">{error}</Alert>}
      <Group>
        <Button onClick={onSave} loading={saving} disabled={!dirty || !valid}>Salva</Button>
        <Text size="xs" c="dimmed">Ctrl+S salva</Text>
        {actions}
        <ConfirmButton
          ml="auto"
          message={
            <Stack gap="xs">
              <Text size="sm">Eliminare {name}?</Text>
              {alsoDelete && <Checkbox size="xs" label={alsoDelete.label} checked={withExtra} onChange={(event) => setWithExtra(event.currentTarget.checked)} />}
            </Stack>
          }
          loading={remove.isPending || extraPending}
          error={alsoDelete?.error ?? remove.error?.message}
          onConfirm={onDelete}
        >
          Elimina
        </ConfirmButton>
      </Group>
    </Stack>
  );
}

const fields = <T extends object>(item: T & { name: string }) => {
  const { name: _name, ...body } = item;
  return body;
};

// ------------------------------------------------------------------ editors

/** «Nasce da»: the activities that list this agent task (a click opens one); nothing when none. */
function BornFrom({ project, task }: { project: string; task: string }) {
  const activities = useActivities(project);
  const [, setSearch] = useSearchParams();
  const parents = (activities.data ?? []).filter((activity) => activity.agent_tasks.includes(task));
  if (!parents.length) return null;
  return (
    <Text size="xs">
      📋 Nasce da:{" "}
      {parents.map((activity, index) => (
        <span key={activity.name}>
          {index > 0 && ", "}
          <Anchor size="xs" component="button" type="button" onClick={() => setSearch({ note: activity.name }, { replace: true })}>{activity.title}</Anchor>
        </span>
      ))}
    </Text>
  );
}

/** Where the task is in its flow, and the one action that moves it on:
 * created → «Rifinisci con il Refiner» (in refinement at once, no LLM), in
 * refinement → «Segna da fare», todo → «Delega a Copilot», to verify →
 * «Conferma» or «Rimanda a Copilot»; in progress is Copilot's. Only a
 * development has «to verify» in its path. «Cambia stato» is for any other
 * move, by hand. */
function StatusPath({ project, status, planOnly, missing, busy, dirty, onStatus, onRefine, onDelegate, onSendBack }: {
  project: string; status: string;
  /** Not a development: Copilot never changes the code, no «to verify». */
  planOnly: boolean;
  /** What a refined task should have and this one lacks. */
  missing: string[];
  busy: boolean; dirty: boolean;
  onStatus: (status: AgentTaskBody["status"]) => void; onRefine: () => void; onDelegate: () => void; onSendBack: () => void;
}) {
  const path = STATUS.filter((item) => !planOnly || item.value !== "to_verify" || status === "to_verify");
  const index = Math.max(0, path.findIndex((item) => item.value === status));
  return (
    <Stack gap="xs">
      <Stepper active={index} size="xs" iconSize={22} allowNextStepsSelect={false} aria-label="Stato del task">
        {path.map((item, position) => (
          <Stepper.Step key={item.value} label={item.label} color={position <= index ? path[index].color : undefined} />
        ))}
      </Stepper>
      <Group gap="xs">
        {status === "created" && (
          <>
            <Button size="xs" loading={busy} onClick={() => { onStatus("refinement"); onRefine(); }}>🧠 Rifinisci con il Refiner</Button>
            <Text size="xs" c="dimmed">Il task passa «in rifinitura»: il Refiner ti fa domande e scrive i campi con te.</Text>
          </>
        )}
        {status === "refinement" && (
          <>
            <Button size="xs" onClick={() => onStatus("todo")} loading={busy}>✅ Segna da fare</Button>
            <Text size="xs" c={missing.length ? "orange" : "dimmed"}>
              {missing.length ? `Manca ancora ${missing.join(" e ")}.` : "Quando è rifinito: pronto da delegare."}
            </Text>
          </>
        )}
        {status === "todo" && (
          <Button size="xs" onClick={onDelegate} disabled={dirty} title={dirty ? "Salva prima il task: Copilot legge il file" : undefined}>
            🤖 Delega a Copilot
          </Button>
        )}
        {status === "in_progress" && (
          <Text size="xs">
            Copilot ci sta lavorando: <Anchor component={Link} to={`/projects/${encodeURIComponent(project)}/copilot`}>apri Copilot</Anchor>
            {planOnly && <>; quando la risposta va bene, «Salva come nota»</>}.
          </Text>
        )}
        {status === "to_verify" && (
          <>
            <Button size="xs" color="green" onClick={() => onStatus("done")} loading={busy}>✅ Conferma</Button>
            <Button size="xs" variant="light" onClick={onSendBack}>↩️ Rimanda a Copilot</Button>
            <Text size="xs" c="dimmed">Controlla le modifiche di Copilot: commit e push li fai tu.</Text>
          </>
        )}
        {status === "done" && <Text size="xs" c="dimmed">Fatto.</Text>}
        <Menu position="bottom-end">
          <Menu.Target>
            <Button size="xs" variant="subtle" ml="auto" loading={busy && status !== "refinement"}>Cambia stato ▾</Button>
          </Menu.Target>
          <Menu.Dropdown>
            {path.filter((item) => item.value !== status).map((item) => (
              <Menu.Item key={item.value} onClick={() => onStatus(item.value)}>
                <Badge size="xs" variant="light" color={item.color}>{item.label}</Badge>
              </Menu.Item>
            ))}
          </Menu.Dropdown>
        </Menu>
      </Group>
    </Stack>
  );
}

function AgentTaskEditor({ project, task, onRefine }: { project: string; task: AgentTask; onRefine: () => void }) {
  const save = useSaveAgentTask(project);
  const sessions = useCopilotSessions(project);
  const deleteSessions = useDeleteTaskSessions(project);
  const taskSessions = (sessions.data ?? []).filter((session) => session.task_note === task.name).length;
  const [form, setForm] = useState<AgentTaskBody>(() => fields(task));
  /** The task as the form was loaded: what «dirty» compares with. */
  const [base, setBase] = useState<AgentTaskBody>(() => fields(task));
  const set = (patch: Partial<AgentTaskBody>) => setForm((current) => ({ ...current, ...patch }));
  const dirty = JSON.stringify(form) !== JSON.stringify(base);
  const latest = JSON.stringify(fields(task));
  const reload = () => { setForm(fields(task)); setBase(fields(task)); };
  const outdated = latest !== JSON.stringify(base); // changed elsewhere (e.g. by the Refiner)
  useEffect(() => { if (outdated && !dirty) reload(); }, [latest]); // eslint-disable-line react-hooks/exhaustive-deps
  const [delegating, setDelegating] = useState(false);
  const [sendingBack, setSendingBack] = useState(false);
  const write = (body: AgentTaskBody, message: (saved: AgentTask) => string) =>
    save.mutate(
      { name: task.name, body: { ...body, criteria: (body.criteria ?? []).filter((item) => item.text.trim()) } },
      { onSuccess: (saved) => { setForm(fields(saved)); setBase(fields(saved)); notifications.show({ message: message(saved) }); } },
    );
  const onSave = () => write(form, (saved) => `${saved.title} salvato.`);
  /** A move along the flow is saved at once, with what is in the form. */
  const moveTo = (status: AgentTaskBody["status"]) =>
    write({ ...form, status }, (saved) => `${saved.title}: ${STATUS.find((item) => item.value === saved.status)?.label.toLowerCase()}.`);
  const missing = [
    !(form.objective ?? "").trim() && "l'obiettivo",
    !(form.criteria ?? []).some((item) => item.text.trim()) && "i criteri di accettazione",
  ].filter((item): item is string => !!item);
  return (
    <EditorShell
      project={project} name={task.name} dirty={dirty} valid={!!form.title.trim()} saving={save.isPending} error={save.error?.message} onSave={onSave}
      alsoDelete={taskSessions ? {
        label: `Elimina anche ${taskSessions === 1 ? "la sessione Copilot" : `le ${taskSessions} sessioni Copilot`} di questo task (l'uso resta in Observability)`,
        run: () => deleteSessions.mutateAsync(task.name),
        error: deleteSessions.error?.message,
      } : undefined}
      actions={
        <>
          <DelegateModal project={project} task={task.name} opened={delegating} onClose={() => setDelegating(false)} />
          <SendBackModal project={project} task={task.name} opened={sendingBack} onClose={() => setSendingBack(false)} />
        </>
      }
    >
      {outdated && dirty && (
        <Alert color="orange">
          <Group justify="space-between" gap="xs">
            <Text size="sm">Il task è cambiato mentre lo modificavi (forse il Refiner): salvando sovrascrivi quelle modifiche.</Text>
            <Button size="compact-xs" variant="light" color="orange" onClick={reload}>Ricarica (perdi le tue)</Button>
          </Group>
        </Alert>
      )}
      <StatusPath
        project={project} status={form.status ?? "created"} planOnly={isPlanOnly(form.type)} missing={missing} busy={save.isPending} dirty={dirty}
        onStatus={moveTo} onRefine={onRefine} onDelegate={() => setDelegating(true)} onSendBack={() => setSendingBack(true)}
      />
      <BornFrom project={project} task={task.name} />
      <TextInput label="Titolo" value={form.title} onChange={(event) => set({ title: event.currentTarget.value })} />
      <div>
        <Text size="sm" fw={500} mb={4}>Tipo</Text>
        <SegmentedControl
          aria-label="Tipo del task"
          data={TYPES.map(({ value, label }) => ({ value, label }))}
          value={form.type ?? "development"}
          onChange={(value) => set({ type: value as AgentTaskBody["type"] })}
        />
      </div>
      <Textarea label="Obiettivo" description="Cosa deve ottenere l'agente." autosize minRows={2} value={form.objective ?? ""} onChange={(event) => set({ objective: event.currentTarget.value })} />
      <Textarea label="Contesto" description="Repository, file, decisioni già prese." autosize minRows={2} value={form.context ?? ""} onChange={(event) => set({ context: event.currentTarget.value })} />
      <div>
        <Text size="sm" fw={500} mb={4}>Criteri di accettazione</Text>
        <ChecklistEditor items={form.criteria ?? []} onChange={(criteria) => set({ criteria })} addLabel="Criterio" placeholder="es. I test passano" />
      </div>
      <Textarea label="Vincoli" description="Cosa non deve fare o toccare." autosize minRows={2} value={form.constraints ?? ""} onChange={(event) => set({ constraints: event.currentTarget.value })} />
      <ReferencesSection project={project} value={form.references ?? []} onChange={(references) => set({ references })} />
    </EditorShell>
  );
}

function ActivityEditor({ project, activity }: { project: string; activity: Activity }) {
  const save = useSaveActivity(project);
  const [form, setForm] = useState<ActivityBody>(() => fields(activity));
  const [base, setBase] = useState<ActivityBody>(() => fields(activity));
  const set = (patch: Partial<ActivityBody>) => setForm((current) => ({ ...current, ...patch }));
  const dirty = JSON.stringify(form) !== JSON.stringify(base);
  const latest = JSON.stringify(fields(activity));
  useEffect(() => { // changed elsewhere (e.g. by the secretary): reloaded when nothing is unsaved
    if (latest !== JSON.stringify(base) && !dirty) { setForm(fields(activity)); setBase(fields(activity)); }
  }, [latest]); // eslint-disable-line react-hooks/exhaustive-deps
  const items = form.items ?? [];
  const done = items.filter((item) => item.done).length;
  const write = (body: ActivityBody, message: string) =>
    save.mutate(
      { name: activity.name, body: { ...body, items: (body.items ?? []).filter((item) => item.text.trim()) } },
      { onSuccess: (saved) => { setForm(fields(saved)); setBase(fields(saved)); notifications.show({ message }); } },
    );
  return (
    <EditorShell
      project={project} name={activity.name} dirty={dirty} valid={!!form.title.trim()} saving={save.isPending} error={save.error?.message}
      onSave={() => write(form, `${form.title} salvata.`)}
    >
      <TextInput label="Titolo" value={form.title} onChange={(event) => set({ title: event.currentTarget.value })} />
      <Group align="flex-end" gap="sm">
        <div>
          <Text size="sm" fw={500} mb={4}>Stato</Text>
          <SegmentedControl
            aria-label="Stato dell'attività"
            data={ACTIVITY_STATUS.map(({ value, label }) => ({ value, label }))}
            value={form.status ?? "todo"}
            onChange={(value) => set({ status: value as ActivityBody["status"] })}
          />
        </div>
        {!!items.length && done === items.length && form.status !== "done" && (
          <Button size="xs" variant="light" color="green" loading={save.isPending}
            onClick={() => write({ ...form, status: "done" }, form.learned?.trim() ? `${form.title}: fatta, «Imparato» nel contesto.` : `${form.title}: fatta. Scrivi «Imparato» se c'è una lezione da ricordare.`)}>
            ✅ Tutte le voci sono fatte: segna fatta
          </Button>
        )}
      </Group>
      <Textarea label="Descrizione" description="Di cosa si tratta, perché, per quando." autosize minRows={2} value={form.description ?? ""}
        onChange={(event) => set({ description: event.currentTarget.value })} />
      <div>
        <Text size="sm" fw={500} mb={4}>Todo <Text span size="xs" c="dimmed">· {done} di {items.length} fatte</Text></Text>
        <ChecklistEditor items={items} onChange={(next) => set({ items: next })} withDetails addLabel="Voce" />
      </div>
      <Textarea
        label="Imparato" autosize minRows={2}
        description="Cosa hai imparato: quando l'attività è fatta entra nel contesto del progetto, che il Refiner e Copilot consultano."
        value={form.learned ?? ""} onChange={(event) => set({ learned: event.currentTarget.value })}
      />
      <LinkedAgentTasks
        project={project}
        value={form.agent_tasks ?? []}
        onChange={(agent_tasks) => set({ agent_tasks })}
        onCreated={(name) => write({ ...form, agent_tasks: [...(form.agent_tasks ?? []), name] }, "Agent task creato e collegato.")}
      />
      <ReferencesSection project={project} value={form.references ?? []} onChange={(references) => set({ references })} />
    </EditorShell>
  );
}

/** The agent tasks born from an activity: each with its status (a click opens
 * it), unlink, link an existing one, or create a new one already linked
 * (``onCreated``: the activity is saved at once, so the task is not left alone). */
function LinkedAgentTasks({ project, value, onChange, onCreated }: {
  project: string; value: string[]; onChange: (names: string[]) => void; onCreated: (name: string) => void;
}) {
  const tasks = useAgentTasks(project);
  const save = useSaveAgentTask(project);
  const [adding, setAdding] = useState(false);
  const [, setSearch] = useSearchParams();
  const byName = new Map((tasks.data ?? []).map((task) => [task.name, task]));
  const others = (tasks.data ?? []).filter((task) => !value.includes(task.name));
  return (
    <Stack gap="xs">
      <Group justify="space-between">
        <Text size="sm" fw={500}>🤖 Agent task</Text>
        <Button size="xs" variant="light" onClick={() => setAdding(true)}>➕ Nuovo agent task</Button>
      </Group>
      {!value.length && <Text size="xs" c="dimmed">Nessun agent task nato da questa attività: creane uno o collega uno esistente.</Text>}
      {value.map((name) => {
        const task = byName.get(name);
        const status = STATUS.find((item) => item.value === task?.status) ?? STATUS[0];
        return (
          <Group key={name} justify="space-between" wrap="nowrap">
            {task ? (
              <Anchor size="sm" component="button" type="button" onClick={() => setSearch({ note: name }, { replace: true })}>{task.title}</Anchor>
            ) : <Text size="sm" c="orange"><code>{name}</code> · non trovato</Text>}
            <Group gap={4} wrap="nowrap">
              {task && <Badge size="xs" variant="light" color={status.color}>{status.label}</Badge>}
              <ActionIcon variant="subtle" color="gray" aria-label={`Scollega ${task?.title ?? name}`} onClick={() => onChange(value.filter((item) => item !== name))}>✕</ActionIcon>
            </Group>
          </Group>
        );
      })}
      {others.length > 0 && (
        <Select
          size="xs"
          placeholder="Collega un agent task esistente…"
          searchable
          data={others.map((task) => ({ value: task.name, label: task.title }))}
          value={null}
          onChange={(name) => name && onChange([...value, name])}
        />
      )}
      <TitleModal
        title="Nuovo agent task"
        opened={adding}
        loading={save.isPending}
        onClose={() => setAdding(false)}
        onCreate={(title, onError) => save.mutate(
          { body: { title, status: "created", type: "development", objective: "", context: "", criteria: [], constraints: "", references: [] } },
          { onSuccess: (created) => { setAdding(false); onCreated(created.name); }, onError },
        )}
      />
    </Stack>
  );
}
