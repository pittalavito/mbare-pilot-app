import {
  Alert, Anchor, Badge, Button, Checkbox, Grid, Group, Loader, Menu, Modal, NavLink, SegmentedControl, Stack, Stepper, Text, TextInput, Textarea, UnstyledButton,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { type ReactNode, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { useCopilotSessions, useDeleteTaskSessions } from "../../api/copilot";
import {
  type AgentTask, type AgentTaskBody, type TodoList, type TodoListBody, useAgentTasks, useDeleteNote, useSaveAgentTask, useSaveTodoList, useTodoLists,
} from "../../api/projectData";
import { ConfirmButton } from "../../components/ConfirmButton";
import { DelegateModal } from "../copilot/DelegateModal";
import { ChecklistEditor } from "./ChecklistEditor";
import { ReferencesSection } from "./ReferencesSection";
import { RefinerPanel } from "./RefinerPanel";

/** The typed notes of the Dati tab: agent tasks and todo lists. On disk they
 * are notes (``agent-task-<title>.md``, ``todo-list-<title>.md``) written with
 * their template; here each one is a form of its fields, with the code and
 * context references it links (ReferencesSection). */

/** In order: created and refinement come before todo, ready to delegate. */
export const STATUS = [
  { value: "created", label: "Creato", group: "Creati", color: "gray" },
  { value: "refinement", label: "In rifinitura", group: "In rifinitura", color: "yellow" },
  { value: "todo", label: "Da fare", group: "Da fare", color: "indigo" },
  { value: "in_progress", label: "In corso", group: "In corso", color: "blue" },
  { value: "done", label: "Fatto", group: "Fatti", color: "green" },
] as const;

/** What the task asks for; it picks Copilot's planning prompt (type_prompts). */
export const TYPES = [
  { value: "refinement", label: "Rifinitura", color: "grape" },
  { value: "development", label: "Sviluppo", color: "teal" },
  { value: "analysis", label: "Analisi", color: "orange" },
] as const;

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
        const kind = TYPES.find((item) => item.value === task.type) ?? TYPES[1];
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

export function TodoLists({ project }: { project: string }) {
  const lists = useTodoLists(project);
  const save = useSaveTodoList(project);
  return (
    <TypedNotes
      project={project}
      items={lists.data}
      error={lists.error?.message}
      newLabel="Nuova todo list"
      intro="Una todo list è una checklist, con priorità e scadenza facoltative per voce. È una nota todo-list-<titolo>.md."
      describe={(todo) => {
        const done = todo.items.filter((item) => item.done).length;
        return <Badge size="xs" variant="light" color={todo.items.length && done === todo.items.length ? "green" : "gray"}>{done}/{todo.items.length}</Badge>;
      }}
      create={(title, done) => save.mutate({ body: { title, items: [], references: [] } }, done)}
      creating={save.isPending}
      renderEditor={(todo) => <TodoListEditor key={todo.name} project={project} todo={todo} />}
    />
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

/** Where the task is in its flow, and the one action that moves it on:
 * created → «Rifinisci con il Refiner», in refinement → «Segna da fare», todo →
 * «Delega a Copilot»; in progress and done are Copilot's. «Cambia stato» is for
 * any other move, by hand. */
function StatusPath({ project, status, missing, busy, dirty, onStatus, onRefine, onDelegate }: {
  project: string; status: string;
  /** What a refined task should have and this one lacks. */
  missing: string[];
  busy: boolean; dirty: boolean;
  onStatus: (status: AgentTaskBody["status"]) => void; onRefine: () => void; onDelegate: () => void;
}) {
  const index = Math.max(0, STATUS.findIndex((item) => item.value === status));
  return (
    <Stack gap="xs">
      <Stepper active={index} size="xs" iconSize={22} allowNextStepsSelect={false} aria-label="Stato del task">
        {STATUS.map((item, position) => (
          <Stepper.Step key={item.value} label={item.label} color={position <= index ? STATUS[index].color : undefined} />
        ))}
      </Stepper>
      <Group gap="xs">
        {status === "created" && (
          <>
            <Button size="xs" onClick={onRefine}>🧠 Rifinisci con il Refiner</Button>
            <Text size="xs" c="dimmed">Il Refiner lo prende, ti fa domande e scrive i campi con te.</Text>
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
            Copilot ci sta lavorando: <Anchor component={Link} to={`/projects/${encodeURIComponent(project)}/copilot`}>apri Copilot</Anchor>.
          </Text>
        )}
        {status === "done" && <Text size="xs" c="dimmed">Fatto.</Text>}
        <Menu position="bottom-end">
          <Menu.Target>
            <Button size="xs" variant="subtle" ml="auto" loading={busy && status !== "refinement"}>Cambia stato ▾</Button>
          </Menu.Target>
          <Menu.Dropdown>
            {STATUS.filter((item) => item.value !== status).map((item) => (
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
      actions={<DelegateModal project={project} task={task.name} opened={delegating} onClose={() => setDelegating(false)} />}
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
        project={project} status={form.status ?? "created"} missing={missing} busy={save.isPending} dirty={dirty}
        onStatus={moveTo} onRefine={onRefine} onDelegate={() => setDelegating(true)}
      />
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

function TodoListEditor({ project, todo }: { project: string; todo: TodoList }) {
  const save = useSaveTodoList(project);
  const [form, setForm] = useState<TodoListBody>(() => fields(todo));
  const dirty = JSON.stringify(form) !== JSON.stringify(fields(todo));
  const items = form.items ?? [];
  const done = items.filter((item) => item.done).length;
  const onSave = () =>
    save.mutate(
      { name: todo.name, body: { ...form, items: items.filter((item) => item.text.trim()) } },
      { onSuccess: (saved) => { setForm(fields(saved)); notifications.show({ message: `${saved.title} salvata.` }); } },
    );
  return (
    <EditorShell project={project} name={todo.name} dirty={dirty} valid={!!form.title.trim()} saving={save.isPending} error={save.error?.message} onSave={onSave}>
      <TextInput label="Titolo" value={form.title} onChange={(event) => setForm({ ...form, title: event.currentTarget.value })} />
      <Text size="sm" c="dimmed">{done} di {items.length} fatte</Text>
      <ChecklistEditor items={items} onChange={(next) => setForm({ ...form, items: next })} withDetails addLabel="Voce" />
      <ReferencesSection project={project} value={form.references ?? []} onChange={(references) => setForm((current) => ({ ...current, references }))} />
    </EditorShell>
  );
}
