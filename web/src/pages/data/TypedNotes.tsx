import { Alert, Badge, Button, Checkbox, Grid, Group, Loader, Modal, NavLink, SegmentedControl, Stack, Text, TextInput, Textarea } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { type ReactNode, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

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
  { value: "created", label: "Creato", color: "gray" },
  { value: "refinement", label: "In rifinitura", color: "yellow" },
  { value: "todo", label: "Da fare", color: "indigo" },
  { value: "in_progress", label: "In corso", color: "blue" },
  { value: "done", label: "Fatto", color: "green" },
] as const;

/** What the task asks for; it picks Copilot's planning prompt (type_prompts). */
export const TYPES = [
  { value: "refinement", label: "Rifinitura", color: "grape" },
  { value: "development", label: "Sviluppo", color: "teal" },
  { value: "analysis", label: "Analisi", color: "orange" },
] as const;

const ALL = "all";

/** The agent tasks, with the Refiner chatbot on the right (it can be hidden). */
export function AgentTasks({ project }: { project: string }) {
  const [refiner, setRefiner] = useState(true);
  return (
    <Grid gutter="md">
      <Grid.Col span={{ base: 12, lg: refiner ? 8 : 12 }}>
        <Group justify="flex-end" mb="xs">
          <Button size="compact-xs" variant="subtle" onClick={() => setRefiner(!refiner)}>{refiner ? "Nascondi il Refiner" : "🧠 Mostra il Refiner"}</Button>
        </Group>
        <AgentTaskList project={project} />
      </Grid.Col>
      {refiner && <Grid.Col span={{ base: 12, lg: 4 }}><RefinerPanel project={project} /></Grid.Col>}
    </Grid>
  );
}

function AgentTaskList({ project }: { project: string }) {
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
      describe={(task) => {
        const status = STATUS.find((item) => item.value === task.status) ?? STATUS[0];
        const kind = TYPES.find((item) => item.value === task.type) ?? TYPES[1];
        return (
          <Group gap={4} wrap="nowrap">
            <Badge size="xs" variant="outline" color={kind.color}>{kind.label}</Badge>
            <Badge size="xs" variant="light" color={status.color}>{status.label}</Badge>
          </Group>
        );
      }}
      create={(title, done) => save.mutate({
        body: { title, status: "created", type: type === ALL ? "development" : type as AgentTaskBody["type"], objective: "", context: "", criteria: [], constraints: "", references: [] },
      }, done)}
      creating={save.isPending}
      renderEditor={(task) => <AgentTaskEditor key={task.name} project={project} task={task} />}
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
function TypedNotes<T extends Named>({ items, error, newLabel, intro, toolbar, describe, create, creating, renderEditor }: {
  project: string;
  items?: T[];
  error?: string;
  newLabel: string;
  intro: string;
  /** Under «New»: e.g. a filter of the list. */
  toolbar?: ReactNode;
  describe: (item: T) => ReactNode;
  create: (title: string, done: Done) => void;
  creating: boolean;
  renderEditor: (item: T) => ReactNode;
}) {
  const [search, setSearch] = useSearchParams();
  const [adding, setAdding] = useState(false);
  const requested = search.get("note");
  const selected = items?.find((item) => item.name === requested) ?? items?.[0];
  const select = (name: string) => setSearch({ note: name }, { replace: true });
  return (
    <Grid gutter="md">
      <Grid.Col span={{ base: 12, md: 3 }}>
        <Stack gap="xs">
          <Button onClick={() => setAdding(true)}>➕ {newLabel}</Button>
          {toolbar}
          {!items && !error && <Loader size="sm" />}
          {error && <Alert color="red">{error}</Alert>}
          {items && !items.length && <Text size="sm" c="dimmed">Nessuna, per ora.</Text>}
          {items?.map((item) => (
            <NavLink key={item.name} label={item.title} rightSection={describe(item)} active={item.name === selected?.name} onClick={() => select(item.name)} />
          ))}
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

function AgentTaskEditor({ project, task }: { project: string; task: AgentTask }) {
  const save = useSaveAgentTask(project);
  const sessions = useCopilotSessions(project);
  const deleteSessions = useDeleteTaskSessions(project);
  const taskSessions = (sessions.data ?? []).filter((session) => session.task_note === task.name).length;
  const [form, setForm] = useState<AgentTaskBody>(() => fields(task));
  const set = (patch: Partial<AgentTaskBody>) => setForm((current) => ({ ...current, ...patch }));
  const dirty = JSON.stringify(form) !== JSON.stringify(fields(task));
  const [delegating, setDelegating] = useState(false);
  const onSave = () =>
    save.mutate(
      { name: task.name, body: { ...form, criteria: (form.criteria ?? []).filter((item) => item.text.trim()) } },
      { onSuccess: (saved) => { setForm(fields(saved)); notifications.show({ message: `${saved.title} salvato.` }); } },
    );
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
          <Button variant="light" onClick={() => setDelegating(true)} disabled={dirty} title={dirty ? "Salva prima il task: Copilot legge il file" : undefined}>
            🤖 Delega a Copilot
          </Button>
          <DelegateModal project={project} task={task.name} opened={delegating} onClose={() => setDelegating(false)} />
        </>
      }
    >
      <TextInput label="Titolo" value={form.title} onChange={(event) => set({ title: event.currentTarget.value })} />
      <Group align="flex-end" gap="md">
        <div>
          <Text size="sm" fw={500} mb={4}>Stato</Text>
          <SegmentedControl
            aria-label="Stato"
            data={STATUS.map(({ value, label }) => ({ value, label }))}
            value={form.status ?? "created"}
            onChange={(value) => set({ status: value as AgentTaskBody["status"] })}
          />
        </div>
        <div>
          <Text size="sm" fw={500} mb={4}>Tipo</Text>
          <SegmentedControl
            aria-label="Tipo del task"
            data={TYPES.map(({ value, label }) => ({ value, label }))}
            value={form.type ?? "development"}
            onChange={(value) => set({ type: value as AgentTaskBody["type"] })}
          />
        </div>
      </Group>
      {form.status && !["todo", "in_progress", "done"].includes(form.status) && (
        <Text size="xs" c="dimmed">Non ancora pronto: quando è rifinito, mettilo «Da fare». Si può delegare comunque, con un avviso.</Text>
      )}
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
