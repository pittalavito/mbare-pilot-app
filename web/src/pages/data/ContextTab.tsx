import { Alert, Badge, Button, Card, Grid, Group, Loader, Modal, NavLink, Stack, Text, TextInput, Textarea } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useState } from "react";

import {
  useContextDocument, useContextDocuments, useContextIndex, useDeleteContext, useReindexContext, useSaveContext, useSearchContext,
} from "../../api/context";
import { ConfirmButton } from "../../components/ConfirmButton";

/** «📚 Contesto»: the documents of the project's context/ folder
 * (architecture, conventions, decisions, runbooks, glossary). Saving one
 * indexes it; the Refiner and Copilot search the index (search_context),
 * together with the done activities that have «Imparato». */
export function ContextTab({ project }: { project: string }) {
  const documents = useContextDocuments(project);
  const [selected, setSelected] = useState<string>();
  const [creating, setCreating] = useState(false);
  const names = documents.data?.map((item) => item.name) ?? [];
  const current = selected && names.includes(selected) ? selected : names[0];
  return (
    <Stack gap="md">
      <IndexBar project={project} />
      <Grid gutter="md">
        <Grid.Col span={{ base: 12, md: 3 }}>
          <Stack gap="xs">
            <Button onClick={() => setCreating(true)}>➕ Nuovo documento</Button>
            {documents.isPending && <Loader size="sm" />}
            {documents.error && <Alert color="red">{documents.error.message}</Alert>}
            {documents.data && !names.length && <Text size="sm" c="dimmed">Nessun documento di contesto.</Text>}
            {names.map((name) => <NavLink key={name} label={name} active={name === current} onClick={() => setSelected(name)} />)}
          </Stack>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 9 }}>
          {current ? <ContextEditor key={current} project={project} name={current} /> : (
            <Text c="dimmed">
              Scrivi qui quello che serve sapere sul progetto: architettura, convenzioni, decisioni, runbook, glossario. Un titolo «##» per
              argomento: il Refiner e Copilot cercano i pezzi giusti, con la fonte.
            </Text>
          )}
        </Grid.Col>
      </Grid>
      <NewContextModal project={project} existing={names} opened={creating} onClose={() => setCreating(false)} onCreated={setSelected} />
    </Stack>
  );
}

/** What the index holds, «Reindicizza tutto», and a search to see what the agents would get. */
function IndexBar({ project }: { project: string }) {
  const index = useContextIndex(project);
  const reindex = useReindexContext(project);
  const search = useSearchContext(project);
  const [question, setQuestion] = useState("");
  return (
    <Card withBorder p="sm">
      <Stack gap="xs">
        <Group gap="xs">
          {index.data && (
            <Text size="sm">
              🔎 Indice: <b>{index.data.documents}</b> documenti, <b>{index.data.pieces}</b> pezzi
              {index.data.embedder && <> · embedder <code>{index.data.embedder}</code></>}
            </Text>
          )}
          <Button size="compact-xs" variant="light" ml="auto" loading={reindex.isPending}
                  onClick={() => reindex.mutate(undefined, { onSuccess: (state) => notifications.show({ message: `Indice aggiornato: ${state.documents} documenti.` }) })}>
            🔄 Reindicizza tutto
          </Button>
        </Group>
        {index.data?.error && <Alert color="orange" p="xs">{index.data.error}</Alert>}
        {reindex.error && <Alert color="red" p="xs">{reindex.error.message}</Alert>}
        <Group gap="xs" wrap="nowrap">
          <TextInput size="xs" style={{ flex: 1 }} placeholder="Prova una ricerca, es. «come si fa il rollback?»" aria-label="Prova una ricerca"
                     value={question} onChange={(event) => setQuestion(event.currentTarget.value)}
                     onKeyDown={(event) => event.key === "Enter" && question.trim() && search.mutate(question)} />
          <Button size="xs" onClick={() => search.mutate(question)} loading={search.isPending} disabled={!question.trim()}>Cerca</Button>
        </Group>
        {search.error && <Alert color="red" p="xs">{search.error.message}</Alert>}
        {search.data && !search.data.length && <Text size="xs" c="dimmed">Niente: l'indice è vuoto.</Text>}
        {search.data?.map((hit) => (
          <Card key={`${hit.path}-${hit.section}-${hit.text.slice(0, 20)}`} withBorder p="xs">
            <Group gap="xs">
              <Badge size="xs" variant="light">{hit.score.toFixed(2)}</Badge>
              <Text size="xs" fw={500}>{hit.title}{hit.section && <> › {hit.section}</>}</Text>
              <Text size="xs" c="dimmed">{hit.path}</Text>
            </Group>
            <Text size="xs" lineClamp={3} style={{ whiteSpace: "pre-wrap" }}>{hit.text}</Text>
          </Card>
        ))}
      </Stack>
    </Card>
  );
}

function ContextEditor({ project, name }: { project: string; name: string }) {
  const document = useContextDocument(project, name);
  if (document.error) return <Alert color="red">{document.error.message}</Alert>;
  if (document.isPending) return <Loader size="sm" />;
  return <ContextForm project={project} name={name} saved={document.data.content} />;
}

function ContextForm({ project, name, saved }: { project: string; name: string; saved: string }) {
  const save = useSaveContext(project);
  const remove = useDeleteContext(project);
  const [text, setText] = useState(saved);
  const dirty = text !== saved;
  const onSave = () => save.mutate({ name, content: text }, {
    onSuccess: (result) => notifications.show(result.index_error
      ? { color: "orange", message: `${name} salvato, ma non indicizzato: ${result.index_error}` }
      : { message: `${name} salvato e indicizzato.` }),
  });
  return (
    <Stack gap="sm">
      <Text fw={600}>{name}{dirty && <Text span c="orange" size="sm"> · modifiche non salvate</Text>}</Text>
      <Textarea
        autosize minRows={16} maxRows={30} aria-label="Testo del documento"
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
      {save.error && <Alert color="red">{save.error.message}</Alert>}
      <Group>
        <Button onClick={onSave} loading={save.isPending} disabled={!dirty}>Salva</Button>
        <Text size="xs" c="dimmed">Salvare lo reindicizza (solo se è cambiato)</Text>
        <ConfirmButton ml="auto" message={`Eliminare ${name}? Esce anche dall'indice.`} loading={remove.isPending} error={remove.error?.message}
                       onConfirm={() => remove.mutate(name)}>
          Elimina
        </ConfirmButton>
      </Group>
    </Stack>
  );
}

function NewContextModal({ project, existing, opened, onClose, onCreated }: {
  project: string; existing: string[]; opened: boolean; onClose: () => void; onCreated: (name: string) => void;
}) {
  const save = useSaveContext(project);
  const [name, setName] = useState("");
  const [error, setError] = useState<string>();
  const close = () => { setName(""); setError(undefined); onClose(); };
  const create = () => {
    const clean = name.trim();
    if (!clean) return setError("Il nome è obbligatorio.");
    const candidate = clean.toLowerCase().endsWith(".md") ? clean : `${clean}.md`;
    if (existing.some((item) => item.toLowerCase() === candidate.toLowerCase())) return setError(`Esiste già ${candidate}.`);
    save.mutate({ name: clean, content: `# ${clean.replace(/\.md$/i, "")}\n\n## \n` },
      { onSuccess: (saved) => { onCreated(saved.name); close(); }, onError: (exc) => setError(exc.message) });
  };
  return (
    <Modal opened={opened} onClose={close} title="Nuovo documento di contesto">
      <Stack>
        <TextInput label="Nome" placeholder="es. architettura" data-autofocus value={name} error={error}
                   onChange={(event) => setName(event.currentTarget.value)} onKeyDown={(event) => event.key === "Enter" && create()} />
        <Group><Button onClick={create} loading={save.isPending}>Crea</Button></Group>
      </Stack>
    </Modal>
  );
}
