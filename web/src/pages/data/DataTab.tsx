import { Alert, Anchor, Button, Card, FileInput, Grid, Group, Loader, Modal, NavLink, SegmentedControl, Stack, Text, TextInput, Textarea } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useQueryClient } from "@tanstack/react-query";
import { type ReactNode, useState } from "react";
import { useSearchParams } from "react-router-dom";

import {
  type DataFile, NOTE_PREFIXES, fileUrl, useAgentTasks, useDeleteFile, useDeleteNote, useFiles, useNote, useNotes, useSaveNote, useUploadFiles,
} from "../../api/projectData";
import { isDraft } from "../../api/publish";
import { WIP_NOTE, useWipState, wipKeys } from "../../api/wip";
import { ConfirmButton } from "../../components/ConfirmButton";
import { Markdown } from "../../components/Markdown";
import { localTime, size } from "../../format";
import { PublishButton } from "./PublishModal";
import { WipModal } from "./WipModal";

/** The pieces of a project's own data (notes, the WIP note, uploaded files): shown by the
 * zones «Lavoro» (pages/work/WorkZone.tsx) and «Progetto» (pages/project/ProjectZone.tsx). */

// -------------------------------------------------------------------- notes

/** The generic notes (the typed ones and the WIP note live in «Lavoro»). */
export function Notes({ project }: { project: string }) {
  const notes = useNotes(project);
  const [search, setSearch] = useSearchParams();
  const [creating, setCreating] = useState(false);
  const generic = notes.data?.filter((note) => (note.note_type ?? "generic") === "generic").map((note) => note.name) ?? [];
  const names = generic.filter((name) => name !== WIP_NOTE); // the WIP note lives in «Lavoro»
  const requested = search.get("note");
  const selected = requested && names.includes(requested) ? requested : names[0];
  const select = (name: string) => setSearch({ note: name }, { replace: true });

  return (
    <Grid gutter="md">
      <Grid.Col span={{ base: 12, md: 3 }}>
        <Stack gap="xs">
          <Button onClick={() => setCreating(true)}>➕ Nuova nota</Button>
          {notes.isPending && <Loader size="sm" />}
          {notes.error && <Alert color="red">{notes.error.message}</Alert>}
          {names.map((name) => (
            <NavLink key={name} label={name} active={name === selected} onClick={() => select(name)} />
          ))}
        </Stack>
      </Grid.Col>
      <Grid.Col span={{ base: 12, md: 9 }}>
        {selected ? (
          <NoteEditor key={selected} project={project} name={selected} />
        ) : (
          <Text c="dimmed">Le note sono file markdown del progetto: appunti, decisioni, contesto per gli agenti.</Text>
        )}
      </Grid.Col>
      <NewNoteModal project={project} existing={names} opened={creating} onClose={() => setCreating(false)} onCreated={select} />
    </Grid>
  );
}

function NoteEditor({ project, name }: { project: string; name: string }) {
  const note = useNote(project, name);
  if (note.error) return <Alert color="red">{note.error.message}</Alert>;
  if (note.isPending) return <Loader size="sm" />;
  return <NoteForm project={project} name={name} saved={note.data.content} extra={isDraft(name) ? () => <DraftPublish project={project} draft={name} /> : undefined} />;
}

/** A draft (``bozza-<task>.md``) is published from here too, for the task that links it. */
function DraftPublish({ project, draft }: { project: string; draft: string }) {
  const tasks = useAgentTasks(project);
  const task = tasks.data?.find((item) => (item.references ?? []).includes(draft));
  return task ? <PublishButton project={project} task={task} /> : null;
}

/** The WIP note: written freely, «📥 Elabora WIP» turns its new text (after
 * the last «elaborato il…» line) into proposals for the activities. */
export function WipEditor({ project }: { project: string }) {
  const state = useWipState(project);
  const [processing, setProcessing] = useState(false);
  if (state.error) return <Alert color="red">{state.error.message}</Alert>;
  if (state.isPending) return <Loader size="sm" />;
  const pending = state.data.pending_words;
  return (
    <>
      <NoteForm
        key={state.data.content} project={project} name={WIP_NOTE} saved={state.data.content} deletable={false}
        placeholder="Scrivi di getto cosa succede sul progetto: «📥 Elabora WIP» lo trasforma in attività e voci. mask{nome} nasconde un nome."
        extra={(dirty) => (
          <Button variant="light" onClick={() => setProcessing(true)} disabled={dirty || !pending}
                  title={dirty ? "Salva prima la nota" : pending ? undefined : "Niente di nuovo dopo l'ultimo segno"}>
            📥 Elabora WIP{pending ? ` (${pending} parole nuove)` : ""}
          </Button>
        )}
      />
      <WipModal project={project} opened={processing} onClose={() => setProcessing(false)} />
    </>
  );
}

function NoteForm({ project, name, saved, deletable = true, placeholder, extra }: {
  project: string; name: string; saved: string; deletable?: boolean; placeholder?: string; extra?: (dirty: boolean) => ReactNode;
}) {
  const save = useSaveNote(project);
  const remove = useDeleteNote(project);
  const queryClient = useQueryClient();
  const [text, setText] = useState(saved);
  const [view, setView] = useState("edit");
  const dirty = text !== saved;
  const onSave = () => save.mutate({ note: name, content: text }, {
    onSuccess: () => {
      notifications.show({ message: `${name} salvata.` });
      return queryClient.invalidateQueries({ queryKey: wipKeys.state(project) });
    },
  });
  return (
    <Stack gap="sm">
      <Group justify="space-between">
        <Text fw={600}>{name}{dirty && <Text span c="orange" size="sm"> · modifiche non salvate</Text>}</Text>
        <SegmentedControl size="xs" value={view} onChange={setView} data={[{ value: "edit", label: "Modifica" }, { value: "preview", label: "Anteprima" }]} />
      </Group>
      {view === "edit" ? (
        <Textarea
          autosize
          minRows={16}
          maxRows={30}
          placeholder={placeholder}
          styles={{ input: { fontFamily: "var(--mantine-font-family-monospace)" } }}
          value={text}
          onChange={(event) => setText(event.currentTarget.value)}
          onKeyDown={(event) => {
            if (event.key === "s" && (event.ctrlKey || event.metaKey)) {
              event.preventDefault();
              onSave();
            }
          }}
        />
      ) : (
        <Card withBorder><Markdown>{text}</Markdown></Card>
      )}
      {save.error && <Alert color="red">{save.error.message}</Alert>}
      <Group>
        <Button onClick={onSave} loading={save.isPending} disabled={!dirty}>Salva</Button>
        <Text size="xs" c="dimmed">Ctrl+S salva</Text>
        {extra?.(dirty)}
        {deletable && (
          <ConfirmButton
            ml="auto"
            message={`Eliminare ${name}?`}
            loading={remove.isPending}
            error={remove.error?.message}
            onConfirm={() => remove.mutate(name)}
          >
            Elimina
          </ConfirmButton>
        )}
      </Group>
    </Stack>
  );
}

function NewNoteModal({ project, existing, opened, onClose, onCreated }: {
  project: string; existing: string[]; opened: boolean; onClose: () => void; onCreated: (name: string) => void;
}) {
  const [name, setName] = useState("");
  const [error, setError] = useState<string>();
  const save = useSaveNote(project);
  const close = () => {
    setName("");
    setError(undefined);
    onClose();
  };
  const create = () => {
    const clean = name.trim();
    if (!clean) return setError("Il nome è obbligatorio.");
    const candidate = clean.toLowerCase().endsWith(".md") ? clean : `${clean}.md`;
    if (existing.some((item) => item.toLowerCase() === candidate.toLowerCase())) return setError(`Esiste già una nota ${candidate}.`);
    const reserved = Object.values(NOTE_PREFIXES).find((prefix) => candidate.toLowerCase().startsWith(prefix));
    if (reserved) return setError(`«${reserved}» è riservato: usa le tab Attività e Agent task.`);
    save.mutate(
      { note: clean, content: `# ${clean.replace(/\.md$/i, "")}\n` },
      { onSuccess: (note) => { onCreated(note.name); close(); }, onError: (exc) => setError(exc.message) },
    );
  };
  return (
    <Modal opened={opened} onClose={close} title="Nuova nota">
      <Stack>
        <TextInput
          label="Nome"
          placeholder="es. decisioni-architettura"
          data-autofocus
          value={name}
          error={error}
          onChange={(event) => setName(event.currentTarget.value)}
          onKeyDown={(event) => event.key === "Enter" && create()}
        />
        <Group><Button onClick={create} loading={save.isPending}>Crea</Button></Group>
      </Stack>
    </Modal>
  );
}

// -------------------------------------------------------------------- files

export function Files({ project }: { project: string }) {
  const files = useFiles(project);
  const upload = useUploadFiles(project);
  const [picked, setPicked] = useState<File[]>([]);
  return (
    <Stack gap="sm">
      <Group align="flex-end">
        <FileInput
          style={{ flex: 1 }}
          label="Carica documenti"
          description="Un file con lo stesso nome viene sovrascritto."
          placeholder="Scegli i file"
          multiple
          clearable
          value={picked}
          onChange={setPicked}
        />
        <Button disabled={!picked.length} loading={upload.isPending} onClick={() => upload.mutate(picked, { onSuccess: () => setPicked([]) })}>
          Salva {picked.length || ""} file
        </Button>
      </Group>
      {upload.error && <Alert color="red">{upload.error.message}</Alert>}
      {files.isPending && <Loader size="sm" />}
      {files.error && <Alert color="red">{files.error.message}</Alert>}
      {files.data && <Text size="xs" c="dimmed">{files.data.length} file</Text>}
      {files.data?.map((item) => <FileRow key={item.name} project={project} item={item} />)}
    </Stack>
  );
}

function FileRow({ project, item }: { project: string; item: DataFile }) {
  const remove = useDeleteFile(project);
  return (
    <Card withBorder padding="sm">
      <Group justify="space-between" wrap="nowrap">
        <div style={{ minWidth: 0 }}>
          <Text fw={600} size="sm" truncate>{item.name}</Text>
          <Text size="xs" c="dimmed">{size(item.size)} · {localTime(item.modified_at)}</Text>
        </div>
        <Group gap="xs" wrap="nowrap">
          <Anchor href={fileUrl(project, item.name)} download={item.name} size="sm">Scarica</Anchor>
          <ConfirmButton
            size="xs"
            message={`Eliminare ${item.name}?`}
            loading={remove.isPending}
            error={remove.error?.message}
            onConfirm={() => remove.mutate(item.name)}
          >
            Elimina
          </ConfirmButton>
        </Group>
      </Group>
    </Card>
  );
}
