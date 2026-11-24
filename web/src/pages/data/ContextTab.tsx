import { Alert, Badge, Button, Card, Grid, Group, Loader, Menu, Modal, NavLink, Stack, Tabs, Text, TextInput, Textarea } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useState } from "react";

import {
  useContextDocument, useContextDocuments, useContextIndex, useGenerateRepositoryMap, useGeneralContext, useDeleteContext, useReindexContext, useSaveContext, useSearchContext,
} from "../../api/context";
import { ConfirmButton } from "../../components/ConfirmButton";
import { Markdown } from "../../components/Markdown";

/** «📚 Contesto»: the documents of the project's context/ folder
 * (architecture, conventions, decisions, runbooks, glossary), under «Progetto»,
 * and the general context of the definitions (how the app works, read only),
 * under «Generale»: both groups start closed. «➕ Nuovo» makes an empty
 * document, a missing ready one or the repository map. Saving a document
 * indexes it; the agents search the index (search_context), Copilot gets only
 * the project's. A document is edited or seen formatted («👁 Anteprima»). */
/** The project's development rules: the Pianificatore reads them to propose the pre/post development tasks. */
export const RULES_DOCUMENT = "sviluppo.md";
export const RULES_TEMPLATE = `# Sviluppo

Le regole che il Pianificatore segue per proporre i task pre e post sviluppo attorno a ogni sviluppo (li fa Dev o tu, mai Copilot).

## Prima dello sviluppo
- Branch: feature/<task> dal branch develop aggiornato.
- Build delle librerie toccate prima dei servizi che le usano.

## Dopo lo sviluppo
- Togli la cartella mbare-pilot/ del task.
- Lancia i test del repository (solo quelli toccati se il progetto è grande).
- Commit e push li faccio io.

## Comandi
- Build: mvn -B clean install
- Test: mvn -B test
`;

/** The other ready documents: a button for each one the project lacks. */
export const TEMPLATES: { name: string; label: string; title: string; content: string }[] = [
  { name: "convenzioni.md", label: "📏 Convenzioni", title: "Branch, commit, package, stile e test: il Refiner e Copilot le seguono", content: `# Convenzioni

## Branch e commit
- Branch: feature/<ticket>-<breve-descrizione>, bugfix/<ticket>.
- Commit: «<TICKET> cosa cambia», al presente.

## Codice
- Package per funzionalità (es. it.azienda.ordini.api, …service, …repository).
- Nomi in inglese; niente Lombok (esempio: cambia con le vostre regole).

## Test
- Test di unità per ogni service; test di integrazione per i controller.
- Coverage minima del codice nuovo: 80%.
` },
  { name: "glossario.md", label: "📖 Glossario", title: "I termini del dominio: meno domande e meno invenzioni", content: `# Glossario

## Termini
- **Termine**: cosa significa nel progetto, in una riga.
- **Altro termine**: …

## Sigle
- **SIGLA**: per esteso e significato.
` },
  { name: "decisioni.md", label: "🧭 Decisioni", title: "Le scelte architetturali con il perché: evita proposte già scartate", content: `# Decisioni

## Titolo della decisione
- **Decisione**: cosa si è scelto.
- **Perché**: il motivo.
- **Scartato**: le alternative e perché no.
- **Data**: gg/mm/aaaa.
` },
];

/** The documents the app looks for by name: on top of «Progetto», with what uses them. */
export const SPECIAL: { name: string; icon: string; label: string; use: string }[] = [
  { name: RULES_DOCUMENT, icon: "📐", label: "Regole di sviluppo", use: "Il Pianificatore la legge per il pre e il post" },
  { name: "repository.md", icon: "🗺", label: "Mappa dei repository", use: "Generata da git e dai file; rigenerala dal documento" },
];
const MAP_DOCUMENT = "repository.md";
const same = (left: string, right: string) => left.toLowerCase() === right.toLowerCase();

export function ContextTab({ project }: { project: string }) {
  const documents = useContextDocuments(project);
  const save = useSaveContext(project);
  const generateMap = useGenerateRepositoryMap(project);
  const general = useGeneralContext(project);
  const [selected, setSelected] = useState<{ general: boolean; name: string }>();
  const [creating, setCreating] = useState(false);
  const names = documents.data?.map((item) => item.name) ?? [];
  const has = (name: string) => names.some((item) => same(item, name));
  const special = SPECIAL.flatMap((item) => names.filter((name) => same(name, item.name)).map((name) => ({ ...item, file: name })));
  const others = names.filter((name) => !SPECIAL.some((item) => same(item.name, name)));
  const missing = [
    { name: RULES_DOCUMENT, label: "📐 Regole di sviluppo", title: "Le regole per i task pre e post sviluppo: il Pianificatore le legge", content: RULES_TEMPLATE },
    ...TEMPLATES,
  ].filter((item) => !has(item.name));
  const open = (name: string, isGeneral = false) => setSelected({ general: isGeneral, name });
  const createFrom = (name: string, content: string) => save.mutate({ name, content }, { onSuccess: (saved) => open(saved.name) });
  const generate = () => generateMap.mutate(undefined, {
    onSuccess: (result) => {
      open(result.name);
      notifications.show({ color: result.index_error ? "orange" : "green", message: result.index_error ?? "Mappa dei repository aggiornata." });
    },
  });
  const current = selected && !selected.general && names.includes(selected.name) ? selected.name : undefined;
  const shownGeneral = selected?.general ? general.data?.find((item) => item.name === selected.name) : undefined;
  return (
    <Stack gap="md">
      <IndexBar project={project} />
      <Grid gutter="md">
        <Grid.Col span={{ base: 12, md: 3 }}>
          <Stack gap="xs">
            <Menu position="bottom-start" withinPortal>
              <Menu.Target>
                <Button loading={save.isPending || generateMap.isPending}>➕ Nuovo</Button>
              </Menu.Target>
              <Menu.Dropdown>
                <Menu.Item onClick={() => setCreating(true)}>📄 Documento vuoto</Menu.Item>
                {documents.data && !!missing.length && <Menu.Label>Modelli</Menu.Label>}
                {documents.data && missing.map((item) => (
                  <Menu.Item key={item.name} title={item.title} onClick={() => createFrom(item.name, item.content)}>{item.label}</Menu.Item>
                ))}
                {documents.data && !has(MAP_DOCUMENT) && (
                  <>
                    <Menu.Label>Dai repository</Menu.Label>
                    <Menu.Item title="Scrive repository.md dai file e da git: build, dipendenze tra repository, ordine di build, branch"
                      onClick={generate}>🗺 Mappa dei repository</Menu.Item>
                  </>
                )}
              </Menu.Dropdown>
            </Menu>
            {generateMap.error && <Alert color="red" p="xs">{generateMap.error.message}</Alert>}
            {save.error && !creating && <Alert color="red" p="xs">{save.error.message}</Alert>}
            {documents.isPending && <Loader size="sm" />}
            {documents.error && <Alert color="red">{documents.error.message}</Alert>}
            <NavLink component="button" label="Progetto" rightSection={<Badge size="sm" variant="light">{names.length}</Badge>}
                     description="I documenti del progetto: si cambiano qui" childrenOffset={8} defaultOpened={false}>
              {documents.data && !names.length && <Text size="xs" c="dimmed" p="xs">Nessun documento: creane uno con «➕ Nuovo».</Text>}
              {special.map((item) => (
                <NavLink key={item.file} label={`${item.icon} ${item.label}`} description={`${item.file} · ${item.use}`}
                         active={item.file === current} onClick={() => open(item.file)} />
              ))}
              {others.map((name) => <NavLink key={name} label={name} active={name === current} onClick={() => open(name)} />)}
            </NavLink>
            <NavLink component="button" label="Generale (da definizioni)" rightSection={<Badge size="sm" variant="light" color="gray">{general.data?.length ?? 0}</Badge>}
                     description="Come funziona l'app, uguale per tutti i progetti" childrenOffset={8} defaultOpened={false}>
              {general.data && !general.data.length && <Text size="xs" c="dimmed" p="xs">Nessun documento in definition/context/.</Text>}
              {general.data?.map((item) => (
                <NavLink key={item.name} label={item.title} description={`${item.name}${item.origin === "tuo" ? " · tuo" : ""}`}
                         active={item.name === shownGeneral?.name} onClick={() => open(item.name, true)} />
              ))}
            </NavLink>
          </Stack>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 9 }}>
          {shownGeneral ? <GeneralDocument name={shownGeneral.name} content={shownGeneral.content} />
            : current ? (
              <ContextEditor key={current} project={project} name={current}
                             regenerate={same(current, MAP_DOCUMENT) ? { run: generate, pending: generateMap.isPending } : undefined} />
            ) : (
              <Text c="dimmed">
                Apri un documento da «Progetto» o «Generale». Scrivi qui quello che serve sapere sul progetto: architettura, convenzioni,
                decisioni, runbook, glossario. Un titolo «##» per argomento: gli agenti e Copilot cercano i pezzi giusti, con la fonte.
              </Text>
            )}
        </Grid.Col>
      </Grid>
      <NewContextModal project={project} existing={names} opened={creating} onClose={() => setCreating(false)} onCreated={(name) => open(name)} />
    </Stack>
  );
}

/** A document of the general context: read only, formatted by default. */
function GeneralDocument({ name, content }: { name: string; content: string }) {
  return (
    <Stack gap="xs">
      <Group gap="xs"><Badge variant="light" color="gray">sola lettura</Badge><Text size="xs" c="dimmed">definition/context/{name}: si cambia nelle definizioni</Text></Group>
      <Tabs defaultValue="preview" keepMounted={false}>
        <Tabs.List>
          <Tabs.Tab value="preview">👁 Anteprima</Tabs.Tab>
          <Tabs.Tab value="text">📄 Testo</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="preview" pt="xs"><Markdown>{content}</Markdown></Tabs.Panel>
        <Tabs.Panel value="text" pt="xs">
          <Textarea aria-label="Documento generale" value={content} readOnly autosize minRows={10} ff="monospace" />
        </Tabs.Panel>
      </Tabs>
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
              🔎 Indice: <b>{index.data.documents}</b> documenti{!!index.data.general && <> (di cui {index.data.general} generali)</>}, <b>{index.data.pieces}</b> pezzi
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
              <Badge size="xs" variant="outline" color={hit.origin === "generale" ? "gray" : "blue"}>{hit.origin}</Badge>
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

type Regenerate = { run: () => void; pending: boolean };

function ContextEditor({ project, name, regenerate }: { project: string; name: string; regenerate?: Regenerate }) {
  const document = useContextDocument(project, name);
  if (document.error) return <Alert color="red">{document.error.message}</Alert>;
  if (document.isPending) return <Loader size="sm" />;
  // a new saved text (saved here, or the map regenerated) starts the form again
  return <ContextForm key={document.data.content} project={project} name={name} saved={document.data.content} regenerate={regenerate} />;
}

function ContextForm({ project, name, saved, regenerate }: { project: string; name: string; saved: string; regenerate?: Regenerate }) {
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
      <Group gap="xs">
        <Text fw={600}>{name}{dirty && <Text span c="orange" size="sm"> · modifiche non salvate</Text>}</Text>
        {regenerate && (
          <Button size="compact-sm" variant="light" ml="auto" loading={regenerate.pending} onClick={regenerate.run}
                  title="Riscrive solo la parte automatica (build, dipendenze, ordine di build, branch): il resto del documento resta">
            🗺 Rigenera
          </Button>
        )}
      </Group>
      <Tabs defaultValue="edit">
        <Tabs.List>
          <Tabs.Tab value="edit">✏️ Modifica</Tabs.Tab>
          <Tabs.Tab value="preview">👁 Anteprima</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="edit" pt="xs">
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
        </Tabs.Panel>
        <Tabs.Panel value="preview" pt="xs">
          {text.trim() ? <Markdown>{text}</Markdown> : <Text size="sm" c="dimmed">Il documento è vuoto.</Text>}
        </Tabs.Panel>
      </Tabs>
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
