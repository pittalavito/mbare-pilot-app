import { Alert, Anchor, Button, Card, FileInput, Grid, Group, Loader, Modal, NavLink, SegmentedControl, Stack, Tabs, Text, TextInput, Textarea } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";

import {
  type DataFile, fileUrl, useDeleteFile, useDeleteNote, useFiles, useNote, useNotes, useSaveNote, useUploadFiles,
} from "../../api/projectData";
import { ConfirmButton } from "../../components/ConfirmButton";
import { Markdown } from "../../components/Markdown";
import { localTime, size } from "../../format";

/** The Dati tab of a project: its own data, kept by the app apart from its
 * code: markdown notes written here and uploaded files (sources of the RAG index). */
export function DataTab() {
  const { project = "" } = useParams();
  return (
    <Tabs defaultValue="notes" keepMounted={false}>
      <Tabs.List mb="md">
        <Tabs.Tab value="notes">📝 Note</Tabs.Tab>
        <Tabs.Tab value="files">📎 File</Tabs.Tab>
      </Tabs.List>
      <Tabs.Panel value="notes"><Notes project={project} /></Tabs.Panel>
      <Tabs.Panel value="files"><Files project={project} /></Tabs.Panel>
    </Tabs>
  );
}

// -------------------------------------------------------------------- notes

function Notes({ project }: { project: string }) {
  const notes = useNotes(project);
  const [search, setSearch] = useSearchParams();
  const [creating, setCreating] = useState(false);
  const names = notes.data?.map((note) => note.name) ?? [];
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
          {notes.data && !notes.data.length && <Text size="sm" c="dimmed">Nessuna nota.</Text>}
          {names.map((name) => <NavLink key={name} label={name} active={name === selected} onClick={() => select(name)} />)}
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
  const save = useSaveNote(project);
  const remove = useDeleteNote(project);
  const [text, setText] = useState<string>();
  const [view, setView] = useState("edit");
  useEffect(() => {
    if (note.data && text === undefined) setText(note.data.content);
  }, [note.data, text]);

  if (note.isPending || text === undefined) return <Loader size="sm" />;
  if (note.error) return <Alert color="red">{note.error.message}</Alert>;
  const dirty = text !== note.data.content;
  const onSave = () => save.mutate({ note: name, content: text }, { onSuccess: () => notifications.show({ message: `${name} salvata.` }) });
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
        <ConfirmButton
          ml="auto"
          message={`Eliminare ${name}?`}
          loading={remove.isPending}
          error={remove.error?.message}
          onConfirm={() => remove.mutate(name)}
        >
          Elimina
        </ConfirmButton>
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

function Files({ project }: { project: string }) {
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
