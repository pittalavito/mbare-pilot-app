import { Alert, Badge, Button, Grid, Group, Loader, Modal, NavLink, SegmentedControl, Stack, Text, TextInput, Textarea } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { type ReactNode, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import {
  type AgentTask, type AgentTaskBody, type TodoList, type TodoListBody, useAgentTasks, useDeleteNote, useSaveAgentTask, useSaveTodoList, useTodoLists,
} from "../../api/projectData";
import { ConfirmButton } from "../../components/ConfirmButton";
import { ChecklistEditor } from "./ChecklistEditor";

/** The typed notes of the Dati tab: agent tasks and todo lists. On disk they
 * are notes (``agent-task-<title>.md``, ``todo-list-<title>.md``) written with
 * their template; here each one is a form of its fields. */

const STATUS = [
  { value: "todo", label: "Da fare", color: "gray" },
  { value: "in_progress", label: "In corso", color: "blue" },
  { value: "done", label: "Fatto", color: "green" },
] as const;

export function AgentTasks({ project }: { project: string }) {
  const tasks = useAgentTasks(project);
  const save = useSaveAgentTask(project);
  return (
    <TypedNotes
      project={project}
      items={tasks.data}
      error={tasks.error?.message}
      newLabel="Nuovo task"
      intro="Un agent task è un compito per un agente: obiettivo, contesto, criteri di accettazione e vincoli. È una nota agent-task-<titolo>.md."
      describe={(task) => {
        const status = STATUS.find((item) => item.value === task.status) ?? STATUS[0];
        return <Badge size="xs" variant="light" color={status.color}>{status.label}</Badge>;
      }}
      create={(title, done) => save.mutate({ body: { title, status: "todo", objective: "", context: "", criteria: [], constraints: "" } }, done)}
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
      create={(title, done) => save.mutate({ body: { title, items: [] } }, done)}
      creating={save.isPending}
      renderEditor={(todo) => <TodoListEditor key={todo.name} project={project} todo={todo} />}
    />
  );
}

// ------------------------------------------------------------------- layout

type Named = { name: string; title: string };
type Done = { onSuccess: (created: Named) => void; onError: (error: Error) => void };

/** The notes of one type on the left (``?note=`` is the open one), its form on the right. */
function TypedNotes<T extends Named>({ items, error, newLabel, intro, describe, create, creating, renderEditor }: {
  project: string;
  items?: T[];
  error?: string;
  newLabel: string;
  intro: string;
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
function EditorShell({ project, name, dirty, valid, saving, error, onSave, children }: {
  project: string; name: string; dirty: boolean; valid: boolean; saving: boolean; error?: string; onSave: () => void; children: ReactNode;
}) {
  const remove = useDeleteNote(project);
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
        <ConfirmButton ml="auto" message={`Eliminare ${name}?`} loading={remove.isPending} error={remove.error?.message} onConfirm={() => remove.mutate(name)}>
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
  const [form, setForm] = useState<AgentTaskBody>(() => fields(task));
  const set = (patch: Partial<AgentTaskBody>) => setForm((current) => ({ ...current, ...patch }));
  const dirty = JSON.stringify(form) !== JSON.stringify(fields(task));
  const onSave = () =>
    save.mutate(
      { name: task.name, body: { ...form, criteria: (form.criteria ?? []).filter((item) => item.text.trim()) } },
      { onSuccess: (saved) => { setForm(fields(saved)); notifications.show({ message: `${saved.title} salvato.` }); } },
    );
  return (
    <EditorShell project={project} name={task.name} dirty={dirty} valid={!!form.title.trim()} saving={save.isPending} error={save.error?.message} onSave={onSave}>
      <TextInput label="Titolo" value={form.title} onChange={(event) => set({ title: event.currentTarget.value })} />
      <SegmentedControl
        style={{ alignSelf: "flex-start" }}
        data={STATUS.map(({ value, label }) => ({ value, label }))}
        value={form.status ?? "todo"}
        onChange={(value) => set({ status: value as AgentTaskBody["status"] })}
      />
      <Textarea label="Obiettivo" description="Cosa deve ottenere l'agente." autosize minRows={2} value={form.objective ?? ""} onChange={(event) => set({ objective: event.currentTarget.value })} />
      <Textarea label="Contesto" description="Repository, file, decisioni già prese." autosize minRows={2} value={form.context ?? ""} onChange={(event) => set({ context: event.currentTarget.value })} />
      <div>
        <Text size="sm" fw={500} mb={4}>Criteri di accettazione</Text>
        <ChecklistEditor items={form.criteria ?? []} onChange={(criteria) => set({ criteria })} addLabel="Criterio" placeholder="es. I test passano" />
      </div>
      <Textarea label="Vincoli" description="Cosa non deve fare o toccare." autosize minRows={2} value={form.constraints ?? ""} onChange={(event) => set({ constraints: event.currentTarget.value })} />
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
    </EditorShell>
  );
}
