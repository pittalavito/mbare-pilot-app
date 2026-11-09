import { ActionIcon, Alert, Anchor, Badge, Button, Card, Group, Modal, SegmentedControl, Select, Stack, Text, TextInput, Textarea } from "@mantine/core";
import { useEffect, useState } from "react";

import { useSearchParams } from "react-router-dom";

import {
  type CodeTodoScan, FILE_LINK_PREFIX, type Reference, type ReferenceBody, type ReferenceKind, fileUrl, useDeleteReference, useFiles, useNotes,
  useReferences, useSaveReference, useScanCodeTodos,
} from "../../api/projectData";
import { size } from "../../format";
import { ConfirmButton } from "../../components/ConfirmButton";
import { CodeTodoHelp, TODO_EXAMPLE } from "./CodeTodoHelp";

/** The code and context references of an agent task or an activity. A
 * reference is a note of its own (``code-reference-<title>.md``...) linked by
 * name, many to many: here only the links change (saved with the task or
 * list); a reference itself is saved as soon as it is created or edited. A
 * generic note (by name) or an uploaded file (``files/<name>``) is linked as it
 * is: Copilot gets it in the task's folder. */

const KINDS: Record<ReferenceKind, { label: string; color: string }> = {
  code_reference: { label: "Codice", color: "violet" },
  context_reference: { label: "Contesto", color: "teal" },
};
const EMPTY: ReferenceBody = { title: "", source: "", source_url: "", repository: "", path: "", lines: "", content: "" };

export function ReferencesSection({ project, value, onChange }: { project: string; value: string[]; onChange: (names: string[]) => void }) {
  const references = useReferences(project);
  const notes = useNotes(project);
  const files = useFiles(project);
  const [, setSearch] = useSearchParams();
  const [editing, setEditing] = useState<Reference | "new">();
  const byName = new Map((references.data ?? []).map((reference) => [reference.name, reference]));
  const noteNames = new Set((notes.data ?? []).filter((note) => (note.note_type ?? "generic") === "generic").map((note) => note.name));
  const fileByLink = new Map((files.data ?? []).map((file) => [FILE_LINK_PREFIX + file.name, file]));
  const others = (references.data ?? []).filter((reference) => !value.includes(reference.name));
  const options = [
    { group: "Riferimenti", items: others.map((reference) => ({ value: reference.name, label: `${reference.title} · ${KINDS[reference.kind as ReferenceKind]?.label ?? reference.kind}` })) },
    { group: "Note", items: [...noteNames].filter((name) => !value.includes(name)).map((name) => ({ value: name, label: name })) },
    { group: "File", items: [...fileByLink.keys()].filter((link) => !value.includes(link)).map((link) => ({ value: link, label: link.slice(FILE_LINK_PREFIX.length) })) },
  ].filter((group) => group.items.length);

  return (
    <Stack gap="xs">
      <Group justify="space-between">
        <Text size="sm" fw={500}>📎 Riferimenti</Text>
        <Group gap="xs">
          <ScanCodeTodosButton project={project} onScanned={(note) => !value.includes(note) && onChange([...value, note])} />
          <Button size="xs" variant="light" onClick={() => setEditing("new")}>➕ Nuovo riferimento</Button>
        </Group>
      </Group>
      {references.error && <Alert color="red">{references.error.message}</Alert>}
      {!value.length && <Text size="xs" c="dimmed">Nessun riferimento collegato: codice o contesto (anche copiato da Jira, Confluence…), una nota o un file utile per questo lavoro.</Text>}
      {value.map((name) => {
        const reference = byName.get(name);
        const file = fileByLink.get(name);
        const note = noteNames.has(name);
        const label = reference?.title ?? (file ? file.name : name);
        return (
          <Card key={name} withBorder p="xs">
            <Group justify="space-between" wrap="nowrap" align="flex-start">
              {reference ? <ReferenceSummary reference={reference} /> : file ? (
                <Group gap="xs"><Badge size="xs" variant="light" color="cyan">File</Badge><Text size="sm">{file.name}</Text><Text size="xs" c="dimmed">{size(file.size)}</Text></Group>
              ) : note ? (
                <Group gap="xs"><Badge size="xs" variant="light" color="gray">Nota</Badge><Text size="sm">{name}</Text></Group>
              ) : (
                <Text size="sm" c="orange"><code>{name}</code> · non trovato (cancellato a mano?)</Text>
              )}
              <Group gap={4} wrap="nowrap">
                {reference && <Button size="compact-xs" variant="subtle" onClick={() => setEditing(reference)}>Modifica</Button>}
                {file && <Anchor size="xs" href={fileUrl(project, file.name)} target="_blank" rel="noreferrer">Scarica</Anchor>}
                {note && <Button size="compact-xs" variant="subtle" onClick={() => setSearch({ note: name }, { replace: true })}>Apri</Button>}
                <ActionIcon variant="subtle" color="gray" aria-label={`Scollega ${label}`} onClick={() => onChange(value.filter((item) => item !== name))}>
                  ✕
                </ActionIcon>
              </Group>
            </Group>
          </Card>
        );
      })}
      {options.length > 0 && (
        <Select
          size="xs"
          placeholder="Collega un riferimento, una nota o un file…"
          searchable
          data={options}
          value={null}
          onChange={(name) => name && onChange([...value, name])}
        />
      )}
      <ReferenceModal
        project={project}
        reference={editing === "new" ? undefined : editing}
        opened={editing !== undefined}
        onClose={() => setEditing(undefined)}
        onCreated={(name) => onChange([...value, name])}
        onDeleted={(name) => onChange(value.filter((item) => item !== name))}
      />
    </Stack>
  );
}

/** What a scan found, said to the user. */
export function scanMessage(scan: CodeTodoScan): string {
  if (!scan.note) return `Nessun commento todoMbarePilot nel codice: scrivilo così, ${TODO_EXAMPLE}`;
  const found = scan.comments
    ? `${scan.comments} ${scan.comments === 1 ? "commento" : "commenti"} todoMbarePilot in ${scan.files} file`
    : "Nessun commento todoMbarePilot valido";
  const wrong = scan.malformed ? `; ${scan.malformed} da correggere (scritti male, elencati nella nota)` : "";
  return `${found}${wrong}: nota ${scan.created ? "creata" : "aggiornata"}.`;
}

/** «🔍 Todo del codice»: gathers the code's todoMbarePilot comments into their
 * note, without an agent; ``onScanned`` gets the note (none when nothing was found). */
export function ScanCodeTodosButton({ project, onScanned }: { project: string; onScanned: (note: string) => void }) {
  const scan = useScanCodeTodos(project);
  return (
    <Group gap="xs" wrap="nowrap">
      {scan.data && <Text size="xs" c={scan.data.malformed ? "orange" : "dimmed"}>{scanMessage(scan.data)}</Text>}
      {scan.error && <Text size="xs" c="red">{scan.error.message}</Text>}
      <Button
        size="xs"
        variant="default"
        loading={scan.isPending}
        title="Cerca i commenti todoMbarePilot{…} nel codice e li raccoglie nella nota «TODO Mbare Pilot»"
        onClick={() => scan.mutate(undefined, { onSuccess: (result) => result.note && onScanned(result.note) })}
      >
        🔍 Todo del codice
      </Button>
      <CodeTodoHelp />
    </Group>
  );
}

export function ReferenceSummary({ reference }: { reference: Reference }) {
  const kind = KINDS[reference.kind as ReferenceKind];
  const where = [reference.repository, reference.path, reference.lines && `righe ${reference.lines}`].filter(Boolean).join(" · ");
  const others = reference.linked_from.length;
  return (
    <Stack gap={2} style={{ minWidth: 0 }}>
      <Group gap="xs">
        <Badge size="xs" variant="light" color={kind?.color}>{kind?.label ?? reference.kind}</Badge>
        <Text size="sm" fw={500}>{reference.title}</Text>
        {reference.source && <Badge size="xs" variant="outline">{reference.source}</Badge>}
      </Group>
      {where && <Text size="xs" c="dimmed"><code>{where}</code></Text>}
      {reference.source_url && <Anchor size="xs" href={reference.source_url} target="_blank" rel="noreferrer">{reference.source_url}</Anchor>}
      {others > 1 && <Text size="xs" c="dimmed">Collegato anche ad altri {others - 1}</Text>}
    </Stack>
  );
}

/** Create (no ``reference``) or edit a reference; deleting it unlinks it everywhere. */
export function ReferenceModal({ project, reference, opened, onClose, onCreated, onDeleted, createLabel = "Crea e collega" }: {
  project: string; reference?: Reference; opened: boolean; onClose: () => void;
  /** The create button: «Crea e collega» from a task, «Crea» where nothing links it. */
  createLabel?: string;
  onCreated: (name: string) => void;
  /** The server unlinks it everywhere: the open form drops it too. */
  onDeleted: (name: string) => void;
}) {
  const save = useSaveReference(project);
  const remove = useDeleteReference(project);
  const [kind, setKind] = useState<ReferenceKind>("context_reference");
  const [form, setForm] = useState<ReferenceBody>(EMPTY);
  const set = (patch: Partial<ReferenceBody>) => setForm((current) => ({ ...current, ...patch }));
  const code = (reference?.kind ?? kind) === "code_reference";

  useEffect(() => {
    if (!opened) return;
    save.reset();
    remove.reset();
    setKind((reference?.kind as ReferenceKind | undefined) ?? "context_reference");
    setForm(reference ? { title: reference.title, source: reference.source, source_url: reference.source_url, repository: reference.repository,
      path: reference.path, lines: reference.lines, content: reference.content } : EMPTY);
  }, [opened, reference]); // a fresh form each time it opens

  const submit = () =>
    save.mutate(
      { name: reference?.name, kind, body: form },
      { onSuccess: (saved) => { if (!reference) onCreated(saved.name); onClose(); } },
    );

  return (
    <Modal opened={opened} onClose={onClose} title={reference ? `Riferimento: ${reference.title}` : "Nuovo riferimento"} size="lg">
      <Stack gap="sm">
        {reference ? <Text size="xs" c="dimmed"><code>{reference.name}</code></Text> : (
          <SegmentedControl
            style={{ alignSelf: "flex-start" }}
            data={[{ value: "context_reference", label: "Contesto" }, { value: "code_reference", label: "Codice" }]}
            value={kind}
            onChange={(next) => setKind(next as ReferenceKind)}
          />
        )}
        <TextInput label="Titolo" data-autofocus value={form.title} onChange={(event) => set({ title: event.currentTarget.value })} />
        <Group grow>
          <TextInput label="Fonte" description="Vuota = scritto a mano; es. jira, confluence, dynatrace" value={form.source ?? ""} onChange={(event) => set({ source: event.currentTarget.value })} />
          <TextInput label="Link" value={form.source_url ?? ""} onChange={(event) => set({ source_url: event.currentTarget.value })} />
        </Group>
        {code && (
          <Group grow>
            <TextInput label="Repository" value={form.repository ?? ""} onChange={(event) => set({ repository: event.currentTarget.value })} />
            <TextInput label="File" value={form.path ?? ""} onChange={(event) => set({ path: event.currentTarget.value })} />
            <TextInput label="Righe" placeholder="es. 10-40" value={form.lines ?? ""} onChange={(event) => set({ lines: event.currentTarget.value })} />
          </Group>
        )}
        <Textarea
          label="Contenuto" description={code ? "Il codice o perché conta per il task." : "Il testo di contesto (markdown)."}
          autosize minRows={4} value={form.content ?? ""} onChange={(event) => set({ content: event.currentTarget.value })}
        />
        {save.error && <Alert color="red">{save.error.message}</Alert>}
        <Group>
          <Button onClick={submit} loading={save.isPending} disabled={!form.title.trim()}>{reference ? "Salva" : createLabel}</Button>
          {reference && (
            <ConfirmButton
              ml="auto"
              message={`Eliminare ${reference.name}? Viene scollegato da ${reference.linked_from.length === 1 ? "1 elemento" : `${reference.linked_from.length} elementi`}.`}
              loading={remove.isPending}
              error={remove.error?.message}
              onConfirm={() => remove.mutate(reference.name, { onSuccess: () => { onDeleted(reference.name); onClose(); } })}
            >
              Elimina
            </ConfirmButton>
          )}
        </Group>
      </Stack>
    </Modal>
  );
}
